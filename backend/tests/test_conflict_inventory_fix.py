import pytest
from datetime import datetime, timezone
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.enums import (
    ResourceType,
    ResourceStatus,
    ResourceCondition,
    SeverityLevel,
    NeedUrgency,
    ConflictType,
    ResolutionStrategy,
    ConflictStatus,
    CoordinationPlanStatus,
    AgentName,
)
from app.models.agent import AgentContext, PlanRecommendedResource
from app.services.agents.adapters.conflict_agent import ConflictResolutionAgent
from app.services.agents.adapters.resource_agent import ResourceCoordinationAgent
from app.services.agents.orchestrator import central_orchestrator, compute_situation_state_fingerprint
from app.services.resource_matching import match_resources_for_needs
from app.models.resource import EmergencyNeedItem
from app.db.mongodb import db_manager


# =========================================================================
# GENERIC TEST MATRIX (CASES A - P)
# =========================================================================

@pytest.mark.anyio
async def test_case_a_water_partial_shortfall():
    """CASE A: Water -> Required = 100, Available = 70 -> Shortfall = 30."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CASE-A",
        situation_title="Flood Zone Water Relief",
        emergency_type="Flood",
        description="Potable water needed.",
        location_summary="Vijayawada Sector 1",
        parameters={
            "assessed_needs": [
                {"resource_type": "Water", "requested_quantity": 100.0, "unit": "Litres", "urgency": "HIGH"}
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Water",
                    "quantity_required": 100.0,
                    "unit": "Litres",
                    "urgency": "HIGH",
                    "matched_resource_id": "RES-WATER-01",
                    "matched_resource_name": "Municipal Water Reserve",
                    "available_in_inventory": 70.0,
                    "allocated_quantity": 70.0,
                }
            ],
            "effective_priority": "HIGH",
        },
    )
    result = await agent.execute(context)
    assert result.status.value == "COMPLETED"
    conflicts = result.structured_output["conflicts_detected"]
    assert len(conflicts) == 1
    conf = conflicts[0]
    assert conf["conflict_type"] == ConflictType.INSUFFICIENT_QUANTITY.value
    assert conf["detected_quantity"] == 100.0
    assert conf["available_quantity"] == 70.0
    assert conf["shortfall"] == 30.0
    assert "70" in conf["explanation"] and "30" in conf["explanation"]


@pytest.mark.anyio
async def test_case_b_food_partial_shortfall():
    """CASE B: Food -> Required = 200, Available = 120 -> Shortfall = 80."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CASE-B",
        situation_title="Cyclone Relief Camp",
        emergency_type="Cyclone",
        description="Ration packets needed.",
        location_summary="Machilipatnam Coastal Hub",
        parameters={
            "assessed_needs": [
                {"resource_type": "Food", "requested_quantity": 200.0, "unit": "Packets", "urgency": "HIGH"}
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Food",
                    "quantity_required": 200.0,
                    "unit": "Packets",
                    "urgency": "HIGH",
                    "matched_resource_id": "RES-FOOD-01",
                    "matched_resource_name": "Civil Supplies Godown",
                    "available_in_inventory": 120.0,
                    "allocated_quantity": 120.0,
                }
            ],
            "effective_priority": "HIGH",
        },
    )
    result = await agent.execute(context)
    conflicts = result.structured_output["conflicts_detected"]
    assert len(conflicts) == 1
    conf = conflicts[0]
    assert conf["conflict_type"] == ConflictType.INSUFFICIENT_QUANTITY.value
    assert conf["detected_quantity"] == 200.0
    assert conf["available_quantity"] == 120.0
    assert conf["shortfall"] == 80.0
    assert "120" in conf["explanation"] and "80" in conf["explanation"]


@pytest.mark.anyio
async def test_case_c_rescue_equipment_shortfall():
    """CASE C: Rescue Equipment -> Required = 20, Available = 8 -> Shortfall = 12."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CASE-C",
        situation_title="Landslide Rescue Operation",
        emergency_type="Landslide",
        description="Hydraulic rescue cutters needed.",
        location_summary="Hillside Sector 3",
        parameters={
            "assessed_needs": [
                {"resource_type": "Rescue Equipment", "requested_quantity": 20.0, "unit": "Units", "urgency": "CRITICAL"}
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Rescue Equipment",
                    "quantity_required": 20.0,
                    "unit": "Units",
                    "urgency": "CRITICAL",
                    "matched_resource_id": "RES-RESCUE-01",
                    "matched_resource_name": "Fire & Rescue Station",
                    "available_in_inventory": 8.0,
                    "allocated_quantity": 8.0,
                }
            ],
            "effective_priority": "CRITICAL",
        },
    )
    result = await agent.execute(context)
    conflicts = result.structured_output["conflicts_detected"]
    assert len(conflicts) == 1
    conf = conflicts[0]
    assert conf["conflict_type"] == ConflictType.INSUFFICIENT_QUANTITY.value
    assert conf["detected_quantity"] == 20.0
    assert conf["available_quantity"] == 8.0
    assert conf["shortfall"] == 12.0


@pytest.mark.anyio
async def test_case_d_first_aid_kits_shortfall():
    """CASE D: First Aid Kits -> Required = 30, Available = 25 -> Shortfall = 5."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CASE-D",
        situation_title="Urban Building Incident",
        emergency_type="Structural",
        description="Emergency first aid kits needed.",
        location_summary="Downtown Hub",
        parameters={
            "assessed_needs": [
                {"resource_type": "Medical", "requested_quantity": 30.0, "unit": "Kits", "urgency": "HIGH"}
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Medical",
                    "quantity_required": 30.0,
                    "unit": "Kits",
                    "urgency": "HIGH",
                    "matched_resource_id": "RES-MED-01",
                    "matched_resource_name": "Red Cross Medical Cache",
                    "available_in_inventory": 25.0,
                    "allocated_quantity": 25.0,
                }
            ],
            "effective_priority": "HIGH",
        },
    )
    result = await agent.execute(context)
    conflicts = result.structured_output["conflicts_detected"]
    assert len(conflicts) == 1
    conf = conflicts[0]
    assert conf["conflict_type"] == ConflictType.INSUFFICIENT_QUANTITY.value
    assert conf["detected_quantity"] == 30.0
    assert conf["available_quantity"] == 25.0
    assert conf["shortfall"] == 5.0


@pytest.mark.anyio
async def test_case_e_fully_satisfied_need_no_conflict():
    """CASE E: Required = 100, Available = 100 -> Shortfall = 0, NO shortage conflict."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CASE-E",
        situation_title="Relief Distribution",
        emergency_type="Flood",
        description="Blankets needed.",
        location_summary="Sector 5",
        parameters={
            "assessed_needs": [
                {"resource_type": "Blankets", "requested_quantity": 100.0, "unit": "Units", "urgency": "HIGH"}
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Blankets",
                    "quantity_required": 100.0,
                    "unit": "Units",
                    "urgency": "HIGH",
                    "matched_resource_id": "RES-BLK-01",
                    "matched_resource_name": "Disaster Logistics Depot",
                    "available_in_inventory": 100.0,
                    "allocated_quantity": 100.0,
                }
            ],
            "effective_priority": "HIGH",
        },
    )
    result = await agent.execute(context)
    conflicts = result.structured_output["conflicts_detected"]
    shortage_confs = [c for c in conflicts if c["conflict_type"] in [ConflictType.RESOURCE_SHORTAGE.value, ConflictType.INSUFFICIENT_QUANTITY.value]]
    assert len(shortage_confs) == 0


@pytest.mark.anyio
async def test_case_f_surplus_inventory_no_conflict():
    """CASE F: Required = 100, Available = 130 -> Shortfall = 0, NO shortage conflict."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CASE-F",
        situation_title="Relief Operations",
        emergency_type="Flood",
        description="Tarpaulins needed.",
        location_summary="Sector 5",
        parameters={
            "assessed_needs": [
                {"resource_type": "Shelter", "requested_quantity": 100.0, "unit": "Tarpaulins", "urgency": "HIGH"}
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Shelter",
                    "quantity_required": 100.0,
                    "unit": "Tarpaulins",
                    "urgency": "HIGH",
                    "matched_resource_id": "RES-TRP-01",
                    "matched_resource_name": "Central Warehouse",
                    "available_in_inventory": 130.0,
                    "allocated_quantity": 100.0,
                }
            ],
            "effective_priority": "HIGH",
        },
    )
    result = await agent.execute(context)
    conflicts = result.structured_output["conflicts_detected"]
    shortage_confs = [c for c in conflicts if c["conflict_type"] in [ConflictType.RESOURCE_SHORTAGE.value, ConflictType.INSUFFICIENT_QUANTITY.value]]
    assert len(shortage_confs) == 0


@pytest.mark.anyio
async def test_case_g_zero_inventory_shortfall():
    """CASE G: Required = 100, Available = 0 -> Shortfall = 100, Zero-inventory conflict."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CASE-G",
        situation_title="Zero Inventory Scenario",
        emergency_type="Flood",
        description="Boats needed.",
        location_summary="Delta Sector",
        parameters={
            "assessed_needs": [
                {"resource_type": "Boats", "requested_quantity": 100.0, "unit": "Boats", "urgency": "CRITICAL"}
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Boats",
                    "quantity_required": 100.0,
                    "unit": "Boats",
                    "urgency": "CRITICAL",
                    "matched_resource_id": None,
                    "matched_resource_name": None,
                    "available_in_inventory": 0.0,
                    "allocated_quantity": 0.0,
                }
            ],
            "effective_priority": "CRITICAL",
        },
    )
    result = await agent.execute(context)
    conflicts = result.structured_output["conflicts_detected"]
    assert len(conflicts) == 1
    conf = conflicts[0]
    assert conf["conflict_type"] == ConflictType.RESOURCE_SHORTAGE.value
    assert conf["detected_quantity"] == 100.0
    assert conf["available_quantity"] == 0.0
    assert conf["shortfall"] == 100.0
    assert "Zero available inventory" in conf["description"]


@pytest.mark.anyio
async def test_case_h_multi_source_inventory():
    """CASE H: Multi-source inventory -> Required = 100, Source A=30, Source B=40, Source C=20 -> Available = 90, Shortfall = 10."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CASE-H",
        situation_title="Multi-depot Supply Chain",
        emergency_type="Flood",
        description="Drinking water aggregation across depots.",
        location_summary="Krishna Basin",
        parameters={
            "assessed_needs": [
                {"resource_type": "Water", "requested_quantity": 100.0, "unit": "Litres", "urgency": "HIGH"}
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Water",
                    "quantity_required": 100.0,
                    "unit": "Litres",
                    "urgency": "HIGH",
                    "matched_resource_id": "RES-DEPOT-A",
                    "matched_resource_name": "Depot Alpha",
                    "available_in_inventory": 30.0,
                    "allocated_quantity": 30.0,
                },
                {
                    "resource_type": "Water",
                    "quantity_required": 100.0,
                    "unit": "Litres",
                    "urgency": "HIGH",
                    "matched_resource_id": "RES-DEPOT-B",
                    "matched_resource_name": "Depot Beta",
                    "available_in_inventory": 40.0,
                    "allocated_quantity": 40.0,
                },
                {
                    "resource_type": "Water",
                    "quantity_required": 100.0,
                    "unit": "Litres",
                    "urgency": "HIGH",
                    "matched_resource_id": "RES-DEPOT-C",
                    "matched_resource_name": "Depot Gamma",
                    "available_in_inventory": 20.0,
                    "allocated_quantity": 20.0,
                },
            ],
            "effective_priority": "HIGH",
        },
    )
    result = await agent.execute(context)
    conflicts = result.structured_output["conflicts_detected"]
    assert len(conflicts) == 1
    conf = conflicts[0]
    assert conf["conflict_type"] == ConflictType.INSUFFICIENT_QUANTITY.value
    assert conf["detected_quantity"] == 100.0
    assert conf["available_quantity"] == 90.0
    assert conf["shortfall"] == 10.0
    assert "90" in conf["explanation"] and "10" in conf["explanation"]


@pytest.mark.anyio
async def test_case_i_unavailable_facility_excluded():
    """CASE I: Inventory in UNAVAILABLE/MAINTENANCE status is NOT counted as usable inventory."""
    db = db_manager.db
    now = datetime.now(timezone.utc)
    res_id_unavail = f"RES-UNAVAIL-{now.strftime('%H%M%S')}"

    # Insert resource with UNAVAILABLE status
    await db["resources"].insert_one({
        "resource_id": res_id_unavail,
        "name": "Flooded Flood Depot",
        "resource_type": "Food",
        "quantity_total": 500.0,
        "quantity_available": 500.0,
        "unit": "Packets",
        "status": "UNAVAILABLE",  # Closed/Flooded
        "condition": "POOR",
        "location": {"latitude": 16.5062, "longitude": 80.6480},
        "created_at": now,
        "updated_at": now,
    })

    # Query using standard matching
    need_items = [EmergencyNeedItem(
        resource_type=ResourceType.FOOD,
        requested_quantity=100.0,
        unit="Packets",
        urgency=NeedUrgency.HIGH,
        reason="Food needed",
    )]

    match_resp = await match_resources_for_needs(
        db=db,
        report_id="REP-TEST-I",
        report_location={"latitude": 16.5062, "longitude": 80.6480},
        needs=need_items,
    )

    # Unavailable facility must NOT be in candidates list
    cand_ids = [c.resource_id for c in match_resp.needs_matches[0].candidates]
    assert res_id_unavail not in cand_ids


@pytest.mark.anyio
async def test_case_j_healthcare_capacity_conflict():
    """CASE J: Healthcare -> Required = 20 beds, Available = 12 beds -> Shortfall = 8 beds."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CASE-J",
        situation_title="Mass Casualty Incident",
        emergency_type="Industrial",
        description="Hospital emergency bed requirement.",
        location_summary="Industrial Corridor",
        parameters={
            "assessed_needs": [],
            "healthcare_shortfall": 8.0,
            "healthcare_summary": {
                "estimated_casualties": 20,
                "total_beds_available": 12.0,
                "total_patients_covered": 12.0,
                "total_shortfall": 8.0,
            },
            "effective_priority": "CRITICAL",
        },
    )
    result = await agent.execute(context)
    conflicts = result.structured_output["conflicts_detected"]
    assert len(conflicts) == 1
    conf = conflicts[0]
    assert conf["conflict_type"] == ConflictType.HEALTHCARE_TRANSPORT_MISMATCH.value
    assert conf["detected_quantity"] == 20.0
    assert conf["available_quantity"] == 12.0
    assert conf["shortfall"] == 8.0
    assert "12" in conf["explanation"] and "8" in conf["explanation"]


@pytest.mark.anyio
async def test_case_k_shelter_capacity_conflict():
    """CASE K: Shelter -> Required = 20, Available capacity = 15 -> Shortfall = 5."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CASE-K",
        situation_title="Coastal Evacuation",
        emergency_type="Cyclone",
        description="Shelter beds needed for evacuees.",
        location_summary="Coastal Zone 2",
        parameters={
            "assessed_needs": [],
            "shelter_shortfall": 5.0,
            "shelter_summary": {
                "affected_population": 20,
                "total_capacity_available": 15.0,
                "total_population_covered": 15.0,
                "total_shortfall": 5.0,
            },
            "effective_priority": "HIGH",
        },
    )
    result = await agent.execute(context)
    conflicts = result.structured_output["conflicts_detected"]
    assert len(conflicts) == 1
    conf = conflicts[0]
    assert conf["conflict_type"] == ConflictType.SHELTER_CAPACITY_CONFLICT.value
    assert conf["detected_quantity"] == 20.0
    assert conf["available_quantity"] == 15.0
    assert conf["shortfall"] == 5.0
    assert "15" in conf["explanation"] and "5" in conf["explanation"]


@pytest.mark.anyio
async def test_case_l_volunteers_shortfall():
    """CASE L: Volunteers -> Required = 10, Eligible active = 7 -> Shortfall = 3."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CASE-L",
        situation_title="Search and Rescue Ops",
        emergency_type="Flood",
        description="Trained SAR volunteers needed.",
        location_summary="Submerged Sector",
        parameters={
            "assessed_needs": [],
            "volunteer_shortfall": 3,
            "volunteer_summary": {
                "volunteers_needed": 10,
                "total_available": 7,
                "total_shortfall": 3,
            },
            "effective_priority": "HIGH",
        },
    )
    result = await agent.execute(context)
    conflicts = result.structured_output["conflicts_detected"]
    assert len(conflicts) == 1
    conf = conflicts[0]
    assert conf["conflict_type"] == ConflictType.VOLUNTEER_AVAILABILITY_CONFLICT.value
    assert conf["detected_quantity"] == 10.0
    assert conf["available_quantity"] == 7.0
    assert conf["shortfall"] == 3.0
    assert "7" in conf["explanation"] and "3" in conf["explanation"]


@pytest.mark.anyio
async def test_case_m_transport_fleet_shortfall():
    """CASE M: Transport -> Required = 5 routes, Eligible available = 2 vehicles -> Shortfall = 3."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CASE-M",
        situation_title="Evacuation Fleet Deployment",
        emergency_type="Flood",
        description="Ambulances and buses needed for routes.",
        location_summary="Transit Zone",
        parameters={
            "assessed_needs": [],
            "transport_shortfall": 3,
            "route_summary": {
                "total_routes_recommended": 5,
                "total_transports_recommended": 2,
                "transport_shortfall": 3,
            },
            "effective_priority": "HIGH",
        },
    )
    result = await agent.execute(context)
    conflicts = result.structured_output["conflicts_detected"]
    assert len(conflicts) == 1
    conf = conflicts[0]
    assert conf["detected_quantity"] == 5.0
    assert conf["available_quantity"] == 2.0
    assert conf["shortfall"] == 3.0
    assert "2" in conf["explanation"] and "3" in conf["explanation"]


@pytest.mark.anyio
async def test_case_n_inventory_changes_reorchestration():
    """CASE N: Inventory changes 0 -> 70 -> Re-run orchestration reflects Available = 70, Shortfall = 30."""
    db = db_manager.db
    now = datetime.now(timezone.utc)
    sit_id = f"SIT-CASE-N-{now.strftime('%H%M%S')}"

    await db["situations"].insert_one({
        "situation_id": sit_id,
        "title": "Severe Coastal Inundation",
        "emergency_type": "Flood",
        "status": "ACTIVE",
        "severity_level": "HIGH",
        "computed_severity_level": "HIGH",
        "severity_score": 8.0,
        "center_location": {"latitude": 16.5062, "longitude": 80.6480},
        "impact_radius_km": 3.0,
        "estimated_affected_population": 500,
        "report_ids": ["REP-N1"],
        "created_at": now,
        "updated_at": now,
    })

    actor = {"id": "OFF-100", "full_name": "Commander Rao", "role": "EMERGENCY_OFFICER"}

    # Initial zero stock
    await db["resources"].delete_many({"resource_type": "Water"})

    plan_v1 = await central_orchestrator.orchestrate_situation(
        situation_id=sit_id,
        actor=actor,
        force_refresh=True,
        db=db,
    )
    water_c_v1 = next((c for c in plan_v1.conflicts if "Water" in str(c.affected_need)), None)
    assert water_c_v1 is not None
    assert water_c_v1.available_quantity == 0.0

    # Stock added in MongoDB
    await db["resources"].insert_one({
        "resource_id": f"RES-WAT-N-{now.strftime('%H%M%S')}",
        "name": "State Emergency Water Cache",
        "resource_type": "Water",
        "quantity_total": 70.0,
        "quantity_available": 70.0,
        "unit": "Litres",
        "status": "AVAILABLE",
        "condition": "GOOD",
        "location": {"latitude": 16.5070, "longitude": 80.6490},
        "created_at": now,
        "updated_at": now,
    })

    # Re-run Orchestration
    plan_v2 = await central_orchestrator.orchestrate_situation(
        situation_id=sit_id,
        actor=actor,
        force_refresh=True,
        db=db,
    )
    water_c_v2 = next((c for c in plan_v2.conflicts if "Water" in str(c.affected_need)), None)
    assert water_c_v2 is not None
    assert water_c_v2.available_quantity == 70.0
    assert water_c_v2.shortfall == max(round(water_c_v2.detected_quantity - 70.0, 2), 0.0)


@pytest.mark.anyio
async def test_case_o_idempotency_without_state_change():
    """CASE O: Unchanged state returns same plan/version without duplicate writes."""
    db = db_manager.db
    now = datetime.now(timezone.utc)
    sit_id = f"SIT-CASE-O-{now.strftime('%H%M%S')}"

    await db["situations"].insert_one({
        "situation_id": sit_id,
        "title": "Idempotency Test Incident",
        "emergency_type": "Flood",
        "status": "ACTIVE",
        "severity_level": "MEDIUM",
        "computed_severity_level": "MEDIUM",
        "center_location": {"latitude": 16.5062, "longitude": 80.6480},
        "report_ids": ["REP-O1"],
        "created_at": now,
        "updated_at": now,
    })

    actor = {"id": "OFF-100", "full_name": "Commander Rao", "role": "EMERGENCY_OFFICER"}

    plan_1 = await central_orchestrator.orchestrate_situation(situation_id=sit_id, actor=actor, db=db)
    plan_2 = await central_orchestrator.orchestrate_situation(situation_id=sit_id, actor=actor, db=db)

    assert plan_1.plan_id == plan_2.plan_id
    assert plan_1.version == plan_2.version


@pytest.mark.anyio
async def test_case_p_universal_invariants_and_zero_mutation():
    """CASE P: Universal mathematical invariants (shortfall >= 0, shortfall == max(req-avail, 0)) and read-only safety."""
    db = db_manager.db
    now = datetime.now(timezone.utc)
    res_id = f"RES-INVAR-{now.strftime('%H%M%S')}"

    await db["resources"].insert_one({
        "resource_id": res_id,
        "name": "Invariant Depot",
        "resource_type": "Medical",
        "quantity_total": 70.0,
        "quantity_available": 70.0,
        "unit": "Kits",
        "status": "AVAILABLE",
        "condition": "GOOD",
        "location": {"latitude": 16.5070, "longitude": 80.6490},
        "created_at": now,
        "updated_at": now,
    })

    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-INVAR",
        situation_title="Invariant Check",
        emergency_type="Earthquake",
        description="Medical supplies needed.",
        location_summary="Zone 1",
        parameters={
            "assessed_needs": [{"resource_type": "Medical", "requested_quantity": 100.0, "unit": "Kits", "urgency": "HIGH"}],
            "recommended_allocations": [
                {
                    "resource_type": "Medical",
                    "quantity_required": 100.0,
                    "unit": "Kits",
                    "urgency": "HIGH",
                    "matched_resource_id": res_id,
                    "matched_resource_name": "Invariant Depot",
                    "available_in_inventory": 70.0,
                    "allocated_quantity": 70.0,
                }
            ],
            "effective_priority": "HIGH",
        },
    )

    result = await agent.execute(context)
    conf = result.structured_output["conflicts_detected"][0]

    # Invariant checks
    req = conf["detected_quantity"]
    avail = conf["available_quantity"]
    sfall = conf["shortfall"]

    assert sfall >= 0.0
    assert sfall == max(round(req - avail, 2), 0.0)
    assert avail <= 70.0

    # Ensure zero mutation in MongoDB
    res_doc = await db["resources"].find_one({"resource_id": res_id})
    assert res_doc["quantity_available"] == 70.0
    assert res_doc["quantity_total"] == 70.0
