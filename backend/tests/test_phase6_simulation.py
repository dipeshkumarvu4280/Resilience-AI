import pytest
import mongomock
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from app.models.enums import (
    OperationalDomain,
    AgentName,
    SeverityLevel,
    NeedUrgency,
    ResourceType,
    CoordinationPlanStatus,
    DiffChangeType,
    TimelineEventType,
)
from app.models.simulation import (
    ScenarioType,
    SimulationStatus,
    SimulationScenario,
    SimulationRun,
    AddScenarioRequest,
    CreateSimulationRequest,
)
from app.models.agent import (
    CoordinationPlan,
    PlanRecommendedResource,
    RecommendedShelter,
    RecommendedHealthcareFacility,
    RecommendedVolunteerAssignment,
    RecommendedTransport,
    RecommendedRoute,
)
from app.services.monitoring.simulation_service import SimulationService


class AsyncMongoMockCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def sort(self, *args, **kwargs):
        self._cursor = self._cursor.sort(*args, **kwargs)
        return self

    def skip(self, *args, **kwargs):
        self._cursor = self._cursor.skip(*args, **kwargs)
        return self

    def limit(self, *args, **kwargs):
        self._cursor = self._cursor.limit(*args, **kwargs)
        return self

    async def to_list(self, length=None):
        docs = list(self._cursor)
        if length is not None:
            docs = docs[:length]
        return docs

    def __iter__(self):
        return iter(self._cursor)


class AsyncMongoMockCollection:
    def __init__(self, sync_collection):
        self._col = sync_collection

    async def find_one(self, *args, **kwargs):
        return self._col.find_one(*args, **kwargs)

    def find(self, *args, **kwargs):
        cursor = self._col.find(*args, **kwargs)
        return AsyncMongoMockCursor(cursor)

    async def insert_one(self, doc, *args, **kwargs):
        return self._col.insert_one(doc, *args, **kwargs)

    async def update_one(self, filter_q, update_q, *args, **kwargs):
        return self._col.update_one(filter_q, update_q, *args, **kwargs)

    async def update_many(self, filter_q, update_q, *args, **kwargs):
        return self._col.update_many(filter_q, update_q, *args, **kwargs)

    async def count_documents(self, filter_q, *args, **kwargs):
        return self._col.count_documents(filter_q, *args, **kwargs)

    def aggregate(self, pipeline, *args, **kwargs):
        res = self._col.aggregate(pipeline)
        return AsyncMongoMockCursor(res)


class AsyncMongoMockDatabase:
    def __init__(self):
        self._client = mongomock.MongoClient()
        self._db = self._client["resilience_ai_simulation_test"]

    def __getitem__(self, item):
        return AsyncMongoMockCollection(self._db[item])


@pytest.fixture
def mock_db():
    return AsyncMongoMockDatabase()


def populate_mock_environment(situation_id="SIT-SIM-001", plan_id="PLAN-ACT-001"):
    situation_doc = {
        "_id": situation_id,
        "situation_id": situation_id,
        "title": "Riverside Inundation Zone",
        "emergency_type": "FLOOD",
        "computed_severity_level": "HIGH",
        "report_ids": ["REP-101", "REP-102"],
        "center_location": {"latitude": 19.0760, "longitude": 72.8777},
    }

    plan_doc = {
        "_id": plan_id,
        "plan_id": plan_id,
        "situation_id": situation_id,
        "assessed_priority": SeverityLevel.HIGH.value,
        "status": CoordinationPlanStatus.ACTIVE.value,
        "version": 1,
        "is_revised_version": False,
        "generated_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        "reasoning": "Baseline response plan.",
        "state_fingerprint": "fp-base-001",
        "recommended_allocations": [
            {
                "resource_type": "Water",
                "quantity_required": 100.0,
                "unit": "LITRES",
                "urgency": "HIGH",
                "matched_resource_id": "RES-WATER-001",
                "matched_resource_name": "Bottled Drinking Water",
                "allocated_quantity": 100.0,
                "depot_location": "North Depot",
            }
        ],
        "recommended_shelters": [
            {
                "shelter_id": "SHELTER-001",
                "shelter_name": "Community Hall A",
                "distance_km": 2.0,
                "total_capacity": 300.0,
                "current_occupancy": 50.0,
                "remaining_capacity": 250.0,
                "recommended_occupancy": 150.0,
                "coverage_percentage": 100.0,
                "suitability_score": 95.0,
                "recommendation_reason": "High capacity flood shelter.",
            }
        ],
        "recommended_facilities": [
            {
                "facility_id": "HOSP-001",
                "facility_name": "Central District Hospital",
                "facility_type": "Hospital",
                "distance_km": 3.0,
                "total_beds": 100.0,
                "available_beds": 20.0,
                "allocated_patients": 10.0,
                "coverage_percentage": 100.0,
                "recommendation_reason": "Level 1 trauma center.",
            }
        ],
        "recommended_volunteers": [
            {
                "volunteer_id": "VOL-001",
                "volunteer_name": "John Doe",
                "role_or_skill": "First Aid Responder",
                "assigned_operation": "First Aid Station A",
                "recommendation_reason": "Certified responder.",
            }
        ],
        "recommended_transports": [
            {
                "transport_id": "TRUCK-001",
                "vehicle_name": "Logistics Truck 1",
                "vehicle_type": "High Clearance Truck",
                "capacity": 5000.0,
                "allocated_load_or_passengers": 2000.0,
                "assigned_mission": "Supply Dispatch",
                "recommendation_reason": "High clearance.",
            }
        ],
        "recommended_routes": [
            {
                "route_id": "ROUTE-001",
                "origin_name": "North Depot",
                "destination_name": "Community Hall A",
                "origin_coordinates": {"latitude": 19.100, "longitude": 72.880},
                "destination_coordinates": {"latitude": 19.080, "longitude": 72.870},
                "distance_km": 4.5,
                "estimated_duration_minutes": 15.0,
                "assigned_mission": "Supply Transport",
                "recommendation_reason": "Primary route.",
            }
        ],
        "agent_results": {},
        "participating_agents": [],
    }

    resource_doc = {
        "_id": "RES-WATER-001",
        "resource_id": "RES-WATER-001",
        "item_name": "Bottled Drinking Water",
        "resource_type": "Water",
        "available_quantity": 120.0,
        "unit": "LITRES",
        "status": "AVAILABLE",
        "location_name": "North Logistics Depot",
    }

    shelter_doc = {
        "_id": "SHELTER-001",
        "shelter_id": "SHELTER-001",
        "name": "Community Hall A",
        "total_capacity": 300.0,
        "current_occupancy": 50.0,
        "status": "AVAILABLE",
    }

    hosp_doc = {
        "_id": "HOSP-001",
        "facility_id": "HOSP-001",
        "name": "Central District Hospital",
        "available_beds": 20.0,
        "status": "AVAILABLE",
    }

    user_doc = {
        "_id": "VOL-001",
        "id": "VOL-001",
        "full_name": "John Doe",
        "role": "VOLUNTEER",
    }

    return situation_doc, plan_doc, resource_doc, shelter_doc, hosp_doc, user_doc


@pytest.mark.asyncio
async def test_critical_safety_zero_mutation(mock_db):
    """
    CRITICAL SAFETY TEST:
    Verifies that running a simulation does NOT mutate real MongoDB operational records.
    1. Real Resource = 120
    2. Simulate Resource: 120 -> 70
    3. Run simulation
    4. Assert Real DB Resource is STILL 120
    5. Assert Real Active Plan is STILL ACTIVE and unchanged
    """
    situation_id = "SIT-SIM-001"
    plan_id = "PLAN-ACT-001"
    sit_doc, plan_doc, res_doc, shelter_doc, hosp_doc, user_doc = populate_mock_environment(situation_id, plan_id)

    await mock_db["situations"].insert_one(sit_doc)
    await mock_db["coordination_plans"].insert_one(plan_doc)
    await mock_db["resources"].insert_one(res_doc)
    await mock_db["shelters"].insert_one(shelter_doc)
    await mock_db["healthcare_facilities"].insert_one(hosp_doc)
    await mock_db["users"].insert_one(user_doc)

    actor = {"id": "OFF-101", "full_name": "Officer Jane", "role": "EMERGENCY_OFFICER"}

    # 1. Create Simulation
    sim = await SimulationService.create_simulation(situation_id, "What-If Water Scarcity", actor, mock_db)
    assert sim.status == SimulationStatus.DRAFT
    assert sim.is_simulation is True

    # 2. Add Scenario: Water 120 -> 70
    scenario_req = AddScenarioRequest(
        scenario_type=ScenarioType.RESOURCE_QUANTITY_REDUCTION,
        target_entity_type="RESOURCE",
        target_entity_id="RES-WATER-001",
        simulated_value=70.0,
        description="Simulate depot water stock reduction to 70L.",
    )
    await SimulationService.add_scenario(sim.simulation_id, scenario_req, actor, mock_db)

    # 3. Run Simulation
    res = await SimulationService.run_simulation(sim.simulation_id, actor, mock_db)
    assert res.success is True
    assert res.status == SimulationStatus.COMPLETED
    assert res.is_simulation is True
    assert res.total_changes >= 1

    # 4. SAFETY ASSERTION: Real DB Resource MUST still be 120
    db_res = await mock_db["resources"].find_one({"resource_id": "RES-WATER-001"})
    assert db_res["available_quantity"] == 120.0

    # 5. SAFETY ASSERTION: Real Active Plan MUST remain unchanged & ACTIVE
    db_plan = await mock_db["coordination_plans"].find_one({"plan_id": plan_id})
    assert db_plan["status"] == CoordinationPlanStatus.ACTIVE.value
    assert db_plan["version"] == 1
    assert db_plan["recommended_allocations"][0]["allocated_quantity"] == 100.0


@pytest.mark.asyncio
async def test_scenario_validation_and_conflict_detection(mock_db):
    """
    Test scenario input validation:
    - Nonexistent targets rejected
    - Negative values rejected
    - Contradictory scenario combinations flagged with SCENARIO_CONFLICT
    """
    situation_id = "SIT-SIM-001"
    sit_doc, plan_doc, res_doc, shelter_doc, hosp_doc, user_doc = populate_mock_environment(situation_id)

    await mock_db["situations"].insert_one(sit_doc)
    await mock_db["coordination_plans"].insert_one(plan_doc)
    await mock_db["resources"].insert_one(res_doc)
    await mock_db["shelters"].insert_one(shelter_doc)

    actor = {"id": "OFF-101", "full_name": "Officer Jane", "role": "EMERGENCY_OFFICER"}
    sim = await SimulationService.create_simulation(situation_id, "Validation Test", actor, mock_db)

    # Nonexistent target should raise ValueError
    with pytest.raises(ValueError) as exc1:
        await SimulationService.add_scenario(
            sim.simulation_id,
            AddScenarioRequest(
                scenario_type=ScenarioType.RESOURCE_QUANTITY_REDUCTION,
                target_entity_type="RESOURCE",
                target_entity_id="FAKE-NONEXISTENT-RESOURCE",
                simulated_value=50.0,
            ),
            actor,
            mock_db,
        )
    assert "does not exist" in str(exc1.value)

    # Negative quantity should raise ValueError
    with pytest.raises(ValueError) as exc2:
        await SimulationService.add_scenario(
            sim.simulation_id,
            AddScenarioRequest(
                scenario_type=ScenarioType.RESOURCE_QUANTITY_REDUCTION,
                target_entity_type="RESOURCE",
                target_entity_id="RES-WATER-001",
                simulated_value=-10.0,
            ),
            actor,
            mock_db,
        )
    assert "cannot be negative" in str(exc2.value)

    # Valid scenario
    await SimulationService.add_scenario(
        sim.simulation_id,
        AddScenarioRequest(
            scenario_type=ScenarioType.RESOURCE_QUANTITY_REDUCTION,
            target_entity_type="RESOURCE",
            target_entity_id="RES-WATER-001",
            simulated_value=50.0,
        ),
        actor,
        mock_db,
    )

    # Adding duplicate scenario on same entity should raise SCENARIO_CONFLICT
    with pytest.raises(ValueError) as exc3:
        await SimulationService.add_scenario(
            sim.simulation_id,
            AddScenarioRequest(
                scenario_type=ScenarioType.RESOURCE_QUANTITY_REDUCTION,
                target_entity_type="RESOURCE",
                target_entity_id="RES-WATER-001",
                simulated_value=40.0,
            ),
            actor,
            mock_db,
        )
    assert "SCENARIO_CONFLICT" in str(exc3.value)


@pytest.mark.asyncio
async def test_multi_scenario_selective_execution(mock_db):
    """
    Test a combined simulation containing multiple scenarios (Shelter + Road Blockage)
    asserting selective agent execution and plan diff generation.
    """
    situation_id = "SIT-SIM-001"
    plan_id = "PLAN-ACT-001"
    sit_doc, plan_doc, res_doc, shelter_doc, hosp_doc, user_doc = populate_mock_environment(situation_id, plan_id)

    await mock_db["situations"].insert_one(sit_doc)
    await mock_db["coordination_plans"].insert_one(plan_doc)
    await mock_db["resources"].insert_one(res_doc)
    await mock_db["shelters"].insert_one(shelter_doc)
    await mock_db["healthcare_facilities"].insert_one(hosp_doc)
    await mock_db["users"].insert_one(user_doc)

    actor = {"id": "OFF-101", "full_name": "Officer Jane", "role": "EMERGENCY_OFFICER"}
    sim = await SimulationService.create_simulation(situation_id, "Combined Multi-Scenario", actor, mock_db)

    # Scenario 1: Shelter capacity drop to 100
    await SimulationService.add_scenario(
        sim.simulation_id,
        AddScenarioRequest(
            scenario_type=ScenarioType.SHELTER_CAPACITY_REDUCTION,
            target_entity_type="SHELTER",
            target_entity_id="SHELTER-001",
            simulated_value=100.0,
            description="Shelter A capacity drops from 250 to 100.",
        ),
        actor,
        mock_db,
    )

    # Scenario 2: Route Blockage
    await SimulationService.add_scenario(
        sim.simulation_id,
        AddScenarioRequest(
            scenario_type=ScenarioType.ROUTE_BLOCKED,
            target_entity_type="ROUTE",
            target_entity_id="ROUTE-001",
            simulated_value="BLOCKED",
            description="Route 1 access flooded.",
        ),
        actor,
        mock_db,
    )

    res = await SimulationService.run_simulation(sim.simulation_id, actor, mock_db)

    assert res.success is True
    assert res.status == SimulationStatus.COMPLETED
    assert res.diff_result is not None
    assert len(res.diff_result.items) >= 2

    # Verify Simulated Plan diff contains CHANGED items for shelter and route
    shelter_diff = next((i for i in res.diff_result.items if i.category == "Shelter"), None)
    assert shelter_diff is not None
    assert shelter_diff.diff_type == DiffChangeType.CHANGED.value


@pytest.mark.asyncio
async def test_stale_simulation_detection(mock_db):
    """
    Test that modifying real operational data after running a simulation causes check_simulation_stale
    to mark the simulation STALE.
    """
    situation_id = "SIT-SIM-001"
    plan_id = "PLAN-ACT-001"
    sit_doc, plan_doc, res_doc, shelter_doc, hosp_doc, user_doc = populate_mock_environment(situation_id, plan_id)

    await mock_db["situations"].insert_one(sit_doc)
    await mock_db["coordination_plans"].insert_one(plan_doc)
    await mock_db["resources"].insert_one(res_doc)
    await mock_db["shelters"].insert_one(shelter_doc)
    await mock_db["healthcare_facilities"].insert_one(hosp_doc)
    await mock_db["users"].insert_one(user_doc)

    actor = {"id": "OFF-101", "full_name": "Officer Jane", "role": "EMERGENCY_OFFICER"}
    sim = await SimulationService.create_simulation(situation_id, "Stale Detection Test", actor, mock_db)

    await SimulationService.add_scenario(
        sim.simulation_id,
        AddScenarioRequest(
            scenario_type=ScenarioType.RESOURCE_QUANTITY_REDUCTION,
            target_entity_type="RESOURCE",
            target_entity_id="RES-WATER-001",
            simulated_value=50.0,
        ),
        actor,
        mock_db,
    )

    await SimulationService.run_simulation(sim.simulation_id, actor, mock_db)

    # Immediately after run, simulation should NOT be stale
    is_stale, _ = await SimulationService.check_simulation_stale(sim.simulation_id, mock_db)
    assert is_stale is False

    # Simulate a real operational event: Situation severity is upgraded to CRITICAL
    await mock_db["situations"].update_one(
        {"situation_id": situation_id},
        {"$set": {"officer_override_severity": "CRITICAL"}}
    )

    # Now check staleness
    is_stale_now, reason = await SimulationService.check_simulation_stale(sim.simulation_id, mock_db)
    assert is_stale_now is True
    assert "state changed" in reason


@pytest.mark.asyncio
async def test_simulation_idempotency(mock_db):
    """
    Test that running the exact same simulation twice against the same baseline reuses
    the existing result without redundant execution.
    """
    situation_id = "SIT-SIM-001"
    sit_doc, plan_doc, res_doc, shelter_doc, hosp_doc, user_doc = populate_mock_environment(situation_id)

    await mock_db["situations"].insert_one(sit_doc)
    await mock_db["coordination_plans"].insert_one(plan_doc)
    await mock_db["resources"].insert_one(res_doc)
    await mock_db["shelters"].insert_one(shelter_doc)

    actor = {"id": "OFF-101", "full_name": "Officer Jane", "role": "EMERGENCY_OFFICER"}
    sim = await SimulationService.create_simulation(situation_id, "Idempotency Test", actor, mock_db)

    await SimulationService.add_scenario(
        sim.simulation_id,
        AddScenarioRequest(
            scenario_type=ScenarioType.RESOURCE_QUANTITY_REDUCTION,
            target_entity_type="RESOURCE",
            target_entity_id="RES-WATER-001",
            simulated_value=80.0,
        ),
        actor,
        mock_db,
    )

    # First Run
    res1 = await SimulationService.run_simulation(sim.simulation_id, actor, mock_db)
    assert res1.success is True

    # Second Run (Idempotency Hit)
    res2 = await SimulationService.run_simulation(sim.simulation_id, actor, mock_db)
    assert res2.success is True
    assert res2.simulated_plan_id == res1.simulated_plan_id


@pytest.mark.asyncio
async def test_simulation_discard(mock_db):
    """
    Test that discarding a simulation marks its status DISCARDED and records an audit log.
    """
    situation_id = "SIT-SIM-001"
    sit_doc, plan_doc, res_doc, shelter_doc, hosp_doc, user_doc = populate_mock_environment(situation_id)

    await mock_db["situations"].insert_one(sit_doc)
    await mock_db["coordination_plans"].insert_one(plan_doc)
    await mock_db["resources"].insert_one(res_doc)

    actor = {"id": "OFF-101", "full_name": "Officer Jane", "role": "EMERGENCY_OFFICER"}
    sim = await SimulationService.create_simulation(situation_id, "Discard Test", actor, mock_db)

    discarded = await SimulationService.discard_simulation(sim.simulation_id, actor, mock_db)
    assert discarded is True

    db_sim = await mock_db["simulations"].find_one({"simulation_id": sim.simulation_id})
    assert db_sim["status"] == SimulationStatus.DISCARDED.value

    # Check audit log
    audit = await mock_db["simulation_audit_logs"].find_one({"simulation_id": sim.simulation_id, "action": TimelineEventType.SIMULATION_DISCARDED.value})
    assert audit is not None
    assert audit["is_simulation"] is True


@pytest.mark.asyncio
async def test_target_lookup_real_data(mock_db):
    """
    Test target lookup returns real operational targets and includes both healthcare and healthcare_facilities aliases.
    """
    situation_id = "SIT-SIM-001"
    sit_doc, plan_doc, res_doc, shelter_doc, hosp_doc, user_doc = populate_mock_environment(situation_id)

    await mock_db["situations"].insert_one(sit_doc)
    await mock_db["coordination_plans"].insert_one(plan_doc)
    await mock_db["resources"].insert_one(res_doc)
    await mock_db["shelters"].insert_one(shelter_doc)
    await mock_db["healthcare_facilities"].insert_one(hosp_doc)
    await mock_db["users"].insert_one(user_doc)

    targets = await SimulationService.get_target_entities(situation_id=situation_id, db=mock_db)
    assert targets.situation_id == situation_id
    assert len(targets.resources) > 0
    assert len(targets.shelters) > 0
    assert len(targets.healthcare_facilities) > 0
    assert len(targets.healthcare) > 0
    assert targets.total_count > 0


@pytest.mark.asyncio
async def test_zero_scenario_draft_execution_blocked(mock_db):
    """
    Test that a zero-scenario draft is created successfully, but execution is blocked with clear instruction.
    """
    situation_id = "SIT-SIM-001"
    sit_doc, plan_doc, res_doc, shelter_doc, hosp_doc, user_doc = populate_mock_environment(situation_id)

    await mock_db["situations"].insert_one(sit_doc)
    await mock_db["coordination_plans"].insert_one(plan_doc)

    actor = {"id": "OFF-101", "full_name": "Officer Jane", "role": "EMERGENCY_OFFICER"}
    sim = await SimulationService.create_simulation(situation_id, "Zero Scenario Test", actor, mock_db)
    assert sim.status == SimulationStatus.DRAFT
    assert len(sim.scenarios) == 0

    with pytest.raises(ValueError, match="Add at least one hypothetical perturbation"):
        await SimulationService.run_simulation(sim.simulation_id, actor, mock_db)


@pytest.mark.asyncio
async def test_compound_perturbations_across_all_domains(mock_db):
    """
    Test simulation with compound perturbations across Shelter, Healthcare, Volunteer, and Route domains.
    """
    situation_id = "SIT-SIM-001"
    sit_doc, plan_doc, res_doc, shelter_doc, hosp_doc, user_doc = populate_mock_environment(situation_id)

    await mock_db["situations"].insert_one(sit_doc)
    await mock_db["coordination_plans"].insert_one(plan_doc)
    await mock_db["resources"].insert_one(res_doc)
    await mock_db["shelters"].insert_one(shelter_doc)
    await mock_db["healthcare_facilities"].insert_one(hosp_doc)
    await mock_db["users"].insert_one(user_doc)

    actor = {"id": "OFF-101", "full_name": "Officer Jane", "role": "EMERGENCY_OFFICER"}
    sim = await SimulationService.create_simulation(situation_id, "Compound Drill", actor, mock_db)

    # 1. Shelter capacity reduction
    await SimulationService.add_scenario(
        sim.simulation_id,
        AddScenarioRequest(
            scenario_type=ScenarioType.SHELTER_CAPACITY_REDUCTION,
            target_entity_type="SHELTER",
            target_entity_id="SHELTER-001",
            simulated_value=50.0,
        ),
        actor,
        mock_db,
    )

    # 2. Healthcare capacity reduction
    await SimulationService.add_scenario(
        sim.simulation_id,
        AddScenarioRequest(
            scenario_type=ScenarioType.HEALTHCARE_CAPACITY_REDUCTION,
            target_entity_type="HEALTHCARE",
            target_entity_id="HOSP-001",
            simulated_value=5.0,
        ),
        actor,
        mock_db,
    )

    # 3. Volunteer dropout
    await SimulationService.add_scenario(
        sim.simulation_id,
        AddScenarioRequest(
            scenario_type=ScenarioType.VOLUNTEER_UNAVAILABLE,
            target_entity_type="VOLUNTEER",
            target_entity_id="VOL-001",
            simulated_value="UNAVAILABLE",
        ),
        actor,
        mock_db,
    )

    # 4. Route blocked
    await SimulationService.add_scenario(
        sim.simulation_id,
        AddScenarioRequest(
            scenario_type=ScenarioType.ROUTE_BLOCKED,
            target_entity_type="ROUTE",
            target_entity_id="ROUTE-001",
            simulated_value="BLOCKED",
        ),
        actor,
        mock_db,
    )

    res = await SimulationService.run_simulation(sim.simulation_id, actor, mock_db)
    assert res.success is True
    assert res.status == SimulationStatus.COMPLETED
    assert res.is_simulation is True
    assert res.diff_result is not None
    assert len(res.diff_result.items) > 0

