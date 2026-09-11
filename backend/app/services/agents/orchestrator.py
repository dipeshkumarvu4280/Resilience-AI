import uuid
import json
import hashlib
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError, PyMongoError
from app.models.enums import (
    AgentName,
    AgentRunStatus,
    CoordinationPlanStatus,
    PlanReviewAction,
    SeverityLevel,
    NeedUrgency,
    ResourceType,
    ResourceStatus,
    TimelineEventType,
    UserRole,
)
from app.models.agent import (
    AgentContext,
    AgentResult,
    AgentRunRecord,
    CoordinationPlan,
    OfficerPlanReview,
    PlanRecommendedResource,
    DetectedConflict,
    ConflictResolutionSummary,
    RecommendedShelter,
    ShelterCoordinationSummary,
    RecommendedHealthcareFacility,
    HealthcareCoordinationSummary,
    RecommendedVolunteerAssignment,
    VolunteerCoordinationSummary,
    RecommendedTransport,
    RecommendedRoute,
    RouteTransportCoordinationSummary,
)
from app.services.agents.registry import agent_registry
from app.services.agents.adapters.priority_agent import PriorityAgent
from app.services.agents.adapters.needs_agent import NeedsAgent
from app.services.agents.adapters.resource_agent import ResourceCoordinationAgent
from app.services.agents.adapters.conflict_agent import ConflictResolutionAgent
from app.services.agents.adapters.shelter_agent import ShelterCoordinationAgent
from app.services.agents.adapters.healthcare_agent import HealthcareCoordinationAgent
from app.services.agents.adapters.volunteer_agent import VolunteerCoordinationAgent
from app.services.agents.adapters.route_agent import RouteTransportCoordinationAgent
from app.services.timeline import record_timeline_event
from app.db.mongodb import db_manager

logger = logging.getLogger("resilience.agents.orchestrator")


def compute_situation_state_fingerprint(situation: Dict[str, Any]) -> str:
    """
    Computes a deterministic canonical fingerprint (SHA-256 hash) of the situation's
    coordination-relevant state. Any material change in severity, reports, emergency type,
    or location produces a different fingerprint.
    """
    clean_sit_id = str(situation.get("situation_id", "")).strip().upper()
    emergency_type = str(situation.get("emergency_type", ""))
    status = str(situation.get("status", "ACTIVE"))
    override_sev = situation.get("officer_override_severity") or situation.get("officer_severity_override")
    computed_sev = situation.get("computed_severity_level") or situation.get("severity_level") or "MEDIUM"
    effective_sev = str(override_sev or computed_sev).upper()

    raw_report_ids = situation.get("report_ids") or situation.get("member_report_ids") or []
    report_ids = sorted([str(r).strip().upper() for r in raw_report_ids if r])

    center_loc = situation.get("center_location") or {}
    lat = center_loc.get("latitude")
    lng = center_loc.get("longitude")
    affected_pop = situation.get("estimated_affected_population") or 0
    casualties = situation.get("estimated_casualties") or situation.get("casualty_count") or 0

    payload = {
        "situation_id": clean_sit_id,
        "emergency_type": emergency_type,
        "status": status,
        "effective_severity": effective_sev,
        "officer_override": str(override_sev).upper() if override_sev else None,
        "report_ids": report_ids,
        "report_count": len(report_ids),
        "lat": round(float(lat), 4) if lat is not None else None,
        "lng": round(float(lng), 4) if lng is not None else None,
        "affected_pop": affected_pop,
        "casualties": casualties,
    }
    canonical_json = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]


class CentralOrchestrator:
    """
    Central Orchestrator Agent.
    Evaluates real situation intelligence, deterministically selects required agent capabilities,
    executes all 8 specialized domain agents in topological order, validates outputs, and
    synthesizes a formal, authoritative Coordination Plan requiring Emergency Officer review.
    Guarantees idempotency via situation state fingerprinting and concurrency locks.
    """

    def __init__(self):
        self._situation_locks: Dict[str, asyncio.Lock] = {}
        # Auto-register Phase 5 foundational agent adapters
        self._ensure_default_agents_registered()

    def _get_situation_lock(self, situation_id: str) -> asyncio.Lock:
        if situation_id not in self._situation_locks:
            self._situation_locks[situation_id] = asyncio.Lock()
        return self._situation_locks[situation_id]

    def _ensure_default_agents_registered(self):
        """Initializes and registers standard adapters into the global registry."""
        if not agent_registry.has_agent(AgentName.PRIORITY_AGENT):
            agent_registry.register(PriorityAgent())
        if not agent_registry.has_agent(AgentName.NEEDS_AGENT):
            agent_registry.register(NeedsAgent())
        if not agent_registry.has_agent(AgentName.RESOURCE_COORDINATION_AGENT):
            agent_registry.register(ResourceCoordinationAgent())
        if not agent_registry.has_agent(AgentName.CONFLICT_RESOLUTION_AGENT):
            agent_registry.register(ConflictResolutionAgent())
        if not agent_registry.has_agent(AgentName.SHELTER_AGENT):
            agent_registry.register(ShelterCoordinationAgent())
        if not agent_registry.has_agent(AgentName.HEALTHCARE_AGENT):
            agent_registry.register(HealthcareCoordinationAgent())
        if not agent_registry.has_agent(AgentName.VOLUNTEER_AGENT):
            agent_registry.register(VolunteerCoordinationAgent())
        if not agent_registry.has_agent(AgentName.ROUTE_AGENT):
            agent_registry.register(RouteTransportCoordinationAgent())

    def get_registered_agent_names(self) -> List[AgentName]:
        return agent_registry.list_agents()

    def select_required_agents(self, situation: Dict[str, Any]) -> List[AgentName]:
        """
        Deterministically selects the exact sequence of specialized domain agents required
        to coordinate this situation cluster based on situation intelligence.
        """
        required: List[AgentName] = []

        # 1. Priority Agent (Always required for situational operational severity)
        if agent_registry.has_agent(AgentName.PRIORITY_AGENT):
            required.append(AgentName.PRIORITY_AGENT)

        # 2. Needs Agent (Always required for structured emergency provisions)
        if agent_registry.has_agent(AgentName.NEEDS_AGENT):
            required.append(AgentName.NEEDS_AGENT)

        # 3. Resource Coordination Agent (Always required for inventory matching)
        if agent_registry.has_agent(AgentName.RESOURCE_COORDINATION_AGENT):
            required.append(AgentName.RESOURCE_COORDINATION_AGENT)

        # 4. Shelter Coordination Agent
        if agent_registry.has_agent(AgentName.SHELTER_AGENT):
            required.append(AgentName.SHELTER_AGENT)

        # 5. Healthcare Coordination Agent
        if agent_registry.has_agent(AgentName.HEALTHCARE_AGENT):
            required.append(AgentName.HEALTHCARE_AGENT)

        # 6. Volunteer Coordination Agent
        if agent_registry.has_agent(AgentName.VOLUNTEER_AGENT):
            required.append(AgentName.VOLUNTEER_AGENT)

        # 7. Route & Transport Coordination Agent
        if agent_registry.has_agent(AgentName.ROUTE_AGENT):
            required.append(AgentName.ROUTE_AGENT)

        # 8. Conflict Resolution Agent (Consolidates all domain recommendations & conflicts)
        if agent_registry.has_agent(AgentName.CONFLICT_RESOLUTION_AGENT):
            required.append(AgentName.CONFLICT_RESOLUTION_AGENT)

        return required

    async def orchestrate_situation(
        self,
        situation_id: str,
        actor: Dict[str, Any],
        force_refresh: bool = False,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> CoordinationPlan:
        """
        Executes multi-agent coordination pipeline across all 8 specialized agents for a given situation cluster.
        Guarantees strict idempotency, auditability, and safety constraints.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        clean_sit_id = situation_id.strip().upper()

        # Synchronize concurrent requests for the same situation via in-memory lock
        async with self._get_situation_lock(clean_sit_id):
            # 1. Fetch Real Situation Cluster from MongoDB Atlas
            situation = await db["situations"].find_one({"situation_id": clean_sit_id})
            if not situation:
                situation = await db["situation_clusters"].find_one({"situation_id": clean_sit_id})
            if not situation:
                raise ValueError(f"Situation {situation_id} does not exist in database.")

            state_fingerprint = compute_situation_state_fingerprint(situation)

            # 2. Strict Idempotency Check
            # Case A: Active pending or draft plan already exists
            existing_active_plan = await db["coordination_plans"].find_one({
                "situation_id": clean_sit_id,
                "status": {"$in": [
                    CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
                    CoordinationPlanStatus.DRAFT.value,
                ]}
            }, sort=[("generated_at", -1)])

            if existing_active_plan:
                existing_fp = existing_active_plan.get("state_fingerprint")
                # If situation state hasn't changed and force_refresh is False, return existing pending plan
                if not force_refresh and existing_fp == state_fingerprint:
                    logger.info(
                        f"Returning existing active coordination plan {existing_active_plan.get('plan_id')} "
                        f"for situation {clean_sit_id} (idempotent, fingerprint={state_fingerprint})"
                    )
                    return CoordinationPlan(**existing_active_plan)
                else:
                    # Situation materially changed or force_refresh requested: supersede old pending plan
                    logger.info(
                        f"Superseding older pending plan {existing_active_plan.get('plan_id')} for {clean_sit_id} "
                        f"due to state change (old_fp={existing_fp}, new_fp={state_fingerprint}, force_refresh={force_refresh})"
                    )
                    await db["coordination_plans"].update_one(
                        {"plan_id": existing_active_plan["plan_id"]},
                        {"$set": {"status": CoordinationPlanStatus.SUPERSEDED.value}}
                    )

            # Case B: No pending plan, but an active or finalized (ACTIVE/APPROVED/REJECTED/MODIFIED) plan exists
            if not force_refresh:
                latest_final_plan = await db["coordination_plans"].find_one({
                    "situation_id": clean_sit_id,
                    "status": {"$in": [
                        CoordinationPlanStatus.ACTIVE.value,
                        CoordinationPlanStatus.APPROVED.value,
                        CoordinationPlanStatus.MODIFIED.value,
                        CoordinationPlanStatus.REJECTED.value,
                        CoordinationPlanStatus.EXECUTED.value,
                    ]}
                }, sort=[("generated_at", -1)])

                if latest_final_plan and (latest_final_plan.get("state_fingerprint") == state_fingerprint or latest_final_plan.get("status") in [CoordinationPlanStatus.APPROVED.value, CoordinationPlanStatus.ACTIVE.value]):
                    logger.info(
                        f"Situation {clean_sit_id} has existing approved/active plan "
                        f"{latest_final_plan.get('plan_id')}. Reusing plan (idempotent)."
                    )
                    return CoordinationPlan(**latest_final_plan)

            # Determine next version
            latest_any_plan = await db["coordination_plans"].find_one(
                {"situation_id": clean_sit_id},
                sort=[("version", -1)]
            )
            next_version = (latest_any_plan.get("version", 0) + 1) if latest_any_plan else 1

            # 3. Build Base Agent Context from Authoritative Situation Data & Saved Needs Assessments
            center_loc = situation.get("center_location", {})
            override_val = situation.get("officer_override_severity") or situation.get("officer_severity_override")
            officer_override = SeverityLevel(override_val) if override_val else None

            member_report_ids = situation.get("report_ids") or situation.get("member_report_ids", [])
            authoritative_needs_list: List[Dict[str, Any]] = []

            # A. Check if situation already has explicitly embedded assessed_needs
            if situation.get("assessed_needs"):
                for n in situation["assessed_needs"]:
                    n_dict = dict(n) if isinstance(n, dict) else n.model_dump()
                    n_dict.setdefault("source", "OFFICER_NEEDS_ASSESSMENT")
                    n_dict.setdefault("officer_assessed", True)
                    n_dict.setdefault("ai_inferred", False)
                    authoritative_needs_list.append(n_dict)

            # B. Query needs_assessments collection for situation_id and all member_report_ids
            query_ids = [clean_sit_id] + [str(r).strip().upper() for r in member_report_ids if r]
            assessments_cursor = db["needs_assessments"].find({
                "$or": [
                    {"situation_id": {"$in": query_ids}},
                    {"report_id": {"$in": query_ids}},
                ]
            })
            assessment_docs = await assessments_cursor.to_list(length=100)
            for doc in assessment_docs:
                doc_needs = doc.get("needs", [])
                for n in doc_needs:
                    n_dict = dict(n) if isinstance(n, dict) else n.model_dump()
                    r_type = n_dict.get("resource_type")
                    req_qty = float(n_dict.get("requested_quantity") or n_dict.get("quantity") or 0.0)
                    existing_match = next((item for item in authoritative_needs_list if item.get("resource_type") == r_type), None)
                    if existing_match:
                        # Sum requirements if from multiple member reports
                        new_total = float(existing_match.get("requested_quantity", 0.0)) + req_qty
                        existing_match["requested_quantity"] = new_total
                        existing_match["quantity"] = new_total
                    else:
                        n_dict["requested_quantity"] = req_qty
                        n_dict["quantity"] = req_qty
                        n_dict["source"] = "OFFICER_NEEDS_ASSESSMENT"
                        n_dict["officer_assessed"] = True
                        n_dict["ai_inferred"] = False
                        authoritative_needs_list.append(n_dict)

            # Query member reports for multimodal visual evidence & extractions
            member_visuals = []
            member_llm_extractions = []
            if member_report_ids:
                rep_cursor = db["citizen_reports"].find(
                    {"report_id": {"$in": member_report_ids}},
                    {"visual_evidence": 1, "llm_extraction": 1, "evidence_verification": 1, "corroboration": 1}
                )
                rep_docs = await rep_cursor.to_list(length=100)
                for rd in rep_docs:
                    if rd.get("visual_evidence"):
                        member_visuals.append(rd["visual_evidence"])
                    if rd.get("llm_extraction"):
                        member_llm_extractions.append(rd["llm_extraction"])

            context_params: Dict[str, Any] = {
                "visual_evidence": situation.get("visual_evidence") or (member_visuals[0] if member_visuals else None),
                "member_visual_evidence": member_visuals,
                "llm_extraction": situation.get("llm_extraction") or (member_llm_extractions[0] if member_llm_extractions else None),
            }

            base_context = AgentContext(
                situation_id=clean_sit_id,
                situation_title=situation.get("title", f"Emergency Situation {clean_sit_id}"),
                emergency_type=situation.get("emergency_type", "General Emergency"),
                description=situation.get("situation_summary") or situation.get("title") or "Active incident response.",
                location_summary=center_loc.get("address") or center_loc.get("city") or "Operational Zone",
                center_latitude=center_loc.get("latitude"),
                center_longitude=center_loc.get("longitude"),
                report_count=situation.get("report_count", 1),
                member_report_ids=member_report_ids,
                officer_severity_override=officer_override,
                existing_needs=authoritative_needs_list,
                actor_id=actor.get("id"),
                actor_name=actor.get("full_name"),
                actor_role=actor.get("role"),
                state_fingerprint=state_fingerprint,
                parameters=context_params,
            )

            actor_role_enum = None
            if actor.get("role"):
                try:
                    actor_role_enum = UserRole(actor.get("role"))

                except Exception:
                    pass

            # Record Orchestration Started Audit Event
            await record_timeline_event(
                db=db,
                report_id=clean_sit_id,
                event_type=TimelineEventType.ORCHESTRATION_STARTED,
                details=f"Multi-agent coordination initiated for situation {clean_sit_id} (v{next_version}, {base_context.emergency_type}).",
                actor_id=actor.get("id"),
                actor_name=actor.get("full_name"),
                actor_role=actor_role_enum,
            )

            # 4. Select and Order Required Agents
            required_agents = self.select_required_agents(situation)
            agent_results: Dict[str, AgentResult] = {}

            # 5. Pipeline Execution
            # Step A: Priority Agent
            priority_res: Optional[AgentResult] = None
            if AgentName.PRIORITY_AGENT in required_agents:
                agent = agent_registry.get(AgentName.PRIORITY_AGENT)
                if agent:
                    priority_res = await self._run_and_track_agent(
                        agent, base_context, actor, force_refresh=force_refresh, db=db
                    )
                    agent_results[AgentName.PRIORITY_AGENT.value] = priority_res

            effective_priority = officer_override or (
                SeverityLevel(priority_res.structured_output["severity_level"])
                if priority_res and "severity_level" in priority_res.structured_output
                else SeverityLevel.MEDIUM
            )

            # Step B: Needs Agent
            needs_res: Optional[AgentResult] = None
            assessed_needs_list: List[Dict[str, Any]] = []
            if AgentName.NEEDS_AGENT in required_agents:
                agent = agent_registry.get(AgentName.NEEDS_AGENT)
                if agent:
                    needs_context = AgentContext(
                        situation_id=base_context.situation_id,
                        situation_title=base_context.situation_title,
                        emergency_type=base_context.emergency_type,
                        description=base_context.description,
                        location_summary=base_context.location_summary,
                        center_latitude=base_context.center_latitude,
                        center_longitude=base_context.center_longitude,
                        report_count=base_context.report_count,
                        member_report_ids=base_context.member_report_ids,
                        officer_severity_override=base_context.officer_severity_override,
                        existing_needs=base_context.existing_needs,
                        state_fingerprint=state_fingerprint,
                        parameters={
                            "assessed_priority": effective_priority.value,
                            "hazard_category": priority_res.structured_output.get("hazard_category") if priority_res else None,
                        },
                        actor_id=actor.get("id"),
                        actor_name=actor.get("full_name"),
                        actor_role=actor.get("role"),
                    )
                    needs_res = await self._run_and_track_agent(
                        agent, needs_context, actor, force_refresh=force_refresh, db=db
                    )
                    agent_results[AgentName.NEEDS_AGENT.value] = needs_res
                    assessed_needs_list = needs_res.structured_output.get("needs", [])

            # Step C: Resource Coordination Agent
            resource_res: Optional[AgentResult] = None
            recommended_allocations: List[PlanRecommendedResource] = []
            if AgentName.RESOURCE_COORDINATION_AGENT in required_agents:
                agent = agent_registry.get(AgentName.RESOURCE_COORDINATION_AGENT)
                if agent:
                    res_context = AgentContext(
                        situation_id=base_context.situation_id,
                        situation_title=base_context.situation_title,
                        emergency_type=base_context.emergency_type,
                        description=base_context.description,
                        location_summary=base_context.location_summary,
                        center_latitude=base_context.center_latitude,
                        center_longitude=base_context.center_longitude,
                        report_count=base_context.report_count,
                        member_report_ids=base_context.member_report_ids,
                        officer_severity_override=base_context.officer_severity_override,
                        existing_needs=base_context.existing_needs,
                        state_fingerprint=state_fingerprint,
                        parameters={
                            "assessed_needs": assessed_needs_list,
                            "effective_priority": effective_priority.value,
                        },
                        actor_id=actor.get("id"),
                        actor_name=actor.get("full_name"),
                        actor_role=actor.get("role"),
                    )
                    resource_res = await self._run_and_track_agent(
                        agent, res_context, actor, force_refresh=force_refresh, db=db
                    )
                    agent_results[AgentName.RESOURCE_COORDINATION_AGENT.value] = resource_res

                    matches = resource_res.structured_output.get("matches", [])
                    for m in matches:
                        r_type = m["resource_type"]
                        u_val = m["urgency"]
                        recommended_allocations.append(PlanRecommendedResource(
                            resource_type=ResourceType(r_type) if isinstance(r_type, str) else r_type,
                            quantity_required=float(m.get("quantity_required", m.get("quantity", 1.0))),
                            unit=m.get("unit", "Units"),
                            urgency=NeedUrgency(u_val) if isinstance(u_val, str) else u_val,
                            matched_resource_id=m.get("matched_resource_id"),
                            matched_resource_name=m.get("matched_resource_name"),
                            available_in_inventory=m.get("available_in_inventory", 0.0),
                            allocated_quantity=m.get("allocated_quantity", 0.0),
                            depot_location=m.get("depot_location"),
                            distance_km=m.get("distance_km"),
                            reasoning=m.get("reasoning", "Recommended regional depot match."),
                        ))

            # Step D: Shelter Coordination Agent
            shelter_res: Optional[AgentResult] = None
            recommended_shelters: List[RecommendedShelter] = []
            shelter_summary: Optional[ShelterCoordinationSummary] = None
            officer_attention_required: bool = False

            if AgentName.SHELTER_AGENT in required_agents:
                agent = agent_registry.get(AgentName.SHELTER_AGENT)
                if agent:
                    # Query real shelters from DB
                    real_shelters_cursor = db["resources"].find({
                        "$or": [
                            {"resource_type": {"$in": ["Shelter", "SHELTER", "shelter"]}},
                            {"category": {"$in": ["Shelter", "SHELTER", "shelter", "Camp", "Evacuation"]}},
                            {"name": {"$regex": "Shelter|Camp|Evacuation|Community Hall", "$options": "i"}},
                        ]
                    })
                    db_shelters = await real_shelters_cursor.to_list(length=100)

                    # Extract affected population from situation or assessed needs
                    sit_pop = situation.get("estimated_affected_population")
                    if sit_pop is None or sit_pop <= 0:
                        for n in assessed_needs_list:
                            if n.get("resource_type") in [ResourceType.SHELTER, ResourceType.SHELTER.value, "Shelter"]:
                                sit_pop = int(float(n.get("requested_quantity", 0)))
                                break

                    # Record Shelter Analysis Started Timeline Event
                    await record_timeline_event(
                        db=db,
                        report_id=clean_sit_id,
                        event_type=TimelineEventType.SHELTER_ANALYSIS_STARTED,
                        details=f"Evaluating emergency shelter facility capacity, proximity, and suitability for situation {clean_sit_id}.",
                        actor_id=actor.get("id"),
                        actor_name=actor.get("full_name"),
                        actor_role=actor_role_enum,
                    )

                    shl_context = AgentContext(
                        situation_id=base_context.situation_id,
                        situation_title=base_context.situation_title,
                        emergency_type=base_context.emergency_type,
                        description=base_context.description,
                        location_summary=base_context.location_summary,
                        center_latitude=base_context.center_latitude,
                        center_longitude=base_context.center_longitude,
                        report_count=base_context.report_count,
                        member_report_ids=base_context.member_report_ids,
                        officer_severity_override=base_context.officer_severity_override,
                        existing_needs=base_context.existing_needs,
                        state_fingerprint=state_fingerprint,
                        parameters={
                            "assessed_needs": assessed_needs_list,
                            "effective_priority": effective_priority.value,
                            "affected_population": sit_pop,
                            "available_shelters": db_shelters,
                        },
                        actor_id=actor.get("id"),
                        actor_name=actor.get("full_name"),
                        actor_role=actor.get("role"),
                    )

                    shelter_res = await self._run_and_track_agent(
                        agent, shl_context, actor, force_refresh=force_refresh, db=db
                    )
                    agent_results[AgentName.SHELTER_AGENT.value] = shelter_res

                    if shelter_res and shelter_res.structured_output:
                        try:
                            shelter_summary = ShelterCoordinationSummary(**shelter_res.structured_output)
                            recommended_shelters = shelter_summary.shelters_recommended
                            if shelter_summary.officer_attention_required:
                                officer_attention_required = True

                            await record_timeline_event(
                                db=db,
                                report_id=clean_sit_id,
                                event_type=TimelineEventType.SHELTER_EVALUATED,
                                details=f"Evaluated {shelter_summary.shelters_evaluated} shelter facility(ies) for situation {clean_sit_id}.",
                                actor_id=actor.get("id"),
                                actor_name=actor.get("full_name"),
                                actor_role=actor_role_enum,
                            )

                            if len(recommended_shelters) > 0:
                                await record_timeline_event(
                                    db=db,
                                    report_id=clean_sit_id,
                                    event_type=TimelineEventType.SHELTER_RECOMMENDED,
                                    details=f"Recommended {len(recommended_shelters)} shelter facility(ies) covering {int(shelter_summary.total_population_covered)} evacuees.",
                                    actor_id=actor.get("id"),
                                    actor_name=actor.get("full_name"),
                                    actor_role=actor_role_enum,
                                    metadata={"shelters": [s.model_dump() for s in recommended_shelters]},
                                )

                            if shelter_summary.total_shortfall > 0:
                                await record_timeline_event(
                                    db=db,
                                    report_id=clean_sit_id,
                                    event_type=TimelineEventType.SHELTER_CAPACITY_SHORTFALL,
                                    details=f"Shelter capacity shortfall detected: {int(shelter_summary.total_shortfall)} persons unaccommodated.",
                                    actor_id=actor.get("id"),
                                    actor_name=actor.get("full_name"),
                                    actor_role=actor_role_enum,
                                )

                            await record_timeline_event(
                                db=db,
                                report_id=clean_sit_id,
                                event_type=TimelineEventType.SHELTER_ANALYSIS_COMPLETED,
                                details=f"Shelter coordination analysis completed ({len(recommended_shelters)} recommended, {int(shelter_summary.total_shortfall)} shortfall).",
                                actor_id=actor.get("id"),
                                actor_name=actor.get("full_name"),
                                actor_role=actor_role_enum,
                            )
                        except Exception as parse_err:
                            logger.error(f"Error parsing shelter coordination summary: {parse_err}")

            # Step E: Healthcare Coordination Agent
            healthcare_res: Optional[AgentResult] = None
            recommended_facilities: List[RecommendedHealthcareFacility] = []
            healthcare_summary: Optional[HealthcareCoordinationSummary] = None

            if AgentName.HEALTHCARE_AGENT in required_agents:
                agent = agent_registry.get(AgentName.HEALTHCARE_AGENT)
                if agent:
                    # Query genuine medical facilities / hospitals from DB
                    hcf_cursor = db["healthcare_facilities"].find({"is_deleted": {"$ne": True}})
                    db_facilities = await hcf_cursor.to_list(length=100)

                    # Also query resources collection for any healthcare items
                    med_cursor = db["resources"].find({
                        "$or": [
                            {"resource_type": {"$in": ["Hospital", "Medical", "Healthcare", "Clinic"]}},
                            {"category": {"$in": ["Hospital", "Medical", "Healthcare", "Clinic"]}},
                            {"name": {"$regex": "Hospital|Clinic|Medical|Health|Trauma", "$options": "i"}},
                        ]
                    })
                    res_facilities = await med_cursor.to_list(length=100)
                    existing_ids = {str(f.get("facility_id") or f.get("_id")) for f in db_facilities}
                    for rf in res_facilities:
                        rf_id = str(rf.get("facility_id") or rf.get("resource_id") or rf.get("_id"))
                        if rf_id not in existing_ids:
                            db_facilities.append(rf)
                            existing_ids.add(rf_id)

                    # Extract casualties
                    sit_cas = situation.get("estimated_casualties") or situation.get("casualty_count") or situation.get("injured_count")

                    await record_timeline_event(
                        db=db,
                        report_id=clean_sit_id,
                        event_type=TimelineEventType.HEALTHCARE_ANALYSIS_STARTED,
                        details=f"Evaluating hospital capacity, ICU beds, oxygen readiness, and casualty demands for situation {clean_sit_id}.",
                        actor_id=actor.get("id"),
                        actor_name=actor.get("full_name"),
                        actor_role=actor_role_enum,
                    )

                    hlt_context = AgentContext(
                        situation_id=base_context.situation_id,
                        situation_title=base_context.situation_title,
                        emergency_type=base_context.emergency_type,
                        description=base_context.description,
                        location_summary=base_context.location_summary,
                        center_latitude=base_context.center_latitude,
                        center_longitude=base_context.center_longitude,
                        report_count=base_context.report_count,
                        member_report_ids=base_context.member_report_ids,
                        officer_severity_override=base_context.officer_severity_override,
                        existing_needs=base_context.existing_needs,
                        state_fingerprint=state_fingerprint,
                        parameters={
                            "assessed_needs": assessed_needs_list,
                            "effective_priority": effective_priority.value,
                            "estimated_casualties": sit_cas,
                            "available_facilities": db_facilities,
                        },
                        actor_id=actor.get("id"),
                        actor_name=actor.get("full_name"),
                        actor_role=actor.get("role"),
                    )

                    healthcare_res = await self._run_and_track_agent(
                        agent, hlt_context, actor, force_refresh=force_refresh, db=db
                    )
                    agent_results[AgentName.HEALTHCARE_AGENT.value] = healthcare_res

                    if healthcare_res and healthcare_res.structured_output:
                        try:
                            healthcare_summary = HealthcareCoordinationSummary(**healthcare_res.structured_output)
                            recommended_facilities = healthcare_summary.facilities_recommended
                            if healthcare_summary.officer_attention_required:
                                officer_attention_required = True

                            await record_timeline_event(
                                db=db,
                                report_id=clean_sit_id,
                                event_type=TimelineEventType.HEALTHCARE_FACILITY_EVALUATED,
                                details=f"Evaluated {healthcare_summary.facilities_evaluated} healthcare facility(ies) for situation {clean_sit_id}.",
                                actor_id=actor.get("id"),
                                actor_name=actor.get("full_name"),
                                actor_role=actor_role_enum,
                            )

                            if len(recommended_facilities) > 0:
                                await record_timeline_event(
                                    db=db,
                                    report_id=clean_sit_id,
                                    event_type=TimelineEventType.HEALTHCARE_ROUTING_RECOMMENDED,
                                    details=f"Recommended {len(recommended_facilities)} healthcare facility(ies) routing {int(healthcare_summary.total_patients_covered)} casualties.",
                                    actor_id=actor.get("id"),
                                    actor_name=actor.get("full_name"),
                                    actor_role=actor_role_enum,
                                    metadata={"facilities": [f.model_dump() for f in recommended_facilities]},
                                )

                            if healthcare_summary.total_shortfall > 0:
                                await record_timeline_event(
                                    db=db,
                                    report_id=clean_sit_id,
                                    event_type=TimelineEventType.HEALTHCARE_CAPACITY_DEFICIT,
                                    details=f"Healthcare capacity deficit detected: {int(healthcare_summary.total_shortfall)} casualties unaccommodated.",
                                    actor_id=actor.get("id"),
                                    actor_name=actor.get("full_name"),
                                    actor_role=actor_role_enum,
                                )

                            await record_timeline_event(
                                db=db,
                                report_id=clean_sit_id,
                                event_type=TimelineEventType.HEALTHCARE_ANALYSIS_COMPLETED,
                                details=f"Healthcare coordination analysis completed ({len(recommended_facilities)} recommended, {int(healthcare_summary.total_shortfall)} shortfall).",
                                actor_id=actor.get("id"),
                                actor_name=actor.get("full_name"),
                                actor_role=actor_role_enum,
                            )
                        except Exception as parse_err:
                            logger.error(f"Error parsing healthcare coordination summary: {parse_err}")

            # Step F: Volunteer Coordination Agent
            volunteer_res: Optional[AgentResult] = None
            recommended_volunteers: List[RecommendedVolunteerAssignment] = []
            volunteer_summary: Optional[VolunteerCoordinationSummary] = None

            if AgentName.VOLUNTEER_AGENT in required_agents:
                agent = agent_registry.get(AgentName.VOLUNTEER_AGENT)
                if agent:
                    # Query genuine registered volunteers from DB
                    vol_cursor = db["users"].find({
                        "$or": [
                            {"role": {"$in": [UserRole.VOLUNTEER.value, "VOLUNTEER", "volunteer"]}},
                            {"volunteer_profile": {"$ne": None}},
                        ]
                    })
                    db_volunteers = await vol_cursor.to_list(length=200)

                    await record_timeline_event(
                        db=db,
                        report_id=clean_sit_id,
                        event_type=TimelineEventType.VOLUNTEER_ANALYSIS_STARTED,
                        details=f"Evaluating verified volunteer responder availability, skill matches, and proximity for situation {clean_sit_id}.",
                        actor_id=actor.get("id"),
                        actor_name=actor.get("full_name"),
                        actor_role=actor_role_enum,
                    )

                    vol_context = AgentContext(
                        situation_id=base_context.situation_id,
                        situation_title=base_context.situation_title,
                        emergency_type=base_context.emergency_type,
                        description=base_context.description,
                        location_summary=base_context.location_summary,
                        center_latitude=base_context.center_latitude,
                        center_longitude=base_context.center_longitude,
                        report_count=base_context.report_count,
                        member_report_ids=base_context.member_report_ids,
                        officer_severity_override=base_context.officer_severity_override,
                        existing_needs=base_context.existing_needs,
                        state_fingerprint=state_fingerprint,
                        parameters={
                            "assessed_needs": assessed_needs_list,
                            "effective_priority": effective_priority.value,
                            "available_volunteers": db_volunteers,
                        },
                        actor_id=actor.get("id"),
                        actor_name=actor.get("full_name"),
                        actor_role=actor.get("role"),
                    )

                    volunteer_res = await self._run_and_track_agent(
                        agent, vol_context, actor, force_refresh=force_refresh, db=db
                    )
                    agent_results[AgentName.VOLUNTEER_AGENT.value] = volunteer_res

                    if volunteer_res and volunteer_res.structured_output:
                        try:
                            volunteer_summary = VolunteerCoordinationSummary(**volunteer_res.structured_output)
                            recommended_volunteers = volunteer_summary.volunteers_recommended
                            if volunteer_summary.officer_attention_required:
                                officer_attention_required = True

                            await record_timeline_event(
                                db=db,
                                report_id=clean_sit_id,
                                event_type=TimelineEventType.VOLUNTEER_EVALUATED,
                                details=f"Evaluated {volunteer_summary.volunteers_evaluated} volunteer responder(s) for situation {clean_sit_id}.",
                                actor_id=actor.get("id"),
                                actor_name=actor.get("full_name"),
                                actor_role=actor_role_enum,
                            )

                            if len(recommended_volunteers) > 0:
                                await record_timeline_event(
                                    db=db,
                                    report_id=clean_sit_id,
                                    event_type=TimelineEventType.VOLUNTEER_ASSIGNMENT_RECOMMENDED,
                                    details=f"Recommended {len(recommended_volunteers)} volunteer assignment(s) for field operations.",
                                    actor_id=actor.get("id"),
                                    actor_name=actor.get("full_name"),
                                    actor_role=actor_role_enum,
                                    metadata={"volunteers": [v.model_dump() for v in recommended_volunteers]},
                                )

                            if volunteer_summary.total_shortfall > 0:
                                await record_timeline_event(
                                    db=db,
                                    report_id=clean_sit_id,
                                    event_type=TimelineEventType.VOLUNTEER_SHORTAGE_DETECTED,
                                    details=f"Volunteer responder shortage detected: {volunteer_summary.total_shortfall} responder role(s) unfilled.",
                                    actor_id=actor.get("id"),
                                    actor_name=actor.get("full_name"),
                                    actor_role=actor_role_enum,
                                )

                            await record_timeline_event(
                                db=db,
                                report_id=clean_sit_id,
                                event_type=TimelineEventType.VOLUNTEER_ANALYSIS_COMPLETED,
                                details=f"Volunteer coordination analysis completed ({len(recommended_volunteers)} assigned, {volunteer_summary.total_shortfall} shortfall).",
                                actor_id=actor.get("id"),
                                actor_name=actor.get("full_name"),
                                actor_role=actor_role_enum,
                            )
                        except Exception as parse_err:
                            logger.error(f"Error parsing volunteer coordination summary: {parse_err}")

            # Step G: Route & Transport Coordination Agent
            route_res: Optional[AgentResult] = None
            recommended_transports: List[RecommendedTransport] = []
            recommended_routes: List[RecommendedRoute] = []
            route_summary: Optional[RouteTransportCoordinationSummary] = None

            if AgentName.ROUTE_AGENT in required_agents:
                agent = agent_registry.get(AgentName.ROUTE_AGENT)
                if agent:
                    # Query genuine vehicles / transports from DB
                    veh_cursor = db["resources"].find({
                        "$or": [
                            {"resource_type": "Transport"},
                            {"category": {"$in": ["Vehicle", "Transport", "Fleet"]}},
                            {"name": {"$regex": "Truck|Ambulance|Bus|Van|Boat|Transport|Pickup", "$options": "i"}},
                        ]
                    })
                    db_vehicles = await veh_cursor.to_list(length=100)

                    await record_timeline_event(
                        db=db,
                        report_id=clean_sit_id,
                        event_type=TimelineEventType.ROUTE_ANALYSIS_STARTED,
                        details=f"Evaluating transit corridors, road conditions, and fleet assignments for situation {clean_sit_id}.",
                        actor_id=actor.get("id"),
                        actor_name=actor.get("full_name"),
                        actor_role=actor_role_enum,
                    )

                    rot_context = AgentContext(
                        situation_id=base_context.situation_id,
                        situation_title=base_context.situation_title,
                        emergency_type=base_context.emergency_type,
                        description=base_context.description,
                        location_summary=base_context.location_summary,
                        center_latitude=base_context.center_latitude,
                        center_longitude=base_context.center_longitude,
                        report_count=base_context.report_count,
                        member_report_ids=base_context.member_report_ids,
                        officer_severity_override=base_context.officer_severity_override,
                        existing_needs=base_context.existing_needs,
                        state_fingerprint=state_fingerprint,
                        parameters={
                            "assessed_needs": assessed_needs_list,
                            "recommended_allocations": [a.model_dump() for a in recommended_allocations],
                            "recommended_shelters": [s.model_dump() for s in recommended_shelters],
                            "recommended_facilities": [f.model_dump() for f in recommended_facilities],
                            "effective_priority": effective_priority.value,
                            "affected_population": situation.get("estimated_affected_population", 0),
                            "estimated_casualties": situation.get("estimated_casualties", 0),
                            "available_vehicles": db_vehicles,
                        },
                        actor_id=actor.get("id"),
                        actor_name=actor.get("full_name"),
                        actor_role=actor.get("role"),
                    )

                    route_res = await self._run_and_track_agent(
                        agent, rot_context, actor, force_refresh=force_refresh, db=db
                    )
                    agent_results[AgentName.ROUTE_AGENT.value] = route_res

                    if route_res and route_res.structured_output:
                        try:
                            route_summary = RouteTransportCoordinationSummary(**route_res.structured_output)
                            recommended_transports = route_summary.transports_recommended
                            recommended_routes = route_summary.routes_recommended
                            if route_summary.officer_attention_required:
                                officer_attention_required = True

                            await record_timeline_event(
                                db=db,
                                report_id=clean_sit_id,
                                event_type=TimelineEventType.ROUTE_EVALUATED,
                                details=f"Evaluated {route_summary.routes_evaluated} transit route(s) and {route_summary.total_vehicles_assigned} fleet vehicle(s) for situation {clean_sit_id}.",
                                actor_id=actor.get("id"),
                                actor_name=actor.get("full_name"),
                                actor_role=actor_role_enum,
                            )

                            if len(recommended_transports) > 0:
                                await record_timeline_event(
                                    db=db,
                                    report_id=clean_sit_id,
                                    event_type=TimelineEventType.TRANSPORT_RECOMMENDED,
                                    details=f"Recommended {len(recommended_transports)} vehicle assignment(s) for emergency transit.",
                                    actor_id=actor.get("id"),
                                    actor_name=actor.get("full_name"),
                                    actor_role=actor_role_enum,
                                    metadata={"transports": [t.model_dump() for t in recommended_transports]},
                                )

                            if len(recommended_routes) > 0:
                                await record_timeline_event(
                                    db=db,
                                    report_id=clean_sit_id,
                                    event_type=TimelineEventType.ROUTE_RECOMMENDED,
                                    details=f"Recommended {len(recommended_routes)} clearance route(s) for rapid ingress/egress.",
                                    actor_id=actor.get("id"),
                                    actor_name=actor.get("full_name"),
                                    actor_role=actor_role_enum,
                                    metadata={"routes": [r.model_dump() for r in recommended_routes]},
                                )

                            if route_summary.transport_shortfall > 0:
                                await record_timeline_event(
                                    db=db,
                                    report_id=clean_sit_id,
                                    event_type=TimelineEventType.TRANSPORT_CAPACITY_DEFICIT,
                                    details=f"Transport capacity deficit detected: {route_summary.transport_shortfall} vehicle requirement(s) unfulfilled.",
                                    actor_id=actor.get("id"),
                                    actor_name=actor.get("full_name"),
                                    actor_role=actor_role_enum,
                                )

                            await record_timeline_event(
                                db=db,
                                report_id=clean_sit_id,
                                event_type=TimelineEventType.ROUTE_ANALYSIS_COMPLETED,
                                details=f"Route & transport coordination analysis completed ({len(recommended_routes)} routes, {len(recommended_transports)} transports).",
                                actor_id=actor.get("id"),
                                actor_name=actor.get("full_name"),
                                actor_role=actor_role_enum,
                            )
                        except Exception as parse_err:
                            logger.error(f"Error parsing route coordination summary: {parse_err}")

            # Step H: Conflict Resolution Agent (Consolidates all domain recommendations & shortfalls)
            conflict_res: Optional[AgentResult] = None
            detected_conflicts: List[DetectedConflict] = []
            conflict_summary: Optional[ConflictResolutionSummary] = None
            has_unresolved_conflicts: bool = False

            if AgentName.CONFLICT_RESOLUTION_AGENT in required_agents:
                agent = agent_registry.get(AgentName.CONFLICT_RESOLUTION_AGENT)
                if agent:
                    await record_timeline_event(
                        db=db,
                        report_id=clean_sit_id,
                        event_type=TimelineEventType.CONFLICT_ANALYSIS_STARTED,
                        details=f"Evaluating multi-domain resource availability, supply deficits, shelter capacities, medical bottlenecks, and route conflicts for situation {clean_sit_id}.",
                        actor_id=actor.get("id"),
                        actor_name=actor.get("full_name"),
                        actor_role=actor_role_enum,
                    )

                    cnf_context = AgentContext(
                        situation_id=base_context.situation_id,
                        situation_title=base_context.situation_title,
                        emergency_type=base_context.emergency_type,
                        description=base_context.description,
                        location_summary=base_context.location_summary,
                        center_latitude=base_context.center_latitude,
                        center_longitude=base_context.center_longitude,
                        report_count=base_context.report_count,
                        member_report_ids=base_context.member_report_ids,
                        officer_severity_override=base_context.officer_severity_override,
                        existing_needs=base_context.existing_needs,
                        state_fingerprint=state_fingerprint,
                        parameters={
                            "assessed_needs": assessed_needs_list,
                            "recommended_allocations": [a.model_dump() for a in recommended_allocations],
                            "effective_priority": effective_priority.value,
                            "shelter_shortfall": shelter_summary.total_shortfall if shelter_summary else 0.0,
                            "shelter_summary": shelter_summary.model_dump() if shelter_summary else {},
                            "healthcare_shortfall": healthcare_summary.total_shortfall if healthcare_summary else 0.0,
                            "healthcare_summary": healthcare_summary.model_dump() if healthcare_summary else {},
                            "volunteer_shortfall": volunteer_summary.total_shortfall if volunteer_summary else 0,
                            "volunteer_summary": volunteer_summary.model_dump() if volunteer_summary else {},
                            "transport_shortfall": route_summary.transport_shortfall if route_summary else 0,
                            "route_summary": route_summary.model_dump() if route_summary else {},
                        },
                        actor_id=actor.get("id"),
                        actor_name=actor.get("full_name"),
                        actor_role=actor.get("role"),
                    )
                    conflict_res = await self._run_and_track_agent(
                        agent, cnf_context, actor, force_refresh=force_refresh, db=db
                    )
                    agent_results[AgentName.CONFLICT_RESOLUTION_AGENT.value] = conflict_res

                    if conflict_res and conflict_res.structured_output:
                        try:
                            conflict_summary = ConflictResolutionSummary(**conflict_res.structured_output)
                            detected_conflicts = conflict_summary.conflicts_detected
                            if conflict_summary.officer_attention_required:
                                officer_attention_required = True
                            has_unresolved_conflicts = conflict_summary.unresolved_conflicts > 0

                            if conflict_summary.conflicts_count > 0:
                                await record_timeline_event(
                                    db=db,
                                    report_id=clean_sit_id,
                                    event_type=TimelineEventType.CONFLICT_DETECTED,
                                    details=f"Detected {conflict_summary.conflicts_count} coordination conflict(s) for situation {clean_sit_id}.",
                                    actor_id=actor.get("id"),
                                    actor_name=actor.get("full_name"),
                                    actor_role=actor_role_enum,
                                    metadata={"conflicts": [c.model_dump() for c in detected_conflicts]},
                                )
                                if conflict_summary.unresolved_conflicts > 0:
                                    await record_timeline_event(
                                        db=db,
                                        report_id=clean_sit_id,
                                        event_type=TimelineEventType.CONFLICT_ESCALATED,
                                        details=f"Escalated {conflict_summary.unresolved_conflicts} unresolved conflict(s) to Emergency Officer.",
                                        actor_id=actor.get("id"),
                                        actor_name=actor.get("full_name"),
                                        actor_role=actor_role_enum,
                                    )
                                else:
                                    await record_timeline_event(
                                        db=db,
                                        report_id=clean_sit_id,
                                        event_type=TimelineEventType.CONFLICT_RESOLVED,
                                        details=f"All {conflict_summary.resolved_conflicts} detected conflict(s) addressed via deterministic resolution strategies.",
                                        actor_id=actor.get("id"),
                                        actor_name=actor.get("full_name"),
                                        actor_role=actor_role_enum,
                                    )

                            await record_timeline_event(
                                db=db,
                                report_id=clean_sit_id,
                                event_type=TimelineEventType.CONFLICT_ANALYSIS_COMPLETED,
                                details=f"Conflict analysis completed ({conflict_summary.conflicts_count} conflicts evaluated).",
                                actor_id=actor.get("id"),
                                actor_name=actor.get("full_name"),
                                actor_role=actor_role_enum,
                            )
                        except Exception as parse_err:
                            logger.error(f"Error parsing conflict resolution summary: {parse_err}")

            # 6. Synthesize Unified Coordination Plan
            plan_id = f"PLN-{uuid.uuid4().hex[:8].upper()}"
            constraints_list: List[str] = [
                "All recommendations are purely advisory and strictly subject to human Emergency Officer review.",
                "No inventory quantities are decremented prior to explicit officer authorization.",
                "No shelter bed capacity or occupancy is automatically mutated during coordination.",
                "No hospital beds or ICU reservations are automatically altered without officer sign-off.",
                "No volunteer field dispatches or mission orders are transmitted without officer approval.",
                "No transport fleet or route clearances are dispatched autonomously.",
            ]

            if officer_override:
                constraints_list.append(f"Authoritative officer priority override ({officer_override.value}) preserved.")

            conflict_desc = (
                f" Evaluated {len(detected_conflicts)} coordination conflict(s) ({conflict_summary.unresolved_conflicts if conflict_summary else 0} requiring attention)."
                if detected_conflicts
                else " Zero coordination conflicts detected."
            )

            domain_summaries: List[str] = []
            if shelter_summary and shelter_summary.shelter_required:
                domain_summaries.append(
                    f"Shelter: {len(recommended_shelters)} facility(ies) covering {int(shelter_summary.total_population_covered)} evacuees"
                    f"{f' ({int(shelter_summary.total_shortfall)} shortfall)' if shelter_summary.total_shortfall > 0 else ''}"
                )
            if healthcare_summary and healthcare_summary.medical_required:
                domain_summaries.append(
                    f"Healthcare: {len(recommended_facilities)} hospital(s) covering {int(healthcare_summary.total_patients_covered)} casualties"
                    f"{f' ({int(healthcare_summary.total_shortfall)} shortfall)' if healthcare_summary.total_shortfall > 0 else ''}"
                )
            if volunteer_summary and volunteer_summary.volunteers_required:
                domain_summaries.append(
                    f"Volunteers: {len(recommended_volunteers)} responder(s) assigned"
                    f"{f' ({volunteer_summary.total_shortfall} shortfall)' if volunteer_summary.total_shortfall > 0 else ''}"
                )
            if route_summary and route_summary.transport_required:
                domain_summaries.append(
                    f"Transport: {len(recommended_transports)} vehicle(s), {len(recommended_routes)} route(s)"
                    f"{f' ({route_summary.transport_shortfall} shortfall)' if route_summary.transport_shortfall > 0 else ''}"
                )

            domain_desc = f" ({'; '.join(domain_summaries)})." if domain_summaries else "."

            plan_reasoning = (
                f"Orchestrated complete 8-agent response pipeline for {base_context.emergency_type} with "
                f"{effective_priority.value} priority. Evaluated {len(assessed_needs_list)} need items "
                f"and matched {len(recommended_allocations)} inventory allocations across regional depots."
                f"{domain_desc}{conflict_desc}"
            )

            avg_confidence = 0.92
            conf_scores = [r.confidence for r in agent_results.values() if r.confidence]
            if conf_scores:
                avg_confidence = sum(conf_scores) / len(conf_scores)

            coordination_plan = CoordinationPlan(
                plan_id=plan_id,
                situation_id=clean_sit_id,
                version=next_version,
                state_fingerprint=state_fingerprint,
                generated_at=datetime.now(timezone.utc),
                participating_agents=required_agents,
                agent_results=agent_results,
                assessed_priority=effective_priority,
                assessed_needs=assessed_needs_list,
                recommended_allocations=recommended_allocations,
                conflicts=detected_conflicts,
                conflict_summary=conflict_summary,
                recommended_shelters=recommended_shelters,
                shelter_summary=shelter_summary,
                recommended_facilities=recommended_facilities,
                healthcare_summary=healthcare_summary,
                recommended_volunteers=recommended_volunteers,
                volunteer_summary=volunteer_summary,
                recommended_transports=recommended_transports,
                recommended_routes=recommended_routes,
                route_summary=route_summary,
                officer_attention_required=officer_attention_required,
                has_unresolved_conflicts=has_unresolved_conflicts,
                reasoning=plan_reasoning,
                constraints=constraints_list,
                confidence=round(avg_confidence, 2),
                status=CoordinationPlanStatus.PENDING_OFFICER_REVIEW,
                officer_review=None,
            )

            # 7. Persist Coordination Plan to MongoDB Atlas with DuplicateKey safety
            plan_dict = coordination_plan.model_dump()
            plan_dict["generated_at"] = plan_dict["generated_at"].isoformat()
            if plan_dict.get("conflict_summary") and plan_dict["conflict_summary"].get("generated_at"):
                plan_dict["conflict_summary"]["generated_at"] = plan_dict["conflict_summary"]["generated_at"].isoformat()
            if plan_dict.get("shelter_summary") and plan_dict["shelter_summary"].get("generated_at"):
                plan_dict["shelter_summary"]["generated_at"] = plan_dict["shelter_summary"]["generated_at"].isoformat()
            if plan_dict.get("healthcare_summary") and plan_dict["healthcare_summary"].get("generated_at"):
                plan_dict["healthcare_summary"]["generated_at"] = plan_dict["healthcare_summary"]["generated_at"].isoformat()
            if plan_dict.get("volunteer_summary") and plan_dict["volunteer_summary"].get("generated_at"):
                plan_dict["volunteer_summary"]["generated_at"] = plan_dict["volunteer_summary"]["generated_at"].isoformat()
            if plan_dict.get("route_summary") and plan_dict["route_summary"].get("generated_at"):
                plan_dict["route_summary"]["generated_at"] = plan_dict["route_summary"]["generated_at"].isoformat()

            try:
                await db["coordination_plans"].insert_one(plan_dict)
            except (DuplicateKeyError, PyMongoError) as e:
                logger.warning(
                    f"Duplicate key conflict on inserting coordination plan {plan_id} for situation {clean_sit_id}: {e}. "
                    f"Retrieving active plan."
                )
                existing_winner = await db["coordination_plans"].find_one({
                    "situation_id": clean_sit_id,
                    "status": CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
                    "state_fingerprint": state_fingerprint,
                }, sort=[("generated_at", -1)])
                if existing_winner:
                    return CoordinationPlan(**existing_winner)
                raise

            # 8. Record Timeline Audit Event
            await record_timeline_event(
                db=db,
                report_id=clean_sit_id,
                event_type=TimelineEventType.COORDINATION_PLAN_GENERATED,
                details=f"Coordination Plan {plan_id} (v{next_version}) generated across 8 agents for situation {clean_sit_id} ({effective_priority.value}).",
                actor_id=actor.get("id"),
                actor_name=actor.get("full_name"),
                actor_role=actor_role_enum,
            )

            return coordination_plan

    async def _run_and_track_agent(
        self,
        agent,
        context: AgentContext,
        actor: Dict[str, Any],
        force_refresh: bool = False,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> AgentResult:
        """
        Executes a single agent, tracks start/completion, and persists the record to ai_agent_runs.
        Reuses recent matching completed agent runs for the same situation state fingerprint.
        """
        if db is None:
            db = db_manager.db
        agent_name = agent.name
        clean_sit_id = context.situation_id

        # Check for reusable completed agent run for the same situation fingerprint
        if not force_refresh and context.state_fingerprint:
            existing_run = await db["ai_agent_runs"].find_one({
                "situation_id": clean_sit_id,
                "agent_name": agent_name.value if hasattr(agent_name, "value") else str(agent_name),
                "state_fingerprint": context.state_fingerprint,
                "status": AgentRunStatus.COMPLETED.value,
            }, sort=[("started_at", -1)])

            if existing_run and existing_run.get("result"):
                logger.info(
                    f"Reusing cached agent run {existing_run.get('run_id')} for agent "
                    f"{agent_name.value} on situation {clean_sit_id}"
                )
                res_data = existing_run["result"]
                return AgentResult(**res_data)

        started_at = datetime.now(timezone.utc)

        actor_role_enum = None
        if actor.get("role"):
            try:
                actor_role_enum = UserRole(actor.get("role"))
            except Exception:
                pass

        try:
            result = await agent.execute(context)
            completed_at = datetime.now(timezone.utc)

            # Persist run record to MongoDB Atlas
            run_record = AgentRunRecord(
                run_id=result.run_id,
                situation_id=context.situation_id,
                agent_name=agent_name,
                agent_version="1.0.0",
                status=result.status,
                state_fingerprint=context.state_fingerprint,
                started_at=started_at,
                completed_at=completed_at,
                input_summary={
                    "emergency_type": context.emergency_type,
                    "report_count": context.report_count,
                    "officer_override": context.officer_severity_override.value if context.officer_severity_override else None,
                },
                result=result,
                confidence=result.confidence,
                warnings=result.warnings,
                error=None,
                actor_id=actor.get("id"),
                actor_name=actor.get("full_name"),
            )

            record_dict = run_record.model_dump()
            record_dict["started_at"] = record_dict["started_at"].isoformat()
            if record_dict["completed_at"]:
                record_dict["completed_at"] = record_dict["completed_at"].isoformat()
            if record_dict["result"] and record_dict["result"]["generated_at"]:
                record_dict["result"]["generated_at"] = record_dict["result"]["generated_at"].isoformat()

            await db["ai_agent_runs"].insert_one(record_dict)

            # Record Agent Completed Event
            await record_timeline_event(
                db=db,
                report_id=context.situation_id,
                event_type=TimelineEventType.AGENT_RUN_COMPLETED,
                details=f"Agent '{agent_name.value}' completed execution with status {result.status.value}.",
                actor_id=actor.get("id"),
                actor_name=actor.get("full_name"),
                actor_role=actor_role_enum,
            )

            return result

        except Exception as e:
            logger.error(f"Agent {agent_name.value} failed with uncaught exception: {e}")
            completed_at = datetime.now(timezone.utc)
            run_id = f"RUN-ERR-{uuid.uuid4().hex[:8].upper()}"

            fallback_result = AgentResult(
                agent_name=agent_name,
                run_id=run_id,
                status=AgentRunStatus.FAILED,
                recommendation=f"Agent '{agent_name.value}' encountered internal failure.",
                structured_output={},
                confidence=0.0,
                evidence=[],
                warnings=[f"Execution failed: {str(e)}"],
                constraints=[],
                generated_at=completed_at,
            )

            await record_timeline_event(
                db=db,
                report_id=context.situation_id,
                event_type=TimelineEventType.AGENT_RUN_FAILED,
                details=f"Agent '{agent_name.value}' failed execution: {str(e)}.",
                actor_id=actor.get("id"),
                actor_name=actor.get("full_name"),
                actor_role=actor_role_enum,
            )

            return fallback_result

    async def review_coordination_plan(
        self,
        plan_id: str,
        action: PlanReviewAction,
        actor: Dict[str, Any],
        notes: Optional[str] = None,
        modified_needs: Optional[List[Dict[str, Any]]] = None,
        modified_allocations: Optional[List[PlanRecommendedResource]] = None,
        modified_shelters: Optional[List[RecommendedShelter]] = None,
        modified_facilities: Optional[List[RecommendedHealthcareFacility]] = None,
        modified_volunteers: Optional[List[RecommendedVolunteerAssignment]] = None,
        modified_transports: Optional[List[RecommendedTransport]] = None,
        modified_routes: Optional[List[RecommendedRoute]] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> CoordinationPlan:
        """
        Handles authenticated Emergency Officer human-in-the-loop review of a Coordination Plan.
        Transitions state from PENDING_OFFICER_REVIEW to ACTIVE (if APPROVED), MODIFIED, or REJECTED.
        Enforces server-side validation against authoritative inventory and shelter/hospital capacities,
        stale-plan protection, and persists full audit trail across all modified domain components.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        plan_data = await db["coordination_plans"].find_one({"plan_id": plan_id})
        if not plan_data:
            raise ValueError(f"Coordination Plan {plan_id} not found.")

        current_status = plan_data.get("status")
        if current_status not in [
            CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
            CoordinationPlanStatus.DRAFT.value,
            CoordinationPlanStatus.MODIFIED.value,
        ]:
            raise ValueError(f"Coordination Plan {plan_id} has already been reviewed ({current_status}).")

        # Stale-Plan Protection Check for approvals/modifications
        if action in [PlanReviewAction.APPROVE, PlanReviewAction.MODIFY]:
            try:
                from app.services.monitoring.plan_activation_service import PlanActivationService
                plan_model_pre = CoordinationPlan(**plan_data)
                is_stale, stale_reason = await PlanActivationService.is_plan_stale(plan_model_pre, db)
                if is_stale:
                    raise ValueError(f"STALE_PLAN_DETECTED: Response plan is no longer current ({stale_reason}). Please refresh and review latest plan.")
            except ValueError:
                raise
            except Exception as stale_err:
                logger.warning(f"Notice on stale-plan check during review for {plan_id}: {stale_err}")

        new_status = CoordinationPlanStatus.ACTIVE if action == PlanReviewAction.APPROVE else (
            CoordinationPlanStatus.MODIFIED if action == PlanReviewAction.MODIFY else CoordinationPlanStatus.REJECTED
        )

        diff_summary: Dict[str, Any] = {
            "allocations_changed": 0,
            "shelters_changed": 0,
            "facilities_changed": 0,
            "volunteers_changed": 0,
            "transports_changed": 0,
            "changes": [],
        }

        # 1. Server-side validation of officer modified resource allocations against real inventory
        if modified_allocations is not None:
            orig_allocs = {a.get("resource_type"): a for a in plan_data.get("recommended_allocations", [])}
            for alloc in modified_allocations:
                qty = float(alloc.allocated_quantity if alloc.allocated_quantity is not None else 0.0)
                r_name = alloc.resource_type.value if hasattr(alloc.resource_type, "value") else str(alloc.resource_type)
                if qty < 0:
                    raise ValueError(f"Invalid modification: Allocated quantity cannot be negative for {r_name}.")

                # Track diff
                orig_item = orig_allocs.get(alloc.resource_type) or orig_allocs.get(r_name)
                orig_qty = float(orig_item.get("allocated_quantity", orig_item.get("quantity_required", 0))) if orig_item else 0.0
                if abs(qty - orig_qty) > 0.001:
                    diff_summary["allocations_changed"] += 1
                    diff_summary["changes"].append({
                        "domain": "RESOURCE_ALLOCATION",
                        "resource_type": r_name,
                        "original_allocated": orig_qty,
                        "officer_allocated": qty,
                        "unit": alloc.unit,
                        "depot": alloc.matched_resource_name or alloc.depot_location,
                    })

                # If matched to a specific depot, validate stock availability
                if alloc.matched_resource_id:
                    res_doc = await db["resources"].find_one({
                        "$or": [
                            {"resource_id": alloc.matched_resource_id},
                            {"_id": alloc.matched_resource_id},
                        ]
                    })
                    if res_doc:
                        avail = float(res_doc.get("quantity_available") if res_doc.get("quantity_available") is not None else res_doc.get("quantity_total", 0.0))
                        if qty > avail:
                            depot_name = res_doc.get("name") or alloc.matched_resource_name or alloc.matched_resource_id
                            raise ValueError(
                                f"Modification error: Allocated quantity ({qty:g} {alloc.unit}) exceeds available stock "
                                f"({avail:g} {alloc.unit}) at depot '{depot_name}' for {r_name}."
                            )

        # 2. Server-side validation of officer modified shelters against real capacity
        if modified_shelters is not None:
            orig_shelters = {s.get("shelter_id") or s.get("shelter_name"): s for s in plan_data.get("recommended_shelters", [])}
            for sh in modified_shelters:
                occ = float(sh.recommended_occupancy if sh.recommended_occupancy is not None else 0.0)
                if occ < 0:
                    raise ValueError(f"Invalid modification: Recommended occupancy cannot be negative for shelter '{sh.shelter_name}'.")

                sh_key = sh.shelter_id or sh.shelter_name
                orig_sh = orig_shelters.get(sh_key)
                orig_occ = float(orig_sh.get("recommended_occupancy", 0)) if orig_sh else 0.0
                if abs(occ - orig_occ) > 0.001:
                    diff_summary["shelters_changed"] += 1
                    diff_summary["changes"].append({
                        "domain": "SHELTER",
                        "shelter_name": sh.shelter_name,
                        "original_occupancy": orig_occ,
                        "officer_occupancy": occ,
                    })

                if sh.shelter_id:
                    sh_doc = await db["shelters"].find_one({
                        "$or": [
                            {"shelter_id": sh.shelter_id},
                            {"_id": sh.shelter_id},
                        ]
                    })
                    if sh_doc:
                        cap = float(sh_doc.get("capacity", 0))
                        curr_occ = float(sh_doc.get("current_occupancy", 0))
                        remaining = max(0.0, cap - curr_occ)
                        if occ > remaining and remaining > 0:
                            raise ValueError(
                                f"Modification error: Shelter '{sh.shelter_name}' requested occupancy ({occ:g}) "
                                f"exceeds remaining capacity ({remaining:g})."
                            )

        # 3. Server-side validation of officer modified healthcare facilities against real bed capacity
        if modified_facilities is not None:
            orig_facs = {f.get("facility_id") or f.get("facility_name"): f for f in plan_data.get("recommended_facilities", [])}
            for fac in modified_facilities:
                pts = float(fac.allocated_patients if fac.allocated_patients is not None else 0.0)
                if pts < 0:
                    raise ValueError(f"Invalid modification: Allocated casualties cannot be negative for hospital '{fac.facility_name}'.")

                f_key = fac.facility_id or fac.facility_name
                orig_f = orig_facs.get(f_key)
                orig_pts = float(orig_f.get("allocated_patients", 0)) if orig_f else 0.0
                if abs(pts - orig_pts) > 0.001:
                    diff_summary["facilities_changed"] += 1
                    diff_summary["changes"].append({
                        "domain": "HEALTHCARE",
                        "facility_name": fac.facility_name,
                        "original_patients": orig_pts,
                        "officer_patients": pts,
                    })

                if fac.facility_id:
                    fac_doc = await db["healthcare_facilities"].find_one({
                        "$or": [
                            {"facility_id": fac.facility_id},
                            {"_id": fac.facility_id},
                        ]
                    })
                    if not fac_doc:
                        fac_doc = await db["facilities"].find_one({
                            "$or": [
                                {"facility_id": fac.facility_id},
                                {"_id": fac.facility_id},
                            ]
                        })
                    if fac_doc:
                        beds = float(fac_doc.get("available_beds") or fac_doc.get("capacity", 0))
                        if pts > beds and beds > 0:
                            raise ValueError(
                                f"Modification error: Hospital '{fac.facility_name}' allocated casualties ({pts:g}) "
                                f"exceeds available beds ({beds:g})."
                            )

        # 4. Server-side validation of officer modified volunteers
        if modified_volunteers is not None:
            orig_vols = {v.get("assignment_id") or v.get("volunteer_name"): v for v in plan_data.get("recommended_volunteers", [])}
            for vol in modified_volunteers:
                cnt = int(vol.assigned_count if vol.assigned_count is not None else 0)
                if cnt < 0:
                    raise ValueError(f"Invalid modification: Assigned responder count cannot be negative for '{vol.volunteer_name}'.")

                v_key = vol.assignment_id or vol.volunteer_name
                orig_v = orig_vols.get(v_key)
                orig_cnt = int(orig_v.get("assigned_count", 0)) if orig_v else 0
                if cnt != orig_cnt:
                    diff_summary["volunteers_changed"] += 1
                    diff_summary["changes"].append({
                        "domain": "VOLUNTEERS",
                        "volunteer_name": vol.volunteer_name,
                        "original_count": orig_cnt,
                        "officer_count": cnt,
                    })

        # 5. Server-side validation of transports
        if modified_transports is not None:
            diff_summary["transports_changed"] = len(modified_transports)

        mod_dict = {}
        if modified_needs is not None:
            mod_dict["needs"] = modified_needs
        if modified_allocations is not None:
            mod_dict["allocations"] = [a.model_dump() for a in modified_allocations]
        if modified_shelters is not None:
            mod_dict["shelters"] = [s.model_dump() for s in modified_shelters]
        if modified_facilities is not None:
            mod_dict["facilities"] = [f.model_dump() for f in modified_facilities]
        if modified_volunteers is not None:
            mod_dict["volunteers"] = [v.model_dump() for v in modified_volunteers]
        if modified_transports is not None:
            mod_dict["transports"] = [t.model_dump() for t in modified_transports]
        if modified_routes is not None:
            mod_dict["routes"] = [r.model_dump() for r in modified_routes]

        officer_review = OfficerPlanReview(
            decision=action,
            reviewed_by_id=actor["id"],
            reviewed_by_name=actor["full_name"],
            reviewed_by_role=actor["role"],
            reviewed_at=datetime.now(timezone.utc),
            officer_notes=notes,
            modified_fields=mod_dict if mod_dict else None,
        )

        update_fields: Dict[str, Any] = {
            "status": new_status.value,
            "officer_review": {
                "decision": officer_review.decision.value,
                "reviewed_by_id": officer_review.reviewed_by_id,
                "reviewed_by_name": officer_review.reviewed_by_name,
                "reviewed_by_role": officer_review.reviewed_by_role,
                "reviewed_at": officer_review.reviewed_at.isoformat(),
                "officer_notes": officer_review.officer_notes,
                "modified_fields": officer_review.modified_fields,
            },
            "diff_summary": diff_summary,
        }

        # Keep authoritative needs intact (separation of need vs fulfillment) unless explicitly passed
        if modified_needs is not None:
            update_fields["assessed_needs"] = modified_needs
        if modified_allocations is not None:
            update_fields["recommended_allocations"] = [a.model_dump() for a in modified_allocations]
        if modified_shelters is not None:
            update_fields["recommended_shelters"] = [s.model_dump() for s in modified_shelters]
        if modified_facilities is not None:
            update_fields["recommended_facilities"] = [f.model_dump() for f in modified_facilities]
        if modified_volunteers is not None:
            update_fields["recommended_volunteers"] = [v.model_dump() for v in modified_volunteers]
        if modified_transports is not None:
            update_fields["recommended_transports"] = [t.model_dump() for t in modified_transports]
        if modified_routes is not None:
            update_fields["recommended_routes"] = [r.model_dump() for r in modified_routes]

        await db["coordination_plans"].update_one(
            {"plan_id": plan_id},
            {"$set": update_fields}
        )

        # Record Timeline Audit Event for Officer Review Action
        actor_role_enum = None
        if actor.get("role"):
            try:
                actor_role_enum = UserRole(actor.get("role"))
            except Exception:
                pass

        sit_id_clean = plan_data.get("situation_id", "").strip().upper()
        if sit_id_clean:
            ev_type = TimelineEventType.ACTIVE_RESPONSE_PLAN_APPROVED if action == PlanReviewAction.APPROVE else (
                TimelineEventType.ACTIVE_RESPONSE_PLAN_MODIFIED if action == PlanReviewAction.MODIFY else TimelineEventType.ACTIVE_RESPONSE_PLAN_REJECTED
            )
            await record_timeline_event(
                db=db,
                report_id=sit_id_clean,
                event_type=ev_type,
                details=f"Coordination Plan {plan_id} {action.value} by Emergency Officer {actor.get('full_name')}." + (f" Notes: {notes}" if notes else ""),
                actor_id=actor.get("id"),
                actor_name=actor.get("full_name"),
                actor_role=actor_role_enum,
                metadata={
                    "plan_id": plan_id,
                    "action": action.value,
                    "modified_fields": list(mod_dict.keys()) if mod_dict else [],
                    "diff_summary": diff_summary,
                },
            )

        # If approved, supersede any previous active plans for this situation
        if action == PlanReviewAction.APPROVE or new_status == CoordinationPlanStatus.ACTIVE:
            sit_id = plan_data.get("situation_id", "").strip().upper()
            if sit_id:
                await db["coordination_plans"].update_many(
                    {
                        "situation_id": sit_id,
                        "plan_id": {"$ne": plan_id},
                        "status": {"$in": [CoordinationPlanStatus.ACTIVE.value, CoordinationPlanStatus.APPROVED.value]},
                    },
                    {"$set": {"status": CoordinationPlanStatus.SUPERSEDED.value}}
                )

        # Record generic audit event
        await record_timeline_event(
            db=db,
            report_id=plan_data.get("situation_id", plan_id),
            event_type=TimelineEventType.COORDINATION_PLAN_REVIEWED,
            details=f"Coordination Plan {plan_id} {new_status.value} by Emergency Officer {actor['full_name']}.",
            actor_id=actor["id"],
            actor_name=actor["full_name"],
            actor_role=actor_role_enum,
        )

        updated_plan_doc = await db["coordination_plans"].find_one({"plan_id": plan_id})
        updated_plan = CoordinationPlan(**updated_plan_doc)

        # Phase 8: Derive executable response tasks only if plan was approved into ACTIVE state
        if action == PlanReviewAction.APPROVE or new_status == CoordinationPlanStatus.ACTIVE:
            try:
                from app.services.field_operations_service import FieldOperationsService
                await FieldOperationsService.derive_tasks_from_plan(
                    plan=updated_plan,
                    officer_actor=actor,
                    db=db,
                )
            except Exception as derive_err:
                logger.warning(f"Error deriving response tasks on plan review approval {plan_id}: {derive_err}")

        return updated_plan


# Global Singleton Instance
central_orchestrator = CentralOrchestrator()
