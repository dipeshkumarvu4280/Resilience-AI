import uuid
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.enums import (
    AgentName,
    AgentRunStatus,
    CoordinationPlanStatus,
    ImpactLevel,
    PlanValidityStatus,
    OperationalDomain,
    TimelineEventType,
    UserRole,
    DiffChangeType,
    SeverityLevel,
)
from app.models.agent import (
    AgentContext,
    AgentResult,
    AgentRunRecord,
    CoordinationPlan,
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
from app.models.monitoring import (
    MonitoringEvent,
    ChangeImpactResult,
    PlanComponentDiffItem,
    PlanDiffResult,
    ReplanningTriggerMetadata,
)
from app.services.agents.registry import agent_registry
from app.services.agents.orchestrator import central_orchestrator, compute_situation_state_fingerprint
from app.services.timeline import record_timeline_event
from app.db.mongodb import db_manager

logger = logging.getLogger("resilience.services.monitoring.replanning")

# Complete Topological Order of Foundational Agents
TOPOLOGICAL_AGENT_ORDER: List[AgentName] = [
    AgentName.PRIORITY_AGENT,
    AgentName.NEEDS_AGENT,
    AgentName.RESOURCE_COORDINATION_AGENT,
    AgentName.SHELTER_AGENT,
    AgentName.HEALTHCARE_AGENT,
    AgentName.VOLUNTEER_AGENT,
    AgentName.ROUTE_AGENT,
    AgentName.CONFLICT_RESOLUTION_AGENT,
]


def compute_replanning_fingerprint(
    situation_id: str,
    previous_plan_id: str,
    previous_plan_version: int,
    trigger_event_fingerprint: str,
    affected_agents: List[str],
) -> str:
    """
    Computes a canonical SHA-256 fingerprint for a re-planning attempt to enforce idempotency.
    """
    payload = {
        "situation_id": str(situation_id).strip().upper(),
        "previous_plan_id": str(previous_plan_id).strip(),
        "previous_version": int(previous_plan_version),
        "event_fp": str(trigger_event_fingerprint).strip(),
        "affected_agents": sorted([str(a) for a in affected_agents]),
    }
    canonical_json = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]


class DynamicReplanningService:
    """
    Phase 6.3 Impact-Aware Dynamic Re-Planning Engine.
    Executes selective agent re-planning strictly for affected domains, preserves unaffected
    plan components, generates deterministic plan diffs, creates immutable plan versions in
    PENDING_OFFICER_REVIEW, and guarantees non-autonomous plan activation.
    """

    @classmethod
    def evaluate_material_change(
        cls,
        impact: ChangeImpactResult,
        active_plan: Optional[CoordinationPlan],
    ) -> bool:
        """
        Evaluates whether a detected impact materially breaches constraints, creates shortfalls,
        or invalidates the active plan, requiring a revised plan version.
        """
        if active_plan is None:
            return False

        # Invalidation or explicit officer attention required
        if impact.plan_status in [PlanValidityStatus.INVALIDATED, PlanValidityStatus.REQUIRES_OFFICER_REVIEW]:
            return True

        # High or Critical impact severity
        if impact.impact_level in [ImpactLevel.CRITICAL, ImpactLevel.HIGH]:
            return True

        # Detected shortfalls or constraint violations
        if impact.shortfalls and any(v > 0 for v in impact.shortfalls.values()):
            return True

        if impact.violated_constraints and len(impact.violated_constraints) > 0:
            return True

        # Situation severity change
        if OperationalDomain.SITUATION in impact.affected_domains:
            return True

        return False

    @classmethod
    def resolve_selective_execution_set(
        cls,
        affected_agents: List[AgentName],
    ) -> List[AgentName]:
        """
        Derives the minimum required sequence of agents to execute based on topological order
        and downstream dependency propagation.
        """
        if not affected_agents:
            return []

        # Find earliest affected index in topological order
        min_idx = len(TOPOLOGICAL_AGENT_ORDER)
        for agent in affected_agents:
            if agent in TOPOLOGICAL_AGENT_ORDER:
                idx = TOPOLOGICAL_AGENT_ORDER.index(agent)
                if idx < min_idx:
                    min_idx = idx

        if min_idx >= len(TOPOLOGICAL_AGENT_ORDER):
            return [AgentName.CONFLICT_RESOLUTION_AGENT]

        # If NeedsAgent is affected, all downstream agents must re-run
        if TOPOLOGICAL_AGENT_ORDER[min_idx] == AgentName.NEEDS_AGENT or TOPOLOGICAL_AGENT_ORDER[min_idx] == AgentName.PRIORITY_AGENT:
            return TOPOLOGICAL_AGENT_ORDER[min_idx:]

        # For specific domain changes (e.g. Shelter, Resource, Healthcare, Volunteer, Route),
        # include the domain agent + ConflictResolutionAgent, plus any explicitly listed dependents
        execution_set: List[AgentName] = []
        for agent in TOPOLOGICAL_AGENT_ORDER:
            if agent in affected_agents:
                execution_set.append(agent)

        # ConflictResolutionAgent must always run if any domain changes to reconcile cross-domain constraints
        if AgentName.CONFLICT_RESOLUTION_AGENT not in execution_set:
            execution_set.append(AgentName.CONFLICT_RESOLUTION_AGENT)

        return execution_set

    @classmethod
    async def replan_from_impact(
        cls,
        impact: ChangeImpactResult,
        event: Optional[MonitoringEvent] = None,
        actor: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> Optional[CoordinationPlan]:
        """
        Executes impact-aware dynamic re-planning.
        Returns the newly synthesized revised CoordinationPlan (status: PENDING_OFFICER_REVIEW),
        or an existing matching revised plan if idempotent.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            logger.error("Database connection unavailable for re-planning.")
            return None

        if actor is None:
            actor = {"id": "SYSTEM_REPLANNING_ENGINE", "full_name": "Resilience Re-Planning Service", "role": "SYSTEM"}

        sit_id = impact.situation_id
        if not sit_id and event:
            sit_id = event.situation_id

        if not sit_id:
            logger.warning(f"Re-planning skipped: No situation_id associated with impact {impact.impact_id}.")
            return None

        clean_sit_id = str(sit_id).strip().upper()

        # 1. Fetch current Situation from MongoDB
        situation_data = await db["situations"].find_one({"situation_id": clean_sit_id})
        if not situation_data:
            situation_data = await db["situations"].find_one({"_id": clean_sit_id})
        if not situation_data:
            logger.warning(f"Re-planning skipped: Situation {clean_sit_id} not found.")
            return None

        # 2. Fetch current Active / Approved Coordination Plan
        active_plan_data = None
        if impact.coordination_plan_id:
            active_plan_data = await db["coordination_plans"].find_one({"plan_id": impact.coordination_plan_id})

        if not active_plan_data:
            active_plan_data = await db["coordination_plans"].find_one(
                {"situation_id": clean_sit_id, "status": {"$in": [CoordinationPlanStatus.APPROVED.value, CoordinationPlanStatus.ACTIVE.value]}},
                sort=[("version", -1)]
            )

        if not active_plan_data:
            # Fallback to most recent plan regardless of status for reference
            active_plan_data = await db["coordination_plans"].find_one(
                {"situation_id": clean_sit_id},
                sort=[("version", -1)]
            )

        if not active_plan_data:
            logger.warning(f"Re-planning skipped: No base coordination plan found for situation {clean_sit_id}.")
            return None

        active_plan = CoordinationPlan(**active_plan_data)

        # 3. Material Change Check
        is_material = cls.evaluate_material_change(impact, active_plan)
        if not is_material:
            logger.info(f"Re-planning not required for impact {impact.impact_id} (non-material delta).")
            return active_plan

        # 4. Idempotency Check
        event_fp = event.event_fingerprint if event else impact.impact_id
        affected_agents_enum = [AgentName(a) if isinstance(a, str) else a for a in impact.affected_agents]
        selective_agents = cls.resolve_selective_execution_set(affected_agents_enum)

        replan_fp = compute_replanning_fingerprint(
            situation_id=clean_sit_id,
            previous_plan_id=active_plan.plan_id,
            previous_plan_version=active_plan.version,
            trigger_event_fingerprint=event_fp,
            affected_agents=[a.value for a in selective_agents],
        )

        # Check if an identical revised plan is already in PENDING_OFFICER_REVIEW
        existing_revised_plan = await db["coordination_plans"].find_one({
            "situation_id": clean_sit_id,
            "previous_plan_id": active_plan.plan_id,
            "state_fingerprint": replan_fp,
            "status": CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
        })

        if existing_revised_plan:
            logger.info(
                f"Idempotency hit: Returning existing revised plan {existing_revised_plan.get('plan_id')} "
                f"for situation {clean_sit_id}."
            )
            return CoordinationPlan(**existing_revised_plan)

        # 5. Record Re-Planning Started Timeline Event
        actor_role_enum = None
        if actor.get("role"):
            try:
                actor_role_enum = UserRole(actor.get("role"))
            except Exception:
                pass

        await record_timeline_event(
            db=db,
            report_id=clean_sit_id,
            event_type=TimelineEventType.REPLANNING_STARTED,
            details=f"Dynamic Re-Planning initiated for Situation {clean_sit_id} (Trigger: {impact.changed_entity}).",
            actor_id=actor.get("id"),
            actor_name=actor.get("full_name"),
            actor_role=actor_role_enum,
            metadata={
                "trigger_event_id": impact.event_id,
                "impact_id": impact.impact_id,
                "previous_plan_id": active_plan.plan_id,
                "previous_version": active_plan.version,
                "affected_agents": [a.value for a in selective_agents],
            },
        )

        # 6. Execute Selective Agents and Preserve Unaffected Outputs
        # Start from base active plan outputs
        assessed_priority = active_plan.assessed_priority
        assessed_needs = list(active_plan.assessed_needs)

        if not assessed_needs:
            m_ids = situation_data.get("report_ids", [])
            q_ids = [clean_sit_id] + [str(r).strip().upper() for r in m_ids if r]
            a_cursor = db["needs_assessments"].find({
                "$or": [
                    {"situation_id": {"$in": q_ids}},
                    {"report_id": {"$in": q_ids}},
                ]
            })
            a_docs = await a_cursor.to_list(length=100)
            for doc in a_docs:
                for n in doc.get("needs", []):
                    n_d = dict(n) if isinstance(n, dict) else n.model_dump()
                    n_d.setdefault("source", "OFFICER_NEEDS_ASSESSMENT")
                    n_d.setdefault("officer_assessed", True)
                    n_d.setdefault("ai_inferred", False)
                    assessed_needs.append(n_d)

        recommended_allocations = list(active_plan.recommended_allocations)
        recommended_shelters = list(active_plan.recommended_shelters)
        shelter_summary = active_plan.shelter_summary
        recommended_facilities = list(active_plan.recommended_facilities)
        healthcare_summary = active_plan.healthcare_summary
        recommended_volunteers = list(active_plan.recommended_volunteers)
        volunteer_summary = active_plan.volunteer_summary
        recommended_transports = list(active_plan.recommended_transports)
        recommended_routes = list(active_plan.recommended_routes)
        route_summary = active_plan.route_summary
        conflicts = list(active_plan.conflicts)
        conflict_summary = active_plan.conflict_summary
        agent_results: Dict[str, AgentResult] = dict(active_plan.agent_results)
        participating_agents: List[AgentName] = list(active_plan.participating_agents)

        # Prepare execution context
        override_sev_str = situation_data.get("officer_override_severity") or situation_data.get("officer_severity_override")
        override_sev = SeverityLevel(override_sev_str) if override_sev_str else None

        base_context = AgentContext(
            situation_id=clean_sit_id,
            situation_title=situation_data.get("title", f"Emergency Situation {clean_sit_id}"),
            emergency_type=situation_data.get("emergency_type", "OTHER"),
            description=situation_data.get("description", ""),
            location_summary=situation_data.get("location_name", "Incident Location"),
            center_latitude=situation_data.get("center_location", {}).get("latitude", 0.0),
            center_longitude=situation_data.get("center_location", {}).get("longitude", 0.0),
            report_count=len(situation_data.get("report_ids", [])),
            member_report_ids=situation_data.get("report_ids", []),
            officer_severity_override=override_sev,
            existing_needs=assessed_needs,
            state_fingerprint=replan_fp,
            parameters={},
            actor_id=actor.get("id"),
            actor_name=actor.get("full_name"),
            actor_role=actor.get("role"),
        )

        # Execute Selective Agents in Topological Sequence
        for agent_name in selective_agents:
            agent = agent_registry.get(agent_name)
            if not agent:
                logger.warning(f"Registered adapter for {agent_name.value} not found, skipping.")
                continue

            await record_timeline_event(
                db=db,
                report_id=clean_sit_id,
                event_type=TimelineEventType.AFFECTED_AGENT_EXECUTION_STARTED,
                details=f"Re-executing affected agent '{agent_name.value}' with fresh operational state.",
                actor_id=actor.get("id"),
                actor_name=actor.get("full_name"),
                actor_role=actor_role_enum,
            )

            # Build fresh agent-specific context
            if agent_name == AgentName.PRIORITY_AGENT:
                ctx = base_context
                res = await central_orchestrator._run_and_track_agent(agent, ctx, actor, force_refresh=True, db=db)
                agent_results[agent_name.value] = res
                if res and res.structured_output:
                    p_str = res.structured_output.get("effective_priority")
                    if p_str:
                        try:
                            assessed_priority = SeverityLevel(p_str)
                        except Exception:
                            pass

            elif agent_name == AgentName.NEEDS_AGENT:
                ctx = AgentContext(
                    **base_context.model_dump(exclude={"parameters"}),
                    parameters={"effective_priority": assessed_priority.value},
                )
                res = await central_orchestrator._run_and_track_agent(agent, ctx, actor, force_refresh=True, db=db)
                agent_results[agent_name.value] = res
                if res and res.structured_output:
                    assessed_needs = res.structured_output.get("needs", assessed_needs)

            elif agent_name == AgentName.RESOURCE_COORDINATION_AGENT:
                res_cursor = db["resources"].find({
                    "status": {"$in": ["AVAILABLE", "PARTIALLY_AVAILABLE", "OPERATIONAL", "Operational", "ACTIVE", "Active"]},
                    "quantity_available": {"$gt": 0},
                })
                db_resources = await res_cursor.to_list(length=200)
                ctx = AgentContext(
                    **base_context.model_dump(exclude={"parameters"}),
                    parameters={
                        "assessed_needs": assessed_needs,
                        "effective_priority": assessed_priority.value,
                        "available_resources": db_resources,
                    },
                )
                res = await central_orchestrator._run_and_track_agent(agent, ctx, actor, force_refresh=True, db=db)
                agent_results[agent_name.value] = res
                if res and res.structured_output:
                    raw_allocs = (
                        res.structured_output.get("matches")
                        or res.structured_output.get("recommended_allocations")
                        or []
                    )
                    recommended_allocations = []
                    for a in raw_allocs:
                        if isinstance(a, PlanRecommendedResource):
                            recommended_allocations.append(a)
                        elif isinstance(a, dict):
                            r_type = a.get("resource_type")
                            u_val = a.get("urgency")
                            recommended_allocations.append(PlanRecommendedResource(
                                resource_type=ResourceType(r_type) if isinstance(r_type, str) else r_type,
                                quantity_required=float(a.get("quantity_required") or a.get("quantity") or 1.0),
                                unit=a.get("unit", "Units"),
                                urgency=NeedUrgency(u_val) if isinstance(u_val, str) else (u_val or NeedUrgency.HIGH),
                                matched_resource_id=a.get("matched_resource_id"),
                                matched_resource_name=a.get("matched_resource_name"),
                                available_in_inventory=float(a.get("available_in_inventory") or 0.0),
                                allocated_quantity=float(a.get("allocated_quantity") or 0.0),
                                depot_location=a.get("depot_location"),
                                distance_km=a.get("distance_km"),
                                reasoning=a.get("reasoning", "Recommended regional depot match."),
                            ))

            elif agent_name == AgentName.SHELTER_AGENT:
                shelter_cursor = db["resources"].find({
                    "$or": [
                        {"category": {"$in": ["Shelter", "SHELTER", "shelter"]}},
                        {"type": {"$in": ["Shelter", "SHELTER", "shelter"]}},
                        {"item_name": {"$regex": "shelter|hall|school|camp|center", "$options": "i"}},
                    ],
                    "status": {"$in": ["AVAILABLE", "PARTIALLY_AVAILABLE"]},
                })
                db_shelters = await shelter_cursor.to_list(length=100)
                ctx = AgentContext(
                    **base_context.model_dump(exclude={"parameters"}),
                    parameters={
                        "assessed_needs": assessed_needs,
                        "effective_priority": assessed_priority.value,
                        "available_shelters": db_shelters,
                        "estimated_affected_population": situation_data.get("estimated_affected_population", 0),
                    },
                )
                res = await central_orchestrator._run_and_track_agent(agent, ctx, actor, force_refresh=True, db=db)
                agent_results[agent_name.value] = res
                if res and res.structured_output:
                    try:
                        shelter_summary = ShelterCoordinationSummary(**res.structured_output)
                        recommended_shelters = shelter_summary.shelters_recommended
                    except Exception as e:
                        logger.error(f"Error parsing shelter summary during re-planning: {e}")

            elif agent_name == AgentName.HEALTHCARE_AGENT:
                hcf_cursor = db["healthcare_facilities"].find({
                    "is_deleted": {"$ne": True},
                    "status": {"$in": ["ACTIVE", "LIMITED", "AVAILABLE", "PARTIALLY_AVAILABLE", "OPERATIONAL"]},
                })
                db_facilities = await hcf_cursor.to_list(length=100)

                hosp_cursor = db["resources"].find({
                    "$or": [
                        {"category": {"$in": ["Healthcare", "HEALTHCARE", "healthcare", "Medical"]}},
                        {"type": {"$in": ["Hospital", "Clinic", "Trauma Center"]}},
                        {"item_name": {"$regex": "hospital|clinic|health|medical", "$options": "i"}},
                    ],
                    "status": {"$in": ["AVAILABLE", "PARTIALLY_AVAILABLE", "OPERATIONAL"]},
                })
                res_facilities = await hosp_cursor.to_list(length=100)
                existing_ids = {str(f.get("facility_id") or f.get("_id")) for f in db_facilities}
                for rf in res_facilities:
                    rf_id = str(rf.get("facility_id") or rf.get("resource_id") or rf.get("_id"))
                    if rf_id not in existing_ids:
                        db_facilities.append(rf)
                        existing_ids.add(rf_id)
                ctx = AgentContext(
                    **base_context.model_dump(exclude={"parameters"}),
                    parameters={
                        "assessed_needs": assessed_needs,
                        "effective_priority": assessed_priority.value,
                        "available_facilities": db_facilities,
                        "estimated_casualties": situation_data.get("estimated_casualties", 0),
                    },
                )
                res = await central_orchestrator._run_and_track_agent(agent, ctx, actor, force_refresh=True, db=db)
                agent_results[agent_name.value] = res
                if res and res.structured_output:
                    try:
                        healthcare_summary = HealthcareCoordinationSummary(**res.structured_output)
                        recommended_facilities = healthcare_summary.facilities_recommended
                    except Exception as e:
                        logger.error(f"Error parsing healthcare summary during re-planning: {e}")

            elif agent_name == AgentName.VOLUNTEER_AGENT:
                vol_cursor = db["users"].find({
                    "$or": [
                        {"role": {"$in": [UserRole.VOLUNTEER.value, "VOLUNTEER", "volunteer"]}},
                        {"volunteer_profile": {"$ne": None}},
                    ]
                })
                db_volunteers = await vol_cursor.to_list(length=200)
                ctx = AgentContext(
                    **base_context.model_dump(exclude={"parameters"}),
                    parameters={
                        "assessed_needs": assessed_needs,
                        "effective_priority": assessed_priority.value,
                        "available_volunteers": db_volunteers,
                    },
                )
                res = await central_orchestrator._run_and_track_agent(agent, ctx, actor, force_refresh=True, db=db)
                agent_results[agent_name.value] = res
                if res and res.structured_output:
                    try:
                        volunteer_summary = VolunteerCoordinationSummary(**res.structured_output)
                        recommended_volunteers = volunteer_summary.volunteers_recommended
                    except Exception as e:
                        logger.error(f"Error parsing volunteer summary during re-planning: {e}")

            elif agent_name == AgentName.ROUTE_AGENT:
                trans_cursor = db["resources"].find({
                    "$or": [
                        {"category": {"$in": ["Transport", "TRANSPORT", "transport", "Fleet"]}},
                        {"type": {"$in": ["Vehicle", "Ambulance", "Truck", "Van", "Boat"]}},
                        {"item_name": {"$regex": "ambulance|truck|van|boat|vehicle", "$options": "i"}},
                    ],
                    "status": {"$in": ["AVAILABLE", "PARTIALLY_AVAILABLE"]},
                })
                db_transports = await trans_cursor.to_list(length=100)
                ctx = AgentContext(
                    **base_context.model_dump(exclude={"parameters"}),
                    parameters={
                        "assessed_needs": assessed_needs,
                        "effective_priority": assessed_priority.value,
                        "available_transports": db_transports,
                        "destination_facilities": [f.model_dump() for f in recommended_facilities],
                        "destination_shelters": [s.model_dump() for s in recommended_shelters],
                    },
                )
                res = await central_orchestrator._run_and_track_agent(agent, ctx, actor, force_refresh=True, db=db)
                agent_results[agent_name.value] = res
                if res and res.structured_output:
                    try:
                        route_summary = RouteTransportCoordinationSummary(**res.structured_output)
                        if route_summary.transports_recommended:
                            recommended_transports = route_summary.transports_recommended
                        elif not recommended_transports:
                            recommended_transports = list(active_plan.recommended_transports)

                        if route_summary.routes_recommended:
                            recommended_routes = route_summary.routes_recommended
                        elif not recommended_routes:
                            recommended_routes = list(active_plan.recommended_routes)
                    except Exception as e:
                        logger.error(f"Error parsing route summary during re-planning: {e}")

            elif agent_name == AgentName.CONFLICT_RESOLUTION_AGENT:
                ctx = AgentContext(
                    **base_context.model_dump(exclude={"parameters"}),
                    parameters={
                        "assessed_needs": assessed_needs,
                        "recommended_allocations": [a.model_dump() for a in recommended_allocations],
                        "effective_priority": assessed_priority.value,
                        "shelter_summary": shelter_summary.model_dump() if shelter_summary else None,
                        "healthcare_summary": healthcare_summary.model_dump() if healthcare_summary else None,
                        "volunteer_summary": volunteer_summary.model_dump() if volunteer_summary else None,
                        "route_summary": route_summary.model_dump() if route_summary else None,
                    },
                )
                res = await central_orchestrator._run_and_track_agent(agent, ctx, actor, force_refresh=True, db=db)
                agent_results[agent_name.value] = res
                if res and res.structured_output:
                    try:
                        conflict_summary = ConflictResolutionSummary(**res.structured_output)
                        conflicts = conflict_summary.conflicts_detected
                    except Exception as e:
                        logger.error(f"Error parsing conflict summary during re-planning: {e}")

            await record_timeline_event(
                db=db,
                report_id=clean_sit_id,
                event_type=TimelineEventType.AFFECTED_AGENT_EXECUTION_COMPLETED,
                details=f"Agent '{agent_name.value}' completed re-planning execution.",
                actor_id=actor.get("id"),
                actor_name=actor.get("full_name"),
                actor_role=actor_role_enum,
            )

        # 7. Synthesize Revised Coordination Plan
        next_version = active_plan.version + 1
        new_plan_id = f"{active_plan.plan_id.split('-V')[0]}-V{next_version}"

        officer_attention = any([
            (shelter_summary and shelter_summary.officer_attention_required),
            (healthcare_summary and healthcare_summary.officer_attention_required),
            (volunteer_summary and volunteer_summary.officer_attention_required),
            (route_summary and route_summary.officer_attention_required),
            (conflict_summary and conflict_summary.officer_attention_required),
            len([c for c in conflicts if c.officer_attention_required]) > 0,
        ])
        has_unresolved = any(c.resolution_status.value == "UNRESOLVED" for c in conflicts) if conflicts else False

        # Build structured change explanation
        explanation_lines = [
            f"Revised Response Plan v{next_version} generated due to live operational change in {impact.changed_entity}.",
            f"Triggering Event: {impact.event_id} ({event.event_type.value if event else 'OPERATIONAL_CHANGE'}).",
            f"Root Cause: {impact.explanation}",
            f"Selectively re-executed agents: {', '.join([a.value for a in selective_agents])}.",
            f"Preserved unaffected operational components: {', '.join([a.value for a in TOPOLOGICAL_AGENT_ORDER if a not in selective_agents])}.",
        ]
        if impact.shortfalls:
            shortfall_desc = ", ".join([f"{k}: {v}" for k, v in impact.shortfalls.items()])
            explanation_lines.append(f"Shortfalls detected: {shortfall_desc}.")
        if officer_attention:
            explanation_lines.append("Officer attention required for unresolved resource/facility constraints.")

        structured_explanation = " \n".join(explanation_lines)

        revised_plan = CoordinationPlan(
            plan_id=new_plan_id,
            situation_id=clean_sit_id,
            version=next_version,
            state_fingerprint=replan_fp,
            generated_at=datetime.now(timezone.utc),
            participating_agents=participating_agents,
            agent_results=agent_results,
            assessed_priority=assessed_priority,
            assessed_needs=assessed_needs,
            recommended_allocations=recommended_allocations,
            conflicts=conflicts,
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
            officer_attention_required=officer_attention,
            has_unresolved_conflicts=has_unresolved,
            reasoning=structured_explanation,
            constraints=impact.violated_constraints if impact.violated_constraints else ["Standard operational constraints applied."],
            confidence=round(min(active_plan.confidence, 0.95), 2),
            status=CoordinationPlanStatus.PENDING_OFFICER_REVIEW,
            officer_review=None,
            previous_plan_id=active_plan.plan_id,
            previous_version=active_plan.version,
            trigger_event_id=impact.event_id,
            impact_id=impact.impact_id,
            is_revised_version=True,
            change_explanation=structured_explanation,
        )

        # 8. Compute Plan Diff
        diff_result = cls.compute_plan_diff(
            previous_plan=active_plan,
            revised_plan=revised_plan,
            impact=impact,
        )
        revised_plan.diff_summary = diff_result.model_dump()

        # 9. Persist Revised Plan to MongoDB
        plan_doc = revised_plan.model_dump()
        plan_doc["generated_at"] = plan_doc["generated_at"].isoformat()
        if plan_doc.get("diff_summary") and plan_doc["diff_summary"].get("generated_at"):
            plan_doc["diff_summary"]["generated_at"] = plan_doc["diff_summary"]["generated_at"].isoformat()

        await db["coordination_plans"].insert_one(plan_doc)

        # 10. Record Revised Plan Generated and Plan Diff Generated Timeline Events
        await record_timeline_event(
            db=db,
            report_id=clean_sit_id,
            event_type=TimelineEventType.REVISED_PLAN_GENERATED,
            details=f"Revised Response Plan {new_plan_id} (v{next_version}) generated in PENDING_OFFICER_REVIEW.",
            actor_id=actor.get("id"),
            actor_name=actor.get("full_name"),
            actor_role=actor_role_enum,
            metadata={
                "plan_id": new_plan_id,
                "version": next_version,
                "previous_plan_id": active_plan.plan_id,
                "status": CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
            },
        )

        await record_timeline_event(
            db=db,
            report_id=clean_sit_id,
            event_type=TimelineEventType.PLAN_DIFF_GENERATED,
            details=f"Plan diff computed for v{active_plan.version} -> v{next_version} ({len(diff_result.items)} item deltas).",
            actor_id=actor.get("id"),
            actor_name=actor.get("full_name"),
            actor_role=actor_role_enum,
            metadata={"diff_summary": diff_result.summary},
        )

        logger.info(
            f"Successfully generated revised Coordination Plan {new_plan_id} (v{next_version}) "
            f"for Situation {clean_sit_id}."
        )

        return revised_plan

    @classmethod
    def compute_plan_diff(
        cls,
        previous_plan: CoordinationPlan,
        revised_plan: CoordinationPlan,
        impact: Optional[ChangeImpactResult] = None,
    ) -> PlanDiffResult:
        """
        Deterministically compares two plan versions and categorizes all component changes
        into ADDED, REMOVED, CHANGED, UNCHANGED across all 7 operational domains
        (Resources, Shelters, Healthcare, Volunteers, Transports, Routes, Conflicts).
        """
        diff_items: List[PlanComponentDiffItem] = []

        # =========================================================================
        # 1. Resources / Allocations Diff
        # =========================================================================
        def normalize_res_type(t):
            if hasattr(t, "value"):
                return str(t.value).upper()
            return str(t).upper()

        prev_allocations = list(previous_plan.recommended_allocations)
        rev_allocations = list(revised_plan.recommended_allocations)

        paired_prev_indices = set()
        paired_rev_indices = set()

        # Pass 1: Match on exact matched_resource_id when present in both
        for r_idx, rev_a in enumerate(rev_allocations):
            rev_res_id = getattr(rev_a, "matched_resource_id", None)
            if not rev_res_id:
                continue
            for p_idx, prev_a in enumerate(prev_allocations):
                if p_idx in paired_prev_indices:
                    continue
                prev_res_id = getattr(prev_a, "matched_resource_id", None)
                if prev_res_id == rev_res_id:
                    paired_prev_indices.add(p_idx)
                    paired_rev_indices.add(r_idx)
                    prev_qty = float(getattr(prev_a, "allocated_quantity", None) or getattr(prev_a, "quantity_required", 0.0))
                    rev_qty = float(getattr(rev_a, "allocated_quantity", None) or getattr(rev_a, "quantity_required", 0.0))
                    item_name = getattr(rev_a, "matched_resource_name", None) or getattr(rev_a, "item_name", None) or normalize_res_type(rev_a.resource_type)
                    unit_str = getattr(rev_a, "unit", "units")

                    if prev_qty != rev_qty:
                        shortfall = max(0.0, prev_qty - rev_qty)
                        if shortfall > 0:
                            reason_msg = f"Available inventory decreased from {prev_qty:g} to {rev_qty:g}, creating a {shortfall:g}-{unit_str} shortfall. Allocation adjusted to feasible quantity."
                        else:
                            reason_msg = f"Allocation increased from {prev_qty:g} to {rev_qty:g} {unit_str}."
                        diff_items.append(PlanComponentDiffItem(
                            category="Resource",
                            entity_id=rev_res_id,
                            entity_name=item_name,
                            diff_type=DiffChangeType.CHANGED.value,
                            previous_value=prev_qty,
                            new_value=rev_qty,
                            reason=reason_msg,
                            requires_officer_attention=(rev_qty < prev_qty),
                        ))
                    else:
                        diff_items.append(PlanComponentDiffItem(
                            category="Resource",
                            entity_id=rev_res_id,
                            entity_name=item_name,
                            diff_type=DiffChangeType.UNCHANGED.value,
                            previous_value=prev_qty,
                            new_value=rev_qty,
                            reason=f"Resource allocation of {rev_qty:g} {unit_str} preserved unchanged.",
                            requires_officer_attention=False,
                        ))
                    break

        # Pass 2: Match remaining by normalized resource_type
        for r_idx, rev_a in enumerate(rev_allocations):
            if r_idx in paired_rev_indices:
                continue
            rev_type = normalize_res_type(rev_a.resource_type)
            for p_idx, prev_a in enumerate(prev_allocations):
                if p_idx in paired_prev_indices:
                    continue
                prev_type = normalize_res_type(prev_a.resource_type)
                if prev_type == rev_type:
                    paired_prev_indices.add(p_idx)
                    paired_rev_indices.add(r_idx)
                    prev_qty = float(getattr(prev_a, "allocated_quantity", None) or getattr(prev_a, "quantity_required", 0.0))
                    rev_qty = float(getattr(rev_a, "allocated_quantity", None) or getattr(rev_a, "quantity_required", 0.0))
                    item_id = getattr(rev_a, "matched_resource_id", None) or getattr(prev_a, "matched_resource_id", None) or rev_type
                    item_name = getattr(rev_a, "matched_resource_name", None) or getattr(prev_a, "matched_resource_name", None) or rev_type
                    unit_str = getattr(rev_a, "unit", "units")

                    if prev_qty != rev_qty:
                        shortfall = max(0.0, prev_qty - rev_qty)
                        if shortfall > 0:
                            reason_msg = f"Available inventory decreased from {prev_qty:g} to {rev_qty:g}, creating a {shortfall:g}-{unit_str} shortfall. Allocation adjusted to feasible quantity."
                        else:
                            reason_msg = f"Allocation modified from {prev_qty:g} to {rev_qty:g} {unit_str}."
                        diff_items.append(PlanComponentDiffItem(
                            category="Resource",
                            entity_id=item_id,
                            entity_name=item_name,
                            diff_type=DiffChangeType.CHANGED.value,
                            previous_value=prev_qty,
                            new_value=rev_qty,
                            reason=reason_msg,
                            requires_officer_attention=(rev_qty < prev_qty),
                        ))
                    else:
                        diff_items.append(PlanComponentDiffItem(
                            category="Resource",
                            entity_id=item_id,
                            entity_name=item_name,
                            diff_type=DiffChangeType.UNCHANGED.value,
                            previous_value=prev_qty,
                            new_value=rev_qty,
                            reason=f"Resource allocation of {rev_qty:g} {unit_str} preserved unchanged.",
                            requires_officer_attention=False,
                        ))
                    break

        # Pass 3: Remaining in revised -> ADDED
        for r_idx, rev_a in enumerate(rev_allocations):
            if r_idx not in paired_rev_indices:
                rev_qty = float(getattr(rev_a, "allocated_quantity", None) or getattr(rev_a, "quantity_required", 0.0))
                item_id = getattr(rev_a, "matched_resource_id", None) or normalize_res_type(rev_a.resource_type)
                item_name = getattr(rev_a, "matched_resource_name", None) or normalize_res_type(rev_a.resource_type)
                unit_str = getattr(rev_a, "unit", "units")
                diff_items.append(PlanComponentDiffItem(
                    category="Resource",
                    entity_id=item_id,
                    entity_name=item_name,
                    diff_type=DiffChangeType.ADDED.value,
                    previous_value=None,
                    new_value=rev_qty,
                    reason=f"Newly added resource allocation of {rev_qty:g} {unit_str} in revised plan.",
                    requires_officer_attention=False,
                ))

        # Pass 4: Remaining in previous -> REMOVED
        for p_idx, prev_a in enumerate(prev_allocations):
            if p_idx not in paired_prev_indices:
                prev_qty = float(getattr(prev_a, "allocated_quantity", None) or getattr(prev_a, "quantity_required", 0.0))
                item_id = getattr(prev_a, "matched_resource_id", None) or normalize_res_type(prev_a.resource_type)
                item_name = getattr(prev_a, "matched_resource_name", None) or normalize_res_type(prev_a.resource_type)
                diff_items.append(PlanComponentDiffItem(
                    category="Resource",
                    entity_id=item_id,
                    entity_name=item_name,
                    diff_type=DiffChangeType.REMOVED.value,
                    previous_value=prev_qty,
                    new_value=0.0,
                    reason=f"Allocation removed because resource {item_name} ({item_id}) became unavailable or depleted.",
                    requires_officer_attention=True,
                ))

        # =========================================================================
        # 2. Shelters Diff
        # =========================================================================
        prev_shl_map = {s.shelter_id: s for s in previous_plan.recommended_shelters}
        rev_shl_map = {s.shelter_id: s for s in revised_plan.recommended_shelters}

        for s_id, rev_s in rev_shl_map.items():
            rev_occ = float(getattr(rev_s, "recommended_occupancy", getattr(rev_s, "allocated_population", 0.0)))
            rev_rem = float(getattr(rev_s, "remaining_capacity", max(0.0, rev_s.total_capacity - rev_s.current_occupancy)))
            if s_id not in prev_shl_map:
                diff_items.append(PlanComponentDiffItem(
                    category="Shelter",
                    entity_id=s_id,
                    entity_name=rev_s.shelter_name,
                    diff_type=DiffChangeType.ADDED.value,
                    previous_value=None,
                    new_value={"occupancy": rev_occ, "remaining_capacity": rev_rem, "status": rev_s.status},
                    reason=f"Alternative shelter facility allocated (Capacity: {rev_s.total_capacity:g}, Occupancy: {rev_occ:g}).",
                ))
            else:
                prev_s = prev_shl_map[s_id]
                prev_occ = float(getattr(prev_s, "recommended_occupancy", getattr(prev_s, "allocated_population", 0.0)))
                prev_rem = float(getattr(prev_s, "remaining_capacity", max(0.0, prev_s.total_capacity - prev_s.current_occupancy)))
                
                if prev_occ != rev_occ or prev_s.status != rev_s.status or prev_rem != rev_rem:
                    occ_delta = rev_occ - prev_occ
                    if rev_s.status in ["UNAVAILABLE", "CLOSED", "OFFLINE"] and prev_s.status not in ["UNAVAILABLE", "CLOSED", "OFFLINE"]:
                        reason_msg = f"Shelter status changed from {prev_s.status} to {rev_s.status}; evacuated {prev_occ:g} evacuees."
                    elif occ_delta > 0:
                        reason_msg = f"Shelter occupancy increased by {occ_delta:g} ({prev_occ:g} -> {rev_occ:g}), reducing remaining capacity from {prev_rem:g} to {rev_rem:g}."
                    elif occ_delta < 0:
                        reason_msg = f"Shelter occupancy decreased by {abs(occ_delta):g} ({prev_occ:g} -> {rev_occ:g}), increasing remaining capacity from {prev_rem:g} to {rev_rem:g}."
                    else:
                        reason_msg = f"Shelter state modified (status: {prev_s.status} -> {rev_s.status}, remaining: {prev_rem:g} -> {rev_rem:g})."

                    diff_items.append(PlanComponentDiffItem(
                        category="Shelter",
                        entity_id=s_id,
                        entity_name=rev_s.shelter_name,
                        diff_type=DiffChangeType.CHANGED.value,
                        previous_value={"occupancy": prev_occ, "remaining_capacity": prev_rem, "status": prev_s.status},
                        new_value={"occupancy": rev_occ, "remaining_capacity": rev_rem, "status": rev_s.status},
                        reason=reason_msg,
                        requires_officer_attention=(rev_s.status != "AVAILABLE" or rev_occ < prev_occ),
                    ))
                else:
                    diff_items.append(PlanComponentDiffItem(
                        category="Shelter",
                        entity_id=s_id,
                        entity_name=rev_s.shelter_name,
                        diff_type=DiffChangeType.UNCHANGED.value,
                        previous_value={"occupancy": prev_occ, "remaining_capacity": prev_rem, "status": prev_s.status},
                        new_value={"occupancy": rev_occ, "remaining_capacity": rev_rem, "status": rev_s.status},
                        reason="Shelter capacity and occupancy preserved unchanged.",
                    ))

        for s_id, prev_s in prev_shl_map.items():
            if s_id not in rev_shl_map:
                prev_occ = float(getattr(prev_s, "recommended_occupancy", getattr(prev_s, "allocated_population", 0.0)))
                prev_rem = float(getattr(prev_s, "remaining_capacity", max(0.0, prev_s.total_capacity - prev_s.current_occupancy)))
                diff_items.append(PlanComponentDiffItem(
                    category="Shelter",
                    entity_id=s_id,
                    entity_name=prev_s.shelter_name,
                    diff_type=DiffChangeType.REMOVED.value,
                    previous_value={"occupancy": prev_occ, "remaining_capacity": prev_rem, "status": prev_s.status},
                    new_value=0.0,
                    reason=f"Shelter {prev_s.shelter_name} removed (closure or capacity breach).",
                    requires_officer_attention=True,
                ))

        # =========================================================================
        # 3. Healthcare Facilities Diff
        # =========================================================================
        prev_hosp_map = {h.facility_id: h for h in previous_plan.recommended_facilities}
        rev_hosp_map = {h.facility_id: h for h in revised_plan.recommended_facilities}

        for h_id, rev_h in rev_hosp_map.items():
            rev_pat = float(getattr(rev_h, "allocated_patients", getattr(rev_h, "allocated_casualties", 0.0)))
            if h_id not in prev_hosp_map:
                diff_items.append(PlanComponentDiffItem(
                    category="Healthcare",
                    entity_id=h_id,
                    entity_name=rev_h.facility_name,
                    diff_type=DiffChangeType.ADDED.value,
                    previous_value=None,
                    new_value={"patients": rev_pat, "available_beds": rev_h.available_beds, "icu_available": rev_h.icu_available, "status": rev_h.status},
                    reason=f"New healthcare facility matched for casualty triage (Beds: {rev_h.available_beds:g}, ICU: {rev_h.icu_available}).",
                ))
            else:
                prev_h = prev_hosp_map[h_id]
                prev_pat = float(getattr(prev_h, "allocated_patients", getattr(prev_h, "allocated_casualties", 0.0)))
                if (prev_pat != rev_pat or 
                    prev_h.status != rev_h.status or 
                    prev_h.available_beds != rev_h.available_beds or
                    prev_h.icu_available != rev_h.icu_available):
                    
                    reason_msg = f"Healthcare facility triage modified: Patients ({prev_pat:g} -> {rev_pat:g})"
                    if prev_h.icu_available != rev_h.icu_available:
                        reason_msg += f", ICU available ({prev_h.icu_available} -> {rev_h.icu_available})"
                    if prev_h.available_beds != rev_h.available_beds:
                        reason_msg += f", Beds available ({prev_h.available_beds:g} -> {rev_h.available_beds:g})"
                    reason_msg += "."

                    diff_items.append(PlanComponentDiffItem(
                        category="Healthcare",
                        entity_id=h_id,
                        entity_name=rev_h.facility_name,
                        diff_type=DiffChangeType.CHANGED.value,
                        previous_value={"patients": prev_pat, "available_beds": prev_h.available_beds, "icu_available": prev_h.icu_available, "status": prev_h.status},
                        new_value={"patients": rev_pat, "available_beds": rev_h.available_beds, "icu_available": rev_h.icu_available, "status": rev_h.status},
                        reason=reason_msg,
                        requires_officer_attention=(rev_h.status != "AVAILABLE" or rev_h.icu_available < prev_h.icu_available),
                    ))
                else:
                    diff_items.append(PlanComponentDiffItem(
                        category="Healthcare",
                        entity_id=h_id,
                        entity_name=rev_h.facility_name,
                        diff_type=DiffChangeType.UNCHANGED.value,
                        previous_value={"patients": prev_pat, "available_beds": prev_h.available_beds, "icu_available": prev_h.icu_available, "status": prev_h.status},
                        new_value={"patients": rev_pat, "available_beds": rev_h.available_beds, "icu_available": rev_h.icu_available, "status": rev_h.status},
                        reason="Healthcare facility capacity preserved unchanged.",
                    ))

        for h_id, prev_h in prev_hosp_map.items():
            if h_id not in rev_hosp_map:
                prev_pat = float(getattr(prev_h, "allocated_patients", getattr(prev_h, "allocated_casualties", 0.0)))
                diff_items.append(PlanComponentDiffItem(
                    category="Healthcare",
                    entity_id=h_id,
                    entity_name=prev_h.facility_name,
                    diff_type=DiffChangeType.REMOVED.value,
                    previous_value={"patients": prev_pat, "status": prev_h.status},
                    new_value=0.0,
                    reason=f"Healthcare facility {prev_h.facility_name} removed (outage or offline).",
                    requires_officer_attention=True,
                ))

        # =========================================================================
        # 4. Volunteers Diff
        # =========================================================================
        prev_vol_map = {v.volunteer_id: v for v in previous_plan.recommended_volunteers}
        rev_vol_map = {v.volunteer_id: v for v in revised_plan.recommended_volunteers}

        for v_id, rev_v in rev_vol_map.items():
            if v_id not in prev_vol_map:
                diff_items.append(PlanComponentDiffItem(
                    category="Volunteer",
                    entity_id=v_id,
                    entity_name=rev_v.volunteer_name,
                    diff_type=DiffChangeType.ADDED.value,
                    previous_value=None,
                    new_value={"role": rev_v.role_or_skill, "operation": rev_v.assigned_operation, "status": rev_v.availability_status},
                    reason=f"New volunteer responder assigned to mission: {rev_v.assigned_operation}.",
                ))
            else:
                prev_v = prev_vol_map[v_id]
                if (prev_v.assigned_operation != rev_v.assigned_operation or 
                    prev_v.availability_status != rev_v.availability_status or
                    prev_v.role_or_skill != rev_v.role_or_skill):
                    diff_items.append(PlanComponentDiffItem(
                        category="Volunteer",
                        entity_id=v_id,
                        entity_name=rev_v.volunteer_name,
                        diff_type=DiffChangeType.CHANGED.value,
                        previous_value={"role": prev_v.role_or_skill, "operation": prev_v.assigned_operation, "status": prev_v.availability_status},
                        new_value={"role": rev_v.role_or_skill, "operation": rev_v.assigned_operation, "status": rev_v.availability_status},
                        reason=f"Volunteer assignment modified from '{prev_v.assigned_operation}' to '{rev_v.assigned_operation}'.",
                        requires_officer_attention=("UNAVAILABLE" in rev_v.availability_status.upper()),
                    ))
                else:
                    diff_items.append(PlanComponentDiffItem(
                        category="Volunteer",
                        entity_id=v_id,
                        entity_name=rev_v.volunteer_name,
                        diff_type=DiffChangeType.UNCHANGED.value,
                        previous_value={"role": prev_v.role_or_skill, "operation": prev_v.assigned_operation, "status": prev_v.availability_status},
                        new_value={"role": rev_v.role_or_skill, "operation": rev_v.assigned_operation, "status": rev_v.availability_status},
                        reason="Volunteer assignment preserved unchanged.",
                    ))

        for v_id, prev_v in prev_vol_map.items():
            if v_id not in rev_vol_map:
                diff_items.append(PlanComponentDiffItem(
                    category="Volunteer",
                    entity_id=v_id,
                    entity_name=prev_v.volunteer_name,
                    diff_type=DiffChangeType.REMOVED.value,
                    previous_value={"role": prev_v.role_or_skill, "operation": prev_v.assigned_operation, "status": prev_v.availability_status},
                    new_value=None,
                    reason=f"Volunteer responder {prev_v.volunteer_name} became unavailable; reassignment required.",
                    requires_officer_attention=True,
                ))

        # =========================================================================
        # 5. Transport Diff
        # =========================================================================
        prev_trans_map = {t.transport_id: t for t in previous_plan.recommended_transports}
        rev_trans_map = {t.transport_id: t for t in revised_plan.recommended_transports}

        for t_id, rev_t in rev_trans_map.items():
            if t_id not in prev_trans_map:
                diff_items.append(PlanComponentDiffItem(
                    category="Transport",
                    entity_id=t_id,
                    entity_name=rev_t.vehicle_name,
                    diff_type=DiffChangeType.ADDED.value,
                    previous_value=None,
                    new_value={"mission": rev_t.assigned_mission, "status": rev_t.current_status},
                    reason=f"New transport vehicle dispatched for mission: {rev_t.assigned_mission}.",
                ))
            else:
                prev_t = prev_trans_map[t_id]
                if prev_t.assigned_mission != rev_t.assigned_mission or prev_t.current_status != rev_t.current_status:
                    diff_items.append(PlanComponentDiffItem(
                        category="Transport",
                        entity_id=t_id,
                        entity_name=rev_t.vehicle_name,
                        diff_type=DiffChangeType.CHANGED.value,
                        previous_value={"mission": prev_t.assigned_mission, "status": prev_t.current_status},
                        new_value={"mission": rev_t.assigned_mission, "status": rev_t.current_status},
                        reason=f"Transport assignment modified: {prev_t.assigned_mission} ({prev_t.current_status}) -> {rev_t.assigned_mission} ({rev_t.current_status}).",
                        requires_officer_attention=(rev_t.current_status != "AVAILABLE"),
                    ))
                else:
                    diff_items.append(PlanComponentDiffItem(
                        category="Transport",
                        entity_id=t_id,
                        entity_name=rev_t.vehicle_name,
                        diff_type=DiffChangeType.UNCHANGED.value,
                        previous_value={"mission": prev_t.assigned_mission, "status": prev_t.current_status},
                        new_value={"mission": rev_t.assigned_mission, "status": rev_t.current_status},
                        reason="Transport vehicle assignment preserved unchanged.",
                    ))

        for t_id, prev_t in prev_trans_map.items():
            if t_id not in rev_trans_map:
                diff_items.append(PlanComponentDiffItem(
                    category="Transport",
                    entity_id=t_id,
                    entity_name=prev_t.vehicle_name,
                    diff_type=DiffChangeType.REMOVED.value,
                    previous_value={"mission": prev_t.assigned_mission, "status": prev_t.current_status},
                    new_value=None,
                    reason=f"Transport vehicle {prev_t.vehicle_name} unavailable / removed.",
                    requires_officer_attention=True,
                ))

        # =========================================================================
        # 6. Routes Diff
        # =========================================================================
        prev_route_map = {r.route_id: r for r in previous_plan.recommended_routes}
        rev_route_map = {r.route_id: r for r in revised_plan.recommended_routes}

        for r_id, rev_r in rev_route_map.items():
            route_label = f"{rev_r.origin_name} → {rev_r.destination_name}"
            if r_id not in prev_route_map:
                diff_items.append(PlanComponentDiffItem(
                    category="Route",
                    entity_id=r_id,
                    entity_name=route_label,
                    diff_type=DiffChangeType.ADDED.value,
                    previous_value=None,
                    new_value={"status": rev_r.road_condition_status, "eta_minutes": rev_r.estimated_duration_minutes},
                    reason=f"New transit corridor activated (ETA: {rev_r.estimated_duration_minutes:.0f} min, Status: {rev_r.road_condition_status}).",
                ))
            else:
                prev_r = prev_route_map[r_id]
                if (prev_r.road_condition_status != rev_r.road_condition_status or 
                    abs(prev_r.estimated_duration_minutes - rev_r.estimated_duration_minutes) > 0.1 or
                    prev_r.assigned_mission != rev_r.assigned_mission):
                    diff_items.append(PlanComponentDiffItem(
                        category="Route",
                        entity_id=r_id,
                        entity_name=route_label,
                        diff_type=DiffChangeType.CHANGED.value,
                        previous_value={"status": prev_r.road_condition_status, "eta_minutes": prev_r.estimated_duration_minutes},
                        new_value={"status": rev_r.road_condition_status, "eta_minutes": rev_r.estimated_duration_minutes},
                        reason=f"Route condition updated ({prev_r.road_condition_status} -> {rev_r.road_condition_status}, ETA {prev_r.estimated_duration_minutes:.0f} min -> {rev_r.estimated_duration_minutes:.0f} min).",
                        requires_officer_attention=(rev_r.road_condition_status != "PASSABLE"),
                    ))
                else:
                    diff_items.append(PlanComponentDiffItem(
                        category="Route",
                        entity_id=r_id,
                        entity_name=route_label,
                        diff_type=DiffChangeType.UNCHANGED.value,
                        previous_value={"status": prev_r.road_condition_status, "eta_minutes": prev_r.estimated_duration_minutes},
                        new_value={"status": rev_r.road_condition_status, "eta_minutes": rev_r.estimated_duration_minutes},
                        reason="Transit route preserved unchanged.",
                    ))

        for r_id, prev_r in prev_route_map.items():
            if r_id not in rev_route_map:
                route_label = f"{prev_r.origin_name} → {prev_r.destination_name}"
                diff_items.append(PlanComponentDiffItem(
                    category="Route",
                    entity_id=r_id,
                    entity_name=route_label,
                    diff_type=DiffChangeType.REMOVED.value,
                    previous_value={"status": prev_r.road_condition_status, "eta_minutes": prev_r.estimated_duration_minutes},
                    new_value=None,
                    reason=f"Route removed due to road blockage or operational rerouting.",
                    requires_officer_attention=True,
                ))

        # =========================================================================
        # 7. Conflicts Diff (Compare by conflict_type + affected_resource/affected_need)
        # =========================================================================
        def get_conflict_key(c):
            c_type = c.conflict_type.value if hasattr(c.conflict_type, "value") else str(c.conflict_type)
            res = str(c.affected_resource or c.affected_need or "GENERAL").strip().upper()
            return f"{c_type}:{res}"

        prev_conf_map = {get_conflict_key(c): c for c in previous_plan.conflicts}
        rev_conf_map = {get_conflict_key(c): c for c in revised_plan.conflicts}

        for c_key, rev_c in rev_conf_map.items():
            c_label = rev_c.conflict_type.value if hasattr(rev_c.conflict_type, "value") else str(rev_c.conflict_type)
            if rev_c.affected_resource:
                c_label += f" ({rev_c.affected_resource})"
            
            if c_key not in prev_conf_map:
                diff_items.append(PlanComponentDiffItem(
                    category="Conflict",
                    entity_id=rev_c.conflict_id,
                    entity_name=c_label,
                    diff_type=DiffChangeType.ADDED.value,
                    previous_value=None,
                    new_value={"shortfall": rev_c.shortfall, "status": rev_c.resolution_status.value if hasattr(rev_c.resolution_status, "value") else str(rev_c.resolution_status)},
                    reason=f"New coordination conflict detected (Shortfall: {rev_c.shortfall or 'N/A'}). {rev_c.description}",
                    requires_officer_attention=rev_c.officer_attention_required,
                ))
            else:
                prev_c = prev_conf_map[c_key]
                if (prev_c.shortfall != rev_c.shortfall or 
                    prev_c.resolution_status != rev_c.resolution_status or
                    prev_c.severity != rev_c.severity):
                    diff_items.append(PlanComponentDiffItem(
                        category="Conflict",
                        entity_id=rev_c.conflict_id,
                        entity_name=c_label,
                        diff_type=DiffChangeType.CHANGED.value,
                        previous_value={"shortfall": prev_c.shortfall, "status": prev_c.resolution_status.value if hasattr(prev_c.resolution_status, "value") else str(prev_c.resolution_status)},
                        new_value={"shortfall": rev_c.shortfall, "status": rev_c.resolution_status.value if hasattr(rev_c.resolution_status, "value") else str(rev_c.resolution_status)},
                        reason=f"Conflict status/shortfall updated: Shortfall {prev_c.shortfall or 0} -> {rev_c.shortfall or 0}.",
                        requires_officer_attention=rev_c.officer_attention_required,
                    ))
                else:
                    diff_items.append(PlanComponentDiffItem(
                        category="Conflict",
                        entity_id=rev_c.conflict_id,
                        entity_name=c_label,
                        diff_type=DiffChangeType.UNCHANGED.value,
                        previous_value={"shortfall": prev_c.shortfall, "status": prev_c.resolution_status.value if hasattr(prev_c.resolution_status, "value") else str(prev_c.resolution_status)},
                        new_value={"shortfall": rev_c.shortfall, "status": rev_c.resolution_status.value if hasattr(rev_c.resolution_status, "value") else str(rev_c.resolution_status)},
                        reason="Conflict state preserved.",
                        requires_officer_attention=False,
                    ))

        for c_key, prev_c in prev_conf_map.items():
            if c_key not in rev_conf_map:
                c_label = prev_c.conflict_type.value if hasattr(prev_c.conflict_type, "value") else str(prev_c.conflict_type)
                if prev_c.affected_resource:
                    c_label += f" ({prev_c.affected_resource})"
                diff_items.append(PlanComponentDiffItem(
                    category="Conflict",
                    entity_id=prev_c.conflict_id,
                    entity_name=c_label,
                    diff_type=DiffChangeType.REMOVED.value,
                    previous_value={"shortfall": prev_c.shortfall, "status": prev_c.resolution_status.value if hasattr(prev_c.resolution_status, "value") else str(prev_c.resolution_status)},
                    new_value=None,
                    reason=f"Conflict resolved in revised plan allocation ({prev_c.description}).",
                    requires_officer_attention=False,
                ))

        # Sort diff items: CHANGED first, then ADDED/REMOVED, then UNCHANGED
        order_map = {
            DiffChangeType.CHANGED.value: 0,
            DiffChangeType.ADDED.value: 1,
            DiffChangeType.REMOVED.value: 2,
            DiffChangeType.UNCHANGED.value: 3,
        }
        diff_items.sort(key=lambda d: order_map.get(d.diff_type, 9))

        # Summary line
        added_cnt = sum(1 for d in diff_items if d.diff_type == DiffChangeType.ADDED.value)
        changed_cnt = sum(1 for d in diff_items if d.diff_type == DiffChangeType.CHANGED.value)
        removed_cnt = sum(1 for d in diff_items if d.diff_type == DiffChangeType.REMOVED.value)
        unchanged_cnt = sum(1 for d in diff_items if d.diff_type == DiffChangeType.UNCHANGED.value)

        diff_summary_str = (
            f"Plan v{previous_plan.version} -> v{revised_plan.version}: "
            f"{changed_cnt} changed, {added_cnt} added, {removed_cnt} removed, {unchanged_cnt} preserved."
        )

        affected_domains_list = impact.affected_domains if (impact and impact.affected_domains) else [OperationalDomain.RESOURCE]
        affected_agents_list = impact.affected_agents if (impact and impact.affected_agents) else [AgentName.CONFLICT_RESOLUTION_AGENT]

        return PlanDiffResult(
            previous_plan_id=previous_plan.plan_id,
            previous_version=previous_plan.version,
            new_plan_id=revised_plan.plan_id,
            new_version=revised_plan.version,
            summary=diff_summary_str,
            items=diff_items,
            affected_domains=affected_domains_list,
            affected_agents=affected_agents_list,
            has_conflicts=revised_plan.has_unresolved_conflicts,
            is_material_change=(changed_cnt > 0 or added_cnt > 0 or removed_cnt > 0),
            generated_at=datetime.now(timezone.utc),
        )
