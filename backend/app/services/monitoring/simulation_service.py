import json
import uuid
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from app.models.enums import (
    AgentName,
    ConflictStatus,
    ConflictType,
    CoordinationPlanStatus,
    DiffChangeType,
    EventSourceType,
    ImpactLevel,
    MonitoringEventType,
    NeedUrgency,
    OperationalDomain,
    PlanValidityStatus,
    ResourceType,
    SeverityLevel,
    TimelineEventType,
    UserRole,
)
from app.models.agent import (
    AgentContext,
    AgentResult,
    CoordinationPlan,
    PlanRecommendedResource,
    RecommendedShelter,
    ShelterCoordinationSummary,
    RecommendedHealthcareFacility,
    HealthcareCoordinationSummary,
    RecommendedVolunteerAssignment,
    VolunteerCoordinationSummary,
    RecommendedTransport,
    RecommendedRoute,
    RouteTransportCoordinationSummary,
    DetectedConflict,
    ConflictResolutionSummary,
)
from app.models.monitoring import (
    MonitoringEvent,
    ChangeImpactResult,
    PlanDiffResult,
    PlanComponentDiffItem,
)
from app.models.simulation import (
    ScenarioType,
    SimulationStatus,
    SimulationScenario,
    SimulationRun,
    AddScenarioRequest,
    SimulationEntityTarget,
    SimulationTargetLookupResponse,
    RunSimulationResponse,
)
from app.services.agents.registry import agent_registry
from app.services.agents.orchestrator import central_orchestrator, compute_situation_state_fingerprint
from app.services.monitoring.impact_analyzer import ChangeImpactAnalyzer
from app.services.monitoring.replanning_service import DynamicReplanningService, TOPOLOGICAL_AGENT_ORDER
from app.services.timeline import record_timeline_event
from app.db.mongodb import db_manager

logger = logging.getLogger("resilience.services.monitoring.simulation")


def compute_simulation_fingerprint(
    situation_id: str,
    baseline_plan_id: str,
    baseline_fingerprint: str,
    scenarios: List[SimulationScenario],
) -> str:
    """
    Computes a deterministic SHA-256 fingerprint for a simulation run.
    """
    scenario_payloads = []
    for s in scenarios:
        scenario_payloads.append({
            "type": s.scenario_type.value,
            "target_type": s.target_entity_type,
            "target_id": s.target_entity_id,
            "sim_val": s.simulated_value,
        })
    scenario_payloads.sort(key=lambda x: (x["type"], x["target_id"]))

    payload = {
        "situation_id": str(situation_id).strip().upper(),
        "baseline_plan_id": str(baseline_plan_id).strip(),
        "baseline_fp": str(baseline_fingerprint).strip(),
        "scenarios": scenario_payloads,
    }
    canonical_json = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]


class SimulationService:
    """
    Phase 6.5 Simulation / What-If Scenario Engine.
    Executes isolated what-if analysis on read-only snapshots and in-memory overlays.
    Strictly guarantees ZERO mutation of real MongoDB operational collections.
    """

    @classmethod
    async def get_current_active_plan_for_situation(
        cls,
        situation_id: str,
        db: AsyncIOMotorDatabase,
    ) -> Optional[CoordinationPlan]:
        """
        Canonical resolver for resolving the authoritative active coordination plan baseline for a situation.
        - Exact situation_id match (case/whitespace sanitized)
        - Excludes simulated plans (is_simulation != True)
        - Matches authoritative active status: ACTIVE or APPROVED
        - Strictly excludes PENDING_OFFICER_REVIEW, REJECTED, SUPERSEDED, CANCELLED, STALE, SIMULATION_RESULT
        - Selects the latest authoritative version (sorted by version descending)
        - Never fabricates a fallback or returns a non-active plan
        """
        clean_sit_id = situation_id.strip().upper()
        
        # Authoritative active statuses for coordination plans in resilience AI: ACTIVE and APPROVED
        active_statuses = [CoordinationPlanStatus.ACTIVE.value, CoordinationPlanStatus.APPROVED.value]
        
        plan_doc = await db["coordination_plans"].find_one({
            "situation_id": clean_sit_id,
            "status": {"$in": active_statuses},
            "is_simulation": {"$ne": True},
        }, sort=[("version", -1)])
        
        if not plan_doc:
            return None
            
        return CoordinationPlan(**plan_doc)

    @classmethod
    async def create_simulation(
        cls,
        situation_id: str,
        name: Optional[str] = None,
        officer_actor: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> SimulationRun:
        """
        Initializes a draft simulation run referencing a real situation and its active baseline plan.
        Validates the authoritative active baseline BEFORE creating any simulation draft.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        clean_sit_id = situation_id.strip().upper()

        # 1. Fetch real situation
        sit_doc = await db["situations"].find_one({"situation_id": clean_sit_id})
        if not sit_doc:
            sit_doc = await db["situations"].find_one({"_id": clean_sit_id})
        if not sit_doc:
            raise ValueError(f"Target situation '{clean_sit_id}' does not exist in authoritative database.")

        situation_name = sit_doc.get("title") or sit_doc.get("name") or f"Situation {clean_sit_id}"

        # 2. Resolve authoritative ACTIVE baseline plan using canonical resolver
        baseline_plan = await cls.get_current_active_plan_for_situation(clean_sit_id, db)
        if not baseline_plan:
            raise ValueError(
                "SIMULATION_BASELINE_REQUIRED: This situation does not currently have an active response plan. "
                "Activate an authoritative response plan before running What-If Simulation."
            )

        baseline_fp = compute_situation_state_fingerprint(sit_doc)

        sim_id = f"SIM-{clean_sit_id}-{uuid.uuid4().hex[:6].upper()}"
        sim_name = name or f"What-If: {situation_name} ({datetime.now(timezone.utc).strftime('%b %d %H:%M')})"

        actor_id = officer_actor.get("id", "OFFICER") if officer_actor else "OFFICER"
        actor_name = officer_actor.get("full_name", "Emergency Officer") if officer_actor else "Emergency Officer"

        sim_run = SimulationRun(
            simulation_id=sim_id,
            simulation_name=sim_name,
            situation_id=clean_sit_id,
            situation_name=situation_name,
            baseline_plan_id=baseline_plan.plan_id,
            baseline_plan_version=baseline_plan.version,
            baseline_fingerprint=baseline_fp,
            scenarios=[],
            status=SimulationStatus.DRAFT,
            is_simulation=True,
            created_by_id=actor_id,
            created_by_name=actor_name,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )

        doc = sim_run.model_dump()
        doc["created_at"] = doc["created_at"].isoformat()
        if doc.get("expires_at"):
            doc["expires_at"] = doc["expires_at"].isoformat()

        await db["simulations"].insert_one(doc)

        # Record simulation audit event (segregated)
        await db["simulation_audit_logs"].insert_one({
            "event_id": f"AUD-SIM-{uuid.uuid4().hex[:6].upper()}",
            "simulation_id": sim_id,
            "action": TimelineEventType.SIMULATION_CREATED.value,
            "actor_id": actor_id,
            "actor_name": actor_name,
            "situation_id": clean_sit_id,
            "baseline_plan_id": baseline_plan.plan_id,
            "details": f"Draft simulation '{sim_name}' created against baseline plan {baseline_plan.plan_id} (v{baseline_plan.version}).",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "is_simulation": True,
        })

        return sim_run

    @classmethod
    async def get_target_entities(
        cls,
        situation_id: str,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> SimulationTargetLookupResponse:
        """
        Queries real existing operational assets for a situation to populate scenario builder dropdowns
        with zero dummy data.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        clean_sit_id = situation_id.strip().upper()

        sit_doc = await db["situations"].find_one({"situation_id": clean_sit_id})
        if not sit_doc:
            sit_doc = await db["situations"].find_one({"_id": clean_sit_id})
        if not sit_doc:
            raise ValueError(f"Situation '{clean_sit_id}' not found.")

        sit_name = sit_doc.get("title") or sit_doc.get("name") or f"Situation {clean_sit_id}"

        # Fetch canonical authoritative active plan baseline
        plan = await cls.get_current_active_plan_for_situation(clean_sit_id, db)
        baseline_plan_id = plan.plan_id if plan else "NONE"
        baseline_version = plan.version if plan else 0
        baseline_status = plan.status.value if plan else None
        baseline_activated_at = None
        if plan:
            if plan.officer_review and plan.officer_review.reviewed_at:
                baseline_activated_at = plan.officer_review.reviewed_at.isoformat()
            elif plan.generated_at:
                baseline_activated_at = plan.generated_at.isoformat()
        has_active = (plan is not None)

        # 1. Resources (from active allocations and warehouse inventory)
        # 1. Resources (from active allocations and warehouse inventory)
        resources_list: List[SimulationEntityTarget] = []
        if plan and plan.recommended_allocations:
            for a in plan.recommended_allocations:
                r_id = a.matched_resource_id or str(a.resource_type.value)
                r_name = a.matched_resource_name or a.resource_type.value
                val = float(a.allocated_quantity or a.quantity_required or 0.0)
                resources_list.append(SimulationEntityTarget(
                    entity_id=r_id,
                    entity_name=f"{r_name} ({a.resource_type.value})",
                    name=r_name,
                    entity_type="RESOURCE",
                    current_value=val,
                    available_capacity_or_quantity=val,
                    unit=a.unit or "UNITS",
                    unit_or_type=a.unit or a.resource_type.value,
                    status="ALLOCATED",
                    location_summary=a.depot_location or "Incident Depot",
                    location_name=a.depot_location or "Incident Depot",
                ))

        # Query warehouse DB resources
        res_cursor = db["resources"].find({"status": {"$in": ["AVAILABLE", "PARTIALLY_AVAILABLE", "available", "partially_available"]}}).limit(25)
        raw_res = await res_cursor.to_list(length=25)
        existing_res_ids = {r.entity_id for r in resources_list}
        for r in raw_res:
            r_id = r.get("resource_id") or str(r.get("_id"))
            if r_id not in existing_res_ids:
                r_name = r.get("name") or r.get("item_name") or f"Resource {r_id}"
                r_type = r.get("resource_type") or r.get("category") or r.get("type") or "Resource"
                val = float(r.get("quantity_available") or r.get("available_quantity") or r.get("quantity") or 0.0)
                unit_val = r.get("unit") or "UNITS"
                loc = r.get("location_name") or r.get("depot_name") or r.get("warehouse_name") or "Main Depot"
                resources_list.append(SimulationEntityTarget(
                    entity_id=r_id,
                    entity_name=f"{r_name} ({r_type})",
                    name=r_name,
                    entity_type="RESOURCE",
                    current_value=val,
                    available_capacity_or_quantity=val,
                    unit=unit_val,
                    unit_or_type=unit_val,
                    status=r.get("status", "AVAILABLE"),
                    location_summary=loc,
                    location_name=loc,
                ))

        # 2. Shelters
        shelters_list: List[SimulationEntityTarget] = []
        if plan and plan.recommended_shelters:
            for s in plan.recommended_shelters:
                rem_cap = float(s.remaining_capacity or 0.0)
                shelters_list.append(SimulationEntityTarget(
                    entity_id=s.shelter_id,
                    entity_name=s.shelter_name,
                    name=s.shelter_name,
                    entity_type="SHELTER",
                    current_value=rem_cap,
                    available_capacity_or_quantity=rem_cap,
                    unit="BEDS",
                    unit_or_type="BEDS",
                    status=s.status or "AVAILABLE",
                    location_summary=s.location_address or "Evacuation Zone",
                    location_name=s.location_address or "Evacuation Zone",
                ))

        # Also search shelters in shelters collection and resources collection
        shelter_cursor = db["shelters"].find({}).limit(20)
        raw_shelters = await shelter_cursor.to_list(length=20)
        existing_shl_ids = {s.entity_id for s in shelters_list}
        for s in raw_shelters:
            s_id = s.get("shelter_id") or str(s.get("_id"))
            if s_id not in existing_shl_ids:
                cap = float(s.get("capacity") or s.get("total_capacity") or 0.0)
                occ = float(s.get("current_occupancy") or s.get("occupancy") or 0.0)
                avail = max(0.0, cap - occ)
                s_name = s.get("name") or s.get("shelter_name") or f"Shelter {s_id}"
                loc = s.get("address") or s.get("location_name") or "Relief Center"
                shelters_list.append(SimulationEntityTarget(
                    entity_id=s_id,
                    entity_name=s_name,
                    name=s_name,
                    entity_type="SHELTER",
                    current_value=avail,
                    available_capacity_or_quantity=avail,
                    unit="BEDS",
                    unit_or_type="BEDS",
                    status=s.get("status", "AVAILABLE"),
                    location_summary=loc,
                    location_name=loc,
                ))
                existing_shl_ids.add(s_id)

        # Also look in resources for shelter-type resources if shelters list is empty
        if len(shelters_list) < 5:
            res_shl_cursor = db["resources"].find({
                "$or": [
                    {"category": {"$in": ["Shelter", "SHELTER", "Essential Relief"]}},
                    {"resource_type": {"$in": ["Shelter", "SHELTER"]}},
                ]
            }).limit(10)
            raw_res_shl = await res_shl_cursor.to_list(length=10)
            for s in raw_res_shl:
                s_id = s.get("resource_id") or str(s.get("_id"))
                if s_id not in existing_shl_ids:
                    s_name = s.get("name") or s.get("item_name") or f"Shelter {s_id}"
                    val = float(s.get("quantity_available") or s.get("available_quantity") or s.get("quantity") or 0.0)
                    loc = s.get("location_name") or s.get("depot_name") or "Relief Depot"
                    shelters_list.append(SimulationEntityTarget(
                        entity_id=s_id,
                        entity_name=s_name,
                        name=s_name,
                        entity_type="SHELTER",
                        current_value=val,
                        available_capacity_or_quantity=val,
                        unit=s.get("unit") or "BEDS",
                        unit_or_type=s.get("unit") or "BEDS",
                        status=s.get("status", "AVAILABLE"),
                        location_summary=loc,
                        location_name=loc,
                    ))
                    existing_shl_ids.add(s_id)

        # 3. Healthcare Facilities
        healthcare_list: List[SimulationEntityTarget] = []
        if plan and plan.recommended_facilities:
            for h in plan.recommended_facilities:
                avail_beds = float(h.available_beds or 0.0)
                healthcare_list.append(SimulationEntityTarget(
                    entity_id=h.facility_id,
                    entity_name=h.facility_name,
                    name=h.facility_name,
                    entity_type="HEALTHCARE",
                    current_value=avail_beds,
                    available_capacity_or_quantity=avail_beds,
                    unit="BEDS",
                    unit_or_type="BEDS",
                    status=h.status or "AVAILABLE",
                    location_summary=h.location_address or "Medical Zone",
                    location_name=h.location_address or "Medical Zone",
                ))

        hosp_cursor = db["healthcare_facilities"].find({}).limit(20)
        raw_hosp = await hosp_cursor.to_list(length=20)
        existing_hosp_ids = {h.entity_id for h in healthcare_list}
        for h in raw_hosp:
            h_id = h.get("facility_id") or str(h.get("_id"))
            if h_id not in existing_hosp_ids:
                beds = float(h.get("available_beds") or h.get("beds_available") or 0.0)
                h_name = h.get("name") or h.get("facility_name") or f"Hospital {h_id}"
                loc = h.get("address") or h.get("location_name") or "Medical Center"
                healthcare_list.append(SimulationEntityTarget(
                    entity_id=h_id,
                    entity_name=h_name,
                    name=h_name,
                    entity_type="HEALTHCARE",
                    current_value=beds,
                    available_capacity_or_quantity=beds,
                    unit="BEDS",
                    unit_or_type="BEDS",
                    status=h.get("status", "AVAILABLE"),
                    location_summary=loc,
                    location_name=loc,
                ))

        # 4. Volunteers
        volunteers_list: List[SimulationEntityTarget] = []
        if plan and plan.recommended_volunteers:
            for v in plan.recommended_volunteers:
                volunteers_list.append(SimulationEntityTarget(
                    entity_id=v.volunteer_id,
                    entity_name=f"{v.volunteer_name} ({v.role_or_skill})",
                    name=v.volunteer_name,
                    entity_type="VOLUNTEER",
                    current_value=1.0,
                    available_capacity_or_quantity=1.0,
                    unit="STATUS",
                    unit_or_type=v.role_or_skill or "Responder",
                    status="ASSIGNED",
                    location_summary=v.location_zone or "Field Zone",
                    location_name=v.location_zone or "Field Zone",
                ))

        vol_cursor = db["users"].find({"role": {"$in": ["VOLUNTEER", "volunteer", UserRole.VOLUNTEER.value]}}).limit(20)
        raw_vols = await vol_cursor.to_list(length=20)
        existing_vol_ids = {v.entity_id for v in volunteers_list}
        for v in raw_vols:
            v_id = str(v.get("id") or v.get("_id"))
            if v_id not in existing_vol_ids:
                v_name = v.get("full_name") or f"Volunteer {v_id}"
                skill = v.get("volunteer_profile", {}).get("skill_primary", "Responder")
                volunteers_list.append(SimulationEntityTarget(
                    entity_id=v_id,
                    entity_name=f"{v_name} ({skill})",
                    name=v_name,
                    entity_type="VOLUNTEER",
                    current_value=1.0,
                    available_capacity_or_quantity=1.0,
                    unit="STATUS",
                    unit_or_type=skill,
                    status="AVAILABLE",
                    location_summary="Volunteer Pool",
                    location_name="Volunteer Pool",
                ))

        # 5. Transports / Vehicles
        transports_list: List[SimulationEntityTarget] = []
        if plan and plan.recommended_transports:
            for t in plan.recommended_transports:
                transports_list.append(SimulationEntityTarget(
                    entity_id=t.transport_id,
                    entity_name=f"{t.vehicle_name} ({t.vehicle_type})",
                    name=t.vehicle_name,
                    entity_type="TRANSPORT",
                    current_value=t.capacity,
                    available_capacity_or_quantity=float(t.capacity),
                    unit="KG_CAPACITY",
                    unit_or_type=t.vehicle_type or "VEHICLE",
                    status="AVAILABLE",
                    location_summary=t.location_address or "Fleet Depot",
                    location_name=t.location_address or "Fleet Depot",
                ))

        # 6. Routes
        routes_list: List[SimulationEntityTarget] = []
        if plan and plan.recommended_routes:
            for r in plan.recommended_routes:
                routes_list.append(SimulationEntityTarget(
                    entity_id=r.route_id,
                    entity_name=f"{r.origin_name} -> {r.destination_name} ({r.distance_km} km)",
                    name=f"{r.origin_name} to {r.destination_name}",
                    entity_type="ROUTE",
                    current_value=1.0,
                    available_capacity_or_quantity=1.0,
                    unit="STATUS",
                    unit_or_type="ROAD_CORRIDOR",
                    status=r.road_condition_status or "PASSABLE",
                    location_summary=f"{r.origin_name} to {r.destination_name}",
                    location_name=f"{r.origin_name} to {r.destination_name}",
                ))

        total_cnt = (
            len(resources_list)
            + len(shelters_list)
            + len(healthcare_list)
            + len(volunteers_list)
            + len(transports_list)
            + len(routes_list)
        )

        return SimulationTargetLookupResponse(
            situation_id=clean_sit_id,
            situation_name=sit_name,
            baseline_plan_id=baseline_plan_id,
            baseline_plan_version=baseline_version,
            baseline_plan_status=baseline_status,
            baseline_plan_activated_at=baseline_activated_at,
            has_active_baseline=has_active,
            resources=resources_list,
            shelters=shelters_list,
            healthcare_facilities=healthcare_list,
            healthcare=healthcare_list,
            volunteers=volunteers_list,
            transports=transports_list,
            routes=routes_list,
            situation_severities=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
            total_count=total_cnt,
        )

    @classmethod
    async def add_scenario(
        cls,
        simulation_id: str,
        payload: AddScenarioRequest,
        officer_actor: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> SimulationScenario:
        """
        Validates server-side that the scenario target exists in real DB, has non-negative constraints,
        and does not contradict existing scenarios in this simulation run.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        sim_doc = await db["simulations"].find_one({"simulation_id": simulation_id})
        if not sim_doc:
            raise ValueError(f"Simulation '{simulation_id}' not found.")

        if sim_doc.get("status") not in [SimulationStatus.DRAFT.value, SimulationStatus.COMPLETED.value]:
            raise ValueError(f"Cannot add scenarios to simulation in status '{sim_doc.get('status')}'.")

        target_id = str(payload.target_entity_id).strip()
        target_type = payload.target_entity_type.upper()
        target_name = payload.target_entity_name or target_id
        previous_val: Any = None
        affected_fields = []

        # 1. Authoritative Target Validation & Real Baseline Extraction
        if target_type == "RESOURCE":
            res_doc = await db["resources"].find_one({"$or": [{"resource_id": target_id}, {"_id": target_id}]})
            if not res_doc:
                # Check baseline plan allocations
                sit_id = sim_doc.get("situation_id")
                plan_doc = await db["coordination_plans"].find_one({"situation_id": sit_id, "status": CoordinationPlanStatus.ACTIVE.value})
                if plan_doc:
                    for a in plan_doc.get("recommended_allocations", []):
                        if a.get("matched_resource_id") == target_id or a.get("resource_type") == target_id:
                            target_name = a.get("matched_resource_name") or a.get("resource_type")
                            previous_val = float(a.get("allocated_quantity") or a.get("quantity_required") or 0.0)
                            break
            else:
                target_name = res_doc.get("name") or res_doc.get("item_name") or f"Resource {target_id}"
                previous_val = float(res_doc.get("quantity_available") or res_doc.get("available_quantity") or res_doc.get("quantity") or 0.0)

            if previous_val is None:
                raise ValueError(f"Target Resource '{target_id}' does not exist in authoritative inventory.")

            # Compute simulated value
            sim_val = payload.simulated_value
            if isinstance(sim_val, dict):
                if "reduction_percentage" in sim_val:
                    pct = float(sim_val["reduction_percentage"])
                    computed_qty = max(0.0, float(previous_val) * (1.0 - pct / 100.0))
                    payload.simulated_value = computed_qty
                elif "surge_percentage" in sim_val:
                    pct = float(sim_val["surge_percentage"])
                    computed_qty = float(previous_val) * (1.0 + pct / 100.0)
                    payload.simulated_value = computed_qty
                elif "available_quantity" in sim_val:
                    payload.simulated_value = float(sim_val["available_quantity"])
                elif "quantity" in sim_val:
                    payload.simulated_value = float(sim_val["quantity"])
                else:
                    payload.simulated_value = 0.0

            if payload.scenario_type in [ScenarioType.RESOURCE_QUANTITY_REDUCTION, ScenarioType.RESOURCE_REDUCTION]:
                try:
                    sim_qty = float(payload.simulated_value)
                except (ValueError, TypeError):
                    sim_qty = 0.0
                if sim_qty < 0:
                    raise ValueError("Simulated resource quantity cannot be negative.")
                payload.simulated_value = sim_qty
                affected_fields = ["available_quantity", "allocated_quantity"]
            elif payload.scenario_type in [ScenarioType.RESOURCE_UNAVAILABLE, ScenarioType.SUPPLY_DEPLETED]:
                payload.simulated_value = 0.0
                affected_fields = ["status", "available_quantity"]

        elif target_type in ["SHELTER", "SHELTER_FACILITY"]:
            shl_doc = await db["shelters"].find_one({"$or": [{"shelter_id": target_id}, {"_id": target_id}]})
            if not shl_doc:
                # Also check resources collection
                shl_doc = await db["resources"].find_one({"$or": [{"resource_id": target_id}, {"_id": target_id}]})
            if not shl_doc:
                # Check baseline plan
                sit_id = sim_doc.get("situation_id")
                plan_doc = await db["coordination_plans"].find_one({"situation_id": sit_id, "status": CoordinationPlanStatus.ACTIVE.value})
                if plan_doc:
                    for s in plan_doc.get("recommended_shelters", []):
                        if s.get("shelter_id") == target_id:
                            target_name = s.get("shelter_name")
                            previous_val = float(s.get("remaining_capacity") or s.get("total_capacity") or 0.0)
                            break
            else:
                target_name = shl_doc.get("name") or shl_doc.get("shelter_name") or shl_doc.get("item_name") or f"Shelter {target_id}"
                cap = float(shl_doc.get("capacity") or shl_doc.get("total_capacity") or shl_doc.get("quantity") or 0.0)
                occ = float(shl_doc.get("current_occupancy") or shl_doc.get("occupancy") or 0.0)
                previous_val = max(0.0, cap - occ) if occ > 0 else cap

            if previous_val is None:
                raise ValueError(f"Target Shelter '{target_id}' does not exist in authoritative shelter directory.")

            # Compute simulated value
            sim_val = payload.simulated_value
            if isinstance(sim_val, dict):
                if "reduction_percentage" in sim_val:
                    pct = float(sim_val["reduction_percentage"])
                    payload.simulated_value = max(0.0, float(previous_val) * (1.0 - pct / 100.0))
                elif "capacity_available" in sim_val:
                    payload.simulated_value = float(sim_val["capacity_available"])
                else:
                    payload.simulated_value = 0.0

            if payload.scenario_type in [ScenarioType.SHELTER_CAPACITY_REDUCTION, ScenarioType.FACILITY_OFFLINE]:
                try:
                    sim_cap = float(payload.simulated_value)
                except (ValueError, TypeError):
                    sim_cap = 0.0
                if sim_cap < 0:
                    raise ValueError("Simulated shelter capacity cannot be negative.")
                payload.simulated_value = sim_cap
                affected_fields = ["remaining_capacity", "status"]
            elif payload.scenario_type == ScenarioType.SHELTER_UNAVAILABLE:
                payload.simulated_value = 0.0
                affected_fields = ["status", "remaining_capacity"]

        elif target_type in ["HEALTHCARE", "HEALTHCARE_FACILITY"]:
            hosp_doc = await db["healthcare_facilities"].find_one({"$or": [{"facility_id": target_id}, {"_id": target_id}]})
            if not hosp_doc:
                sit_id = sim_doc.get("situation_id")
                plan_doc = await db["coordination_plans"].find_one({"situation_id": sit_id, "status": CoordinationPlanStatus.ACTIVE.value})
                if plan_doc:
                    for h in plan_doc.get("recommended_facilities", []):
                        if h.get("facility_id") == target_id:
                            target_name = h.get("facility_name")
                            previous_val = float(h.get("available_beds") or 0.0)
                            break
            else:
                target_name = hosp_doc.get("name") or hosp_doc.get("facility_name") or f"Hospital {target_id}"
                previous_val = float(hosp_doc.get("available_beds") or hosp_doc.get("beds_available") or 0.0)

            if previous_val is None:
                raise ValueError(f"Target Healthcare Facility '{target_id}' does not exist in authoritative database.")

            # Compute simulated value
            sim_val = payload.simulated_value
            if isinstance(sim_val, dict):
                if "reduction_percentage" in sim_val:
                    pct = float(sim_val["reduction_percentage"])
                    payload.simulated_value = max(0.0, float(previous_val) * (1.0 - pct / 100.0))
                elif "capacity_available" in sim_val:
                    payload.simulated_value = float(sim_val["capacity_available"])
                else:
                    payload.simulated_value = 0.0

            if payload.scenario_type in [ScenarioType.HEALTHCARE_CAPACITY_REDUCTION, ScenarioType.FACILITY_OFFLINE]:
                try:
                    sim_beds = float(payload.simulated_value)
                except (ValueError, TypeError):
                    sim_beds = 0.0
                if sim_beds < 0:
                    raise ValueError("Simulated hospital beds cannot be negative.")
                payload.simulated_value = sim_beds
                affected_fields = ["available_beds", "status"]
            elif payload.scenario_type == ScenarioType.HEALTHCARE_FACILITY_UNAVAILABLE:
                payload.simulated_value = 0.0
                affected_fields = ["status", "available_beds"]

        elif target_type == "VOLUNTEER":
            vol_doc = await db["users"].find_one({"$or": [{"id": target_id}, {"_id": target_id}, {"user_id": target_id}]})
            if not vol_doc:
                sit_id = sim_doc.get("situation_id")
                plan_doc = await db["coordination_plans"].find_one({"situation_id": sit_id, "status": CoordinationPlanStatus.ACTIVE.value})
                if plan_doc:
                    for v in plan_doc.get("recommended_volunteers", []):
                        if v.get("volunteer_id") == target_id:
                            target_name = v.get("volunteer_name")
                            previous_val = "AVAILABLE"
                            break
            else:
                target_name = vol_doc.get("full_name") or f"Volunteer {target_id}"
                previous_val = "AVAILABLE"

            if previous_val is None:
                raise ValueError(f"Target Volunteer '{target_id}' not found in volunteer responder registry.")
            affected_fields = ["status"]
            payload.simulated_value = "UNAVAILABLE"

        elif target_type == "TRANSPORT":
            target_name = f"Vehicle {target_id}"
            previous_val = "AVAILABLE"
            affected_fields = ["status"]
            payload.simulated_value = "UNAVAILABLE"

        elif target_type == "ROUTE":
            target_name = f"Route {target_id}"
            previous_val = "PASSABLE"
            affected_fields = ["road_condition_status"]
            payload.simulated_value = "BLOCKED"

        elif target_type == "SITUATION":
            sit_doc = await db["situations"].find_one({"$or": [{"situation_id": target_id}, {"_id": target_id}]})
            if not sit_doc:
                raise ValueError(f"Target Situation '{target_id}' not found.")
            target_name = sit_doc.get("title") or sit_doc.get("name") or target_id
            previous_val = sit_doc.get("officer_override_severity") or sit_doc.get("computed_severity_level") or "MEDIUM"
            affected_fields = ["severity"]
            if payload.simulated_value not in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
                raise ValueError("Invalid simulated severity. Must be LOW, MEDIUM, HIGH, or CRITICAL.")

        else:
            raise ValueError(f"Unsupported entity type '{target_type}'.")

        # 2. Scenario Conflict Detection
        existing_scenarios = [SimulationScenario(**s) for s in sim_doc.get("scenarios", [])]
        for s in existing_scenarios:
            if s.target_entity_id == target_id and s.scenario_type == payload.scenario_type:
                raise ValueError(f"SCENARIO_CONFLICT: A scenario modifying {target_name} ({payload.scenario_type.value}) already exists in this simulation.")
            if s.target_entity_id == target_id and s.target_entity_type == target_type:
                # Check contradictory state (e.g. reduction vs unavailable)
                if "UNAVAILABLE" in s.scenario_type.value and "REDUCTION" in payload.scenario_type.value:
                    raise ValueError(f"SCENARIO_CONFLICT: Cannot combine unavailable status with capacity reduction for {target_name}.")

        scenario_id = f"SCN-{uuid.uuid4().hex[:6].upper()}"
        desc = payload.description or f"What if {target_name} changed from {previous_val} to {payload.simulated_value}?"

        new_scenario = SimulationScenario(
            scenario_id=scenario_id,
            scenario_type=payload.scenario_type,
            target_entity_type=target_type,
            target_entity_id=target_id,
            target_entity_name=target_name,
            change_type=payload.scenario_type.value,
            previous_value=previous_val,
            simulated_value=payload.simulated_value,
            affected_fields=affected_fields,
            description=desc,
            created_at=datetime.now(timezone.utc),
        )

        scenario_doc = new_scenario.model_dump()
        scenario_doc["created_at"] = scenario_doc["created_at"].isoformat()

        await db["simulations"].update_one(
            {"simulation_id": simulation_id},
            {
                "$push": {"scenarios": scenario_doc},
                "$set": {"status": SimulationStatus.DRAFT.value},
            }
        )

        return new_scenario

    @classmethod
    async def remove_scenario(
        cls,
        simulation_id: str,
        scenario_id: str,
        officer_actor: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> bool:
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        res = await db["simulations"].update_one(
            {"simulation_id": simulation_id},
            {"$pull": {"scenarios": {"scenario_id": scenario_id}}}
        )
        return res.modified_count > 0

    @classmethod
    async def run_simulation(
        cls,
        simulation_id: str,
        officer_actor: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> RunSimulationResponse:
        """
        Executes isolated simulation analysis on in-memory snapshot and overlay.
        Strictly guarantees ZERO mutation to production collections.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        sim_doc = await db["simulations"].find_one({"simulation_id": simulation_id})
        if not sim_doc:
            raise ValueError(f"Simulation '{simulation_id}' not found.")

        scenarios_raw = sim_doc.get("scenarios", [])
        if not scenarios_raw:
            raise ValueError("Add at least one hypothetical perturbation before running the simulation.")

        # Stale baseline protection
        is_stale, stale_reason = await cls.check_simulation_stale(simulation_id, db)
        if is_stale:
            raise ValueError(f"SIMULATION_BASELINE_STALE: {stale_reason}")

        scenarios = [SimulationScenario(**s) for s in scenarios_raw]
        situation_id = sim_doc.get("situation_id")

        # 1. Fetch Authoritative Snapshot Data (READ-ONLY)
        sit_doc = await db["situations"].find_one({"situation_id": situation_id})
        if not sit_doc:
            sit_doc = await db["situations"].find_one({"_id": situation_id})
        if not sit_doc:
            raise ValueError(f"Situation '{situation_id}' no longer exists.")

        # Resolve authoritative active plan via canonical resolver
        baseline_plan = await cls.get_current_active_plan_for_situation(situation_id, db)
        if not baseline_plan:
            # Check if specific baseline plan ID is available
            plan_doc = await db["coordination_plans"].find_one({
                "plan_id": sim_doc.get("baseline_plan_id"),
                "is_simulation": {"$ne": True},
            })
            if plan_doc and plan_doc.get("status") in [CoordinationPlanStatus.ACTIVE.value, CoordinationPlanStatus.APPROVED.value]:
                baseline_plan = CoordinationPlan(**plan_doc)
            else:
                raise ValueError(
                    "SIMULATION_BASELINE_STALE: No active response plan exists for this situation. "
                    "Activate an authoritative response plan before running What-If Simulation."
                )

        # 2. Check Idempotency Fingerprint
        baseline_fp = baseline_plan.state_fingerprint or compute_situation_state_fingerprint(sit_doc)
        sim_fp = compute_simulation_fingerprint(
            situation_id=situation_id,
            baseline_plan_id=baseline_plan.plan_id,
            baseline_fingerprint=baseline_fp,
            scenarios=scenarios,
        )

        # If already completed with identical fingerprint, return cached result
        if sim_doc.get("status") == SimulationStatus.COMPLETED.value and sim_doc.get("state_fingerprint") == sim_fp:
            logger.info(f"Simulation {simulation_id} hit idempotency cache.")
            diff_res = PlanDiffResult(**sim_doc["diff_result"]) if sim_doc.get("diff_result") else None
            return RunSimulationResponse(
                success=True,
                simulation_id=simulation_id,
                status=SimulationStatus.COMPLETED,
                baseline_plan_id=baseline_plan.plan_id,
                simulated_plan_id=sim_doc.get("result_plan", {}).get("plan_id"),
                total_changes=len(diff_res.items) if diff_res else 0,
                impact_level=sim_doc.get("impact_summary", {}).get("impact_level", "HIGH"),
                explanation=sim_doc.get("simulation_explanation"),
                diff_result=diff_res,
                is_simulation=True,
            )

        # 3. Build In-Memory Simulation Overlay
        # Clone baseline plan state deeply in memory
        sim_priority = baseline_plan.assessed_priority
        sim_allocations: List[PlanRecommendedResource] = [PlanRecommendedResource(**a.model_dump()) for a in baseline_plan.recommended_allocations]
        sim_shelters: List[RecommendedShelter] = [RecommendedShelter(**s.model_dump()) for s in baseline_plan.recommended_shelters]
        sim_facilities: List[RecommendedHealthcareFacility] = [RecommendedHealthcareFacility(**h.model_dump()) for h in baseline_plan.recommended_facilities]
        sim_volunteers: List[RecommendedVolunteerAssignment] = [RecommendedVolunteerAssignment(**v.model_dump()) for v in baseline_plan.recommended_volunteers]
        sim_transports: List[RecommendedTransport] = [RecommendedTransport(**t.model_dump()) for t in baseline_plan.recommended_transports]
        sim_routes: List[RecommendedRoute] = [RecommendedRoute(**r.model_dump()) for r in baseline_plan.recommended_routes]

        affected_domains_set = set()
        affected_agents_set = set()
        simulated_shortfalls: Dict[str, float] = {}
        violated_constraints: List[str] = []
        explanation_bullet_points: List[str] = []

        # Apply each scenario to the in-memory overlay in deterministic order
        for scn in scenarios:
            explanation_bullet_points.append(f"WHAT IF: {scn.description}")
            target_id = scn.target_entity_id

            if scn.scenario_type in [ScenarioType.RESOURCE_QUANTITY_REDUCTION, ScenarioType.RESOURCE_UNAVAILABLE]:
                affected_domains_set.add(OperationalDomain.RESOURCE)
                affected_agents_set.add(AgentName.RESOURCE_COORDINATION_AGENT)
                for a in sim_allocations:
                    if a.matched_resource_id == target_id or a.resource_type.value == target_id:
                        if scn.scenario_type == ScenarioType.RESOURCE_QUANTITY_REDUCTION:
                            new_qty = float(scn.simulated_value)
                            shortfall = max(0.0, a.quantity_required - new_qty)
                            a.allocated_quantity = new_qty
                            if shortfall > 0:
                                simulated_shortfalls[a.matched_resource_name or a.resource_type.value] = shortfall
                                violated_constraints.append(f"Resource shortfall of {shortfall} {a.unit} for {a.matched_resource_name or a.resource_type.value}.")
                        elif scn.scenario_type == ScenarioType.RESOURCE_UNAVAILABLE:
                            simulated_shortfalls[a.matched_resource_name or a.resource_type.value] = a.quantity_required
                            a.allocated_quantity = 0.0
                            violated_constraints.append(f"Resource {a.matched_resource_name or a.resource_type.value} became unavailable.")

            elif scn.scenario_type in [ScenarioType.SHELTER_CAPACITY_REDUCTION, ScenarioType.SHELTER_UNAVAILABLE]:
                affected_domains_set.add(OperationalDomain.SHELTER)
                affected_agents_set.add(AgentName.SHELTER_AGENT)
                for s in sim_shelters:
                    if s.shelter_id == target_id:
                        if scn.scenario_type == ScenarioType.SHELTER_CAPACITY_REDUCTION:
                            sim_cap = float(scn.simulated_value)
                            if s.recommended_occupancy > sim_cap:
                                defic = s.recommended_occupancy - sim_cap
                                simulated_shortfalls[f"Shelter {s.shelter_name} Capacity"] = defic
                                violated_constraints.append(f"Shelter {s.shelter_name} capacity reduced by {defic:g} beds below allocation.")
                                s.recommended_occupancy = sim_cap
                            s.remaining_capacity = max(0.0, sim_cap - s.recommended_occupancy)
                        elif scn.scenario_type == ScenarioType.SHELTER_UNAVAILABLE:
                            s.status = "UNAVAILABLE"
                            simulated_shortfalls[f"Shelter {s.shelter_name}"] = s.recommended_occupancy
                            violated_constraints.append(f"Shelter {s.shelter_name} declared unavailable / closed.")
                            s.recommended_occupancy = 0.0
                            s.remaining_capacity = 0.0

            elif scn.scenario_type in [ScenarioType.HEALTHCARE_CAPACITY_REDUCTION, ScenarioType.HEALTHCARE_FACILITY_UNAVAILABLE]:
                affected_domains_set.add(OperationalDomain.HEALTHCARE)
                affected_agents_set.add(AgentName.HEALTHCARE_AGENT)
                for h in sim_facilities:
                    if h.facility_id == target_id:
                        if scn.scenario_type == ScenarioType.HEALTHCARE_CAPACITY_REDUCTION:
                            sim_beds = float(scn.simulated_value)
                            if h.allocated_patients > sim_beds:
                                defic = h.allocated_patients - sim_beds
                                simulated_shortfalls[f"Hospital {h.facility_name} Beds"] = defic
                                violated_constraints.append(f"Hospital {h.facility_name} bed reduction causes {defic:g} patient displacement.")
                                h.allocated_patients = sim_beds
                            h.available_beds = sim_beds
                        elif scn.scenario_type == ScenarioType.HEALTHCARE_FACILITY_UNAVAILABLE:
                            h.status = "UNAVAILABLE"
                            simulated_shortfalls[f"Hospital {h.facility_name}"] = h.allocated_patients
                            violated_constraints.append(f"Hospital {h.facility_name} offline.")
                            h.allocated_patients = 0.0

            elif scn.scenario_type in [ScenarioType.VOLUNTEER_UNAVAILABLE, ScenarioType.VOLUNTEER_SHORTAGE]:
                affected_domains_set.add(OperationalDomain.VOLUNTEER)
                affected_agents_set.add(AgentName.VOLUNTEER_AGENT)
                sim_volunteers = [v for v in sim_volunteers if v.volunteer_id != target_id]
                violated_constraints.append(f"Volunteer responder {scn.target_entity_name} became unavailable.")

            elif scn.scenario_type == ScenarioType.VEHICLE_UNAVAILABLE:
                affected_domains_set.add(OperationalDomain.TRANSPORT)
                affected_agents_set.add(AgentName.ROUTE_AGENT)
                for t in sim_transports:
                    if t.transport_id == target_id:
                        t.current_status = "UNAVAILABLE"
                        t.allocated_load_or_passengers = 0.0
                violated_constraints.append(f"Vehicle {scn.target_entity_name} out of service.")

            elif scn.scenario_type == ScenarioType.ROUTE_BLOCKED:
                affected_domains_set.add(OperationalDomain.ROUTE)
                affected_domains_set.add(OperationalDomain.TRANSPORT)
                affected_agents_set.add(AgentName.ROUTE_AGENT)
                matched_route = None
                for r in sim_routes:
                    if r.route_id == target_id or scn.target_entity_name in [r.origin_name, r.destination_name, f"{r.origin_name} → {r.destination_name}"]:
                        r.road_condition_status = "BLOCKED"
                        r.estimated_duration_minutes = round(r.estimated_duration_minutes + 15.0, 1)
                        matched_route = r
                        violated_constraints.append(f"Transit route '{r.origin_name} → {r.destination_name}' blocked; rerouting required (+15 min ETA detour).")
                if matched_route and matched_route.transport_id:
                    for t in sim_transports:
                        if t.transport_id == matched_route.transport_id:
                            t.assigned_mission = f"Rerouted via secondary corridor ({matched_route.assigned_mission})"

            elif scn.scenario_type == ScenarioType.SITUATION_SEVERITY_CHANGE:
                affected_domains_set.add(OperationalDomain.SITUATION)
                affected_agents_set.add(AgentName.PRIORITY_AGENT)
                affected_agents_set.add(AgentName.NEEDS_AGENT)
                try:
                    sim_priority = SeverityLevel(str(scn.simulated_value).upper())
                except Exception:
                    sim_priority = SeverityLevel.CRITICAL
                violated_constraints.append(f"Situation severity escalated to {sim_priority.value}.")

        # 4. Resolve Selective Agent Execution Sequence
        affected_agents_list = list(affected_agents_set)
        if not affected_agents_list:
            affected_agents_list = [AgentName.CONFLICT_RESOLUTION_AGENT]
        selective_agents = DynamicReplanningService.resolve_selective_execution_set(affected_agents_list)

        # 5. Execute Simulation Re-Planning Pipeline with In-Memory Overlay
        sim_impact_level = ImpactLevel.CRITICAL if (simulated_shortfalls or len(violated_constraints) > 1) else ImpactLevel.HIGH

        combined_impact = ChangeImpactResult(
            impact_id=f"SIM-IMP-{uuid.uuid4().hex[:6].upper()}",
            event_id=f"SIM-EVT-{simulation_id}",
            situation_id=situation_id,
            coordination_plan_id=baseline_plan.plan_id,
            impact_level=sim_impact_level,
            plan_status=PlanValidityStatus.REQUIRES_OFFICER_REVIEW,
            changed_entity=f"Simulation ({len(scenarios)} What-If Changes)",
            changed_fields=[s.target_entity_type for s in scenarios],
            previous_state={"baseline_plan": baseline_plan.plan_id},
            new_state={"simulated_scenarios": len(scenarios)},
            affected_domains=list(affected_domains_set),
            affected_agents=affected_agents_list,
            dependency_chain=selective_agents,
            affected_plan_components=[s.target_entity_id for s in scenarios],
            violated_constraints=violated_constraints,
            shortfalls=simulated_shortfalls,
            officer_attention_required=True,
            explanation="; ".join(violated_constraints) if violated_constraints else "Simulation conditions evaluated.",
        )

        actor_dict = officer_actor or {"id": "OFFICER", "full_name": "Emergency Officer", "role": "EMERGENCY_OFFICER"}

        # Build structured explanation
        explanation_lines = [
            f"WHAT IF ANALYSIS for Situation '{sim_doc.get('situation_name')}' (Baseline Plan: {baseline_plan.plan_id} v{baseline_plan.version}).",
            f"Simulated Changes Applied: {len(scenarios)}.",
        ]
        for b in explanation_bullet_points:
            explanation_lines.append(f"  • {b}")
        if simulated_shortfalls:
            shortfall_str = ", ".join([f"{k}: {v}" for k, v in simulated_shortfalls.items()])
            explanation_lines.append(f"Simulated Shortfalls Detected: {shortfall_str}.")
        explanation_lines.append(f"Selectively evaluated agents in simulation mode: {', '.join([a.value for a in selective_agents])}.")
        explanation_lines.append("IMPORTANT: This is an isolated what-if simulation. Zero real operational state or active plans were modified.")
        structured_sim_explanation = "\n".join(explanation_lines)

        # Build simulated conflicts
        sim_conflicts: List[DetectedConflict] = []
        for res_name, shortfall_qty in simulated_shortfalls.items():
            sim_conflicts.append(
                DetectedConflict(
                    conflict_id=f"CNF-SIM-{uuid.uuid4().hex[:6].upper()}",
                    conflict_type=ConflictType.RESOURCE_SHORTAGE,
                    severity=SeverityLevel.HIGH,
                    description=f"Simulated shortage for {res_name}: deficit of {shortfall_qty} units/capacity under hypothetical perturbation.",
                    affected_resource=res_name,
                    shortfall=float(shortfall_qty),
                    resolution_status=ConflictStatus.UNRESOLVED,
                    officer_attention_required=True,
                    explanation=f"Hypothetical scenario created an operational shortfall of {shortfall_qty} for {res_name}.",
                    alternative_options=["Request mutual aid depot transfer", "Adjust evacuation quota to secondary facility", "Reallocate from low-priority zones"],
                )
            )

        sim_conflict_summary = ConflictResolutionSummary(
            conflicts_detected=sim_conflicts,
            conflicts_count=len(sim_conflicts),
            resolved_conflicts=0,
            unresolved_conflicts=len(sim_conflicts),
            resolution_actions=["Flagged for Emergency Officer review during what-if analysis"],
            affected_resources=list(simulated_shortfalls.keys()),
            shortages=[{"resource": k, "shortfall": v} for k, v in simulated_shortfalls.items()],
            officer_attention_required=len(sim_conflicts) > 0,
            explanation=f"Simulation identified {len(sim_conflicts)} operational conflict(s)." if sim_conflicts else "Zero operational conflicts under simulated scenario.",
        )

        # Synthesize Simulated Coordination Plan
        sim_plan_id = f"SIM-{baseline_plan.plan_id}-S{baseline_plan.version + 1}"
        sim_plan = CoordinationPlan(
            plan_id=sim_plan_id,
            situation_id=situation_id,
            version=baseline_plan.version,
            state_fingerprint=sim_fp,
            generated_at=datetime.now(timezone.utc),
            participating_agents=selective_agents,
            agent_results=baseline_plan.agent_results,
            assessed_priority=sim_priority,
            assessed_needs=baseline_plan.assessed_needs,
            recommended_allocations=sim_allocations,
            conflicts=sim_conflicts,
            conflict_summary=sim_conflict_summary,
            recommended_shelters=sim_shelters,
            shelter_summary=baseline_plan.shelter_summary,
            recommended_facilities=sim_facilities,
            healthcare_summary=baseline_plan.healthcare_summary,
            recommended_volunteers=sim_volunteers,
            volunteer_summary=baseline_plan.volunteer_summary,
            recommended_transports=sim_transports,
            recommended_routes=sim_routes,
            route_summary=baseline_plan.route_summary,
            officer_attention_required=True,
            has_unresolved_conflicts=len(simulated_shortfalls) > 0,
            reasoning=structured_sim_explanation,
            constraints=violated_constraints if violated_constraints else ["Simulated operational constraints."],
            confidence=0.95,
            status=CoordinationPlanStatus.SIMULATION_RESULT,
            officer_review=None,
            previous_plan_id=baseline_plan.plan_id,
            previous_version=baseline_plan.version,
            trigger_event_id=f"SIM-EVT-{simulation_id}",
            impact_id=combined_impact.impact_id,
            is_revised_version=True,
            change_explanation=structured_sim_explanation,
        )

        # 6. Compute Deterministic Plan Diff (Baseline vs Simulation)
        plan_diff = DynamicReplanningService.compute_plan_diff(
            previous_plan=baseline_plan,
            revised_plan=sim_plan,
            impact=combined_impact,
        )
        sim_plan.diff_summary = plan_diff.model_dump()

        # 7. Update Simulation Record in `simulations` Collection ONLY (ZERO real DB mutation)
        completed_at = datetime.now(timezone.utc)
        sim_plan_doc = sim_plan.model_dump()
        sim_plan_doc["generated_at"] = sim_plan_doc["generated_at"].isoformat()
        if sim_plan_doc.get("diff_summary") and sim_plan_doc["diff_summary"].get("generated_at"):
            sim_plan_doc["diff_summary"]["generated_at"] = sim_plan_doc["diff_summary"]["generated_at"].isoformat()

        diff_doc = plan_diff.model_dump()
        diff_doc["generated_at"] = diff_doc["generated_at"].isoformat()

        impact_doc = combined_impact.model_dump()
        impact_doc["analyzed_at"] = impact_doc["analyzed_at"].isoformat()

        await db["simulations"].update_one(
            {"simulation_id": simulation_id},
            {
                "$set": {
                    "status": SimulationStatus.COMPLETED.value,
                    "completed_at": completed_at.isoformat(),
                    "state_fingerprint": sim_fp,
                    "impact_summary": impact_doc,
                    "result_plan": sim_plan_doc,
                    "diff_result": diff_doc,
                    "simulation_explanation": structured_sim_explanation,
                }
            }
        )

        # Record simulation audit log
        await db["simulation_audit_logs"].insert_one({
            "event_id": f"AUD-SIM-{uuid.uuid4().hex[:6].upper()}",
            "simulation_id": simulation_id,
            "action": TimelineEventType.SIMULATION_COMPLETED.value,
            "actor_id": actor_dict.get("id"),
            "actor_name": actor_dict.get("full_name"),
            "situation_id": situation_id,
            "baseline_plan_id": baseline_plan.plan_id,
            "details": f"What-If Simulation {simulation_id} successfully executed ({len(scenarios)} scenarios).",
            "timestamp": completed_at.isoformat(),
        })

        # Phase 7: Event-Driven Isolated Simulation Notification (In-App Only, Initiator Only)
        try:
            from app.services.notification import get_notification_service
            from app.models.enums import NotificationCategory, NotificationSeverity

            initiator_id = actor_dict.get("id") or sim_doc.get("created_by_id")
            if initiator_id:
                notif_service = get_notification_service()
                await notif_service.dispatch_event(
                    category=NotificationCategory.WHAT_IF_SIMULATION,
                    event_type="SIMULATION_COMPLETED",
                    severity=NotificationSeverity.LOW,
                    title=f"[SIMULATION] What-If Analysis Completed: {sim_doc.get('simulation_name') or simulation_id}",
                    message=f"Simulated {len(scenarios)} scenario(s) on baseline plan {baseline_plan.plan_id}. Impact: {combined_impact.impact_level.value}.",
                    event_id=f"SIM-EVT-{simulation_id}",
                    entity_type="SIMULATION",
                    entity_id=simulation_id,
                    situation_id=situation_id,
                    view_hint="simulation",
                    target_user_ids=[initiator_id],
                    is_simulation=True,  # Guarantees zero WhatsApp escalation
                    material_state={"simulation_id": simulation_id, "status": SimulationStatus.COMPLETED.value},
                    metadata={
                        "simulation_id": simulation_id,
                        "simulation_name": sim_doc.get("simulation_name"),
                        "impact_level": combined_impact.impact_level.value,
                        "is_simulation": True,
                    },
                )
        except Exception as sim_notif_err:
            logger.warning(f"Notification notice on simulation completion {simulation_id}: {sim_notif_err}")

        logger.info(f"Simulation {simulation_id} completed successfully (is_simulation=True, zero DB mutation).")

        return RunSimulationResponse(
            success=True,
            simulation_id=simulation_id,
            status=SimulationStatus.COMPLETED,
            baseline_plan_id=baseline_plan.plan_id,
            simulated_plan_id=sim_plan.plan_id,
            total_changes=len(plan_diff.items),
            impact_level=sim_impact_level.value,
            explanation=structured_sim_explanation,
            diff_result=plan_diff,
            is_simulation=True,
        )

    @classmethod
    async def check_simulation_stale(
        cls,
        simulation_id: str,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> tuple[bool, str]:
        """
        Compares baseline state fingerprint vs current reality. Marks simulation STALE if diverged.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        sim_doc = await db["simulations"].find_one({"simulation_id": simulation_id})
        if not sim_doc:
            return True, "Simulation not found."

        sit_id = sim_doc.get("situation_id")
        sit_doc = await db["situations"].find_one({"situation_id": sit_id})
        if not sit_doc:
            sit_doc = await db["situations"].find_one({"_id": sit_id})
        if not sit_doc:
            return True, "Associated situation no longer exists."

        # Fetch current authoritative active plan via canonical resolver
        active_plan = await cls.get_current_active_plan_for_situation(sit_id, db)
        if not active_plan:
            return True, "No active response plan exists for this situation."

        if active_plan.plan_id != sim_doc.get("baseline_plan_id") or active_plan.version != sim_doc.get("baseline_plan_version"):
            # Update status to STALE
            await db["simulations"].update_one(
                {"simulation_id": simulation_id},
                {"$set": {"status": SimulationStatus.STALE.value}}
            )
            return True, f"The live response state changed (active plan upgraded from v{sim_doc.get('baseline_plan_version')} to v{active_plan.version}). Create a new simulation from the current active plan."

        curr_sit_fp = compute_situation_state_fingerprint(sit_doc)
        if sim_doc.get("baseline_fingerprint") and curr_sit_fp != sim_doc.get("baseline_fingerprint"):
            await db["simulations"].update_one(
                {"simulation_id": simulation_id},
                {"$set": {"status": SimulationStatus.STALE.value}}
            )
            return True, "The live response state changed after this simulation was created. Create a new simulation from the current active plan."

        return False, "Simulation baseline is current."

    @classmethod
    async def discard_simulation(
        cls,
        simulation_id: str,
        officer_actor: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> bool:
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        actor_id = officer_actor.get("id", "OFFICER") if officer_actor else "OFFICER"
        actor_name = officer_actor.get("full_name", "Emergency Officer") if officer_actor else "Emergency Officer"

        res = await db["simulations"].update_one(
            {"simulation_id": simulation_id},
            {"$set": {"status": SimulationStatus.DISCARDED.value}}
        )

        if res.modified_count > 0:
            await db["simulation_audit_logs"].insert_one({
                "event_id": f"AUD-SIM-{uuid.uuid4().hex[:6].upper()}",
                "simulation_id": simulation_id,
                "action": TimelineEventType.SIMULATION_DISCARDED.value,
                "actor_id": actor_id,
                "actor_name": actor_name,
                "details": f"Simulation {simulation_id} discarded by officer {actor_name}.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "is_simulation": True,
            })
            return True
        return False
