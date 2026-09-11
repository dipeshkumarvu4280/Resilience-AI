import pytest
import mongomock
from datetime import datetime, timezone
from unittest.mock import patch

from app.models.enums import (
    CoordinationPlanStatus,
    SeverityLevel,
    AgentName,
)
from app.models.simulation import (
    ScenarioType,
    SimulationStatus,
    AddScenarioRequest,
)
from app.services.monitoring.simulation_service import SimulationService
from app.services.monitoring.plan_activation_service import PlanActivationService
from app.services.agents.orchestrator import compute_situation_state_fingerprint


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


class AsyncMongoMockDatabase:
    def __init__(self):
        self._client = mongomock.MongoClient()
        self._db = self._client["resilience_test_db"]

    def __getitem__(self, item):
        return AsyncMongoMockCollection(self._db[item])


@pytest.fixture
def mock_db():
    return AsyncMongoMockDatabase()


async def populate_db(db):
    # 1. Real situation record
    sit_doc = {
        "_id": "SIT-WURURZ4T",
        "situation_id": "SIT-WURURZ4T",
        "title": "Fire Cluster (2 Reports) - Chebrolu, Narakoduru",
        "status": "RESPONSE_IN_PROGRESS",
        "severity": "HIGH",
        "computed_severity_level": "HIGH",
        "officer_override_severity": "HIGH",
        "affected_areas": [{"zone_or_district": "Chebrolu", "city": "Guntur"}],
        "report_ids": ["REP-001", "REP-002"],
        "primary_report_id": "REP-001",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    sit_doc["state_fingerprint"] = compute_situation_state_fingerprint(sit_doc)
    await db["situations"].insert_one(sit_doc)

    # 2. Older superseded plan (v4)
    v4_doc = {
        "plan_id": "PLN-5F515A84",
        "situation_id": "SIT-WURURZ4T",
        "version": 4,
        "status": CoordinationPlanStatus.SUPERSEDED.value,
        "assessed_priority": "HIGH",
        "state_fingerprint": sit_doc["state_fingerprint"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_simulation": False,
        "reasoning": "v4 plan",
    }
    await db["coordination_plans"].insert_one(v4_doc)

    # 3. Authoritative active plan (v5) in status APPROVED
    v5_doc = {
        "plan_id": "PLN-F0C4E729",
        "situation_id": "SIT-WURURZ4T",
        "version": 5,
        "status": CoordinationPlanStatus.APPROVED.value,
        "assessed_priority": "HIGH",
        "state_fingerprint": sit_doc["state_fingerprint"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_simulation": False,
        "reasoning": "Authoritative v5 approved active response plan",
        "recommended_allocations": [
            {
                "resource_type": "Water",
                "matched_resource_id": "RES-WATER-01",
                "matched_resource_name": "Potable Water Tanker",
                "quantity_required": 100.0,
                "allocated_quantity": 100.0,
                "unit": "LITERS",
                "urgency": "HIGH",
                "warehouse_source": "Central Depot",
                "distance_km": 5.0,
                "eta_minutes": 15,
                "fulfillment_status": "FULFILLED",
                "allocation_reason": "Fire suppression hydration",
            }
        ],
        "recommended_routes": [
            {
                "route_id": "ROUTE-CHEBROLU-01",
                "origin_name": "Central Depot",
                "destination_name": "Chebrolu Fire Zone",
                "origin_coordinates": {"latitude": 16.200, "longitude": 80.500},
                "destination_coordinates": {"latitude": 16.220, "longitude": 80.520},
                "distance_km": 8.5,
                "estimated_duration_minutes": 20.0,
                "risk_level": "LOW",
                "is_primary": True,
                "road_condition_status": "PASSABLE",
                "assigned_mission": "Water Tanker Dispatch",
                "recommendation_reason": "Clear expressway",
            }
        ],
    }
    await db["coordination_plans"].insert_one(v5_doc)

    # 4. Situation without any plan
    no_plan_sit = {
        "_id": "SIT-NO-PLAN-99",
        "situation_id": "SIT-NO-PLAN-99",
        "title": "Isolated Storm Incident",
        "status": "DETECTED",
        "severity": "LOW",
        "computed_severity_level": "LOW",
        "affected_areas": [{"zone_or_district": "Tenali", "city": "Guntur"}],
        "report_ids": ["REP-099"],
        "primary_report_id": "REP-099",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    no_plan_sit["state_fingerprint"] = compute_situation_state_fingerprint(no_plan_sit)
    await db["situations"].insert_one(no_plan_sit)

    # 5. Situation with only PENDING_OFFICER_REVIEW plan (not active)
    pending_sit = {
        "_id": "SIT-PENDING-ONLY",
        "situation_id": "SIT-PENDING-ONLY",
        "title": "Pending Review Incident",
        "status": "RESPONSE_IN_PROGRESS",
        "severity": "MEDIUM",
        "computed_severity_level": "MEDIUM",
        "affected_areas": [{"zone_or_district": "Mangalagiri", "city": "Guntur"}],
        "report_ids": ["REP-100"],
        "primary_report_id": "REP-100",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    pending_sit["state_fingerprint"] = compute_situation_state_fingerprint(pending_sit)
    await db["situations"].insert_one(pending_sit)

    await db["coordination_plans"].insert_one({
        "plan_id": "PLN-PENDING-001",
        "situation_id": "SIT-PENDING-ONLY",
        "version": 1,
        "status": CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
        "assessed_priority": "MEDIUM",
        "state_fingerprint": pending_sit["state_fingerprint"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_simulation": False,
        "reasoning": "Pending initial review",
    })


@pytest.mark.asyncio
async def test_canonical_active_baseline_resolver(mock_db):
    """
    Test 1: Canonical resolver accurately identifies the authoritative active plan (v5)
    and excludes superseded, pending, and non-existent baselines.
    """
    await populate_db(mock_db)

    # Active plan exists (v5)
    plan = await SimulationService.get_current_active_plan_for_situation("SIT-WURURZ4T", mock_db)
    assert plan is not None
    assert plan.plan_id == "PLN-F0C4E729"
    assert plan.version == 5
    assert plan.status in [CoordinationPlanStatus.ACTIVE, CoordinationPlanStatus.APPROVED]

    # Pending-only situation has no active baseline
    plan_pending = await SimulationService.get_current_active_plan_for_situation("SIT-PENDING-ONLY", mock_db)
    assert plan_pending is None

    # No plan situation has no baseline
    plan_none = await SimulationService.get_current_active_plan_for_situation("SIT-NO-PLAN-99", mock_db)
    assert plan_none is None


@pytest.mark.asyncio
async def test_simulation_creation_blocked_without_active_plan(mock_db):
    """
    Test 2: Simulation creation fails cleanly with SIMULATION_BASELINE_REQUIRED if situation has no active plan.
    """
    await populate_db(mock_db)

    with pytest.raises(ValueError) as exc_info:
        await SimulationService.create_simulation(
            situation_id="SIT-PENDING-ONLY",
            db=mock_db,
        )
    assert "SIMULATION_BASELINE_REQUIRED" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info2:
        await SimulationService.create_simulation(
            situation_id="SIT-NO-PLAN-99",
            db=mock_db,
        )
    assert "SIMULATION_BASELINE_REQUIRED" in str(exc_info2.value)


@pytest.mark.asyncio
async def test_simulation_full_lifecycle_with_active_baseline(mock_db):
    """
    Test 3: Simulation lifecycle:
    Select situation -> Resolve v5 -> Create draft -> Add perturbation -> Run simulation -> Diff produced.
    """
    await populate_db(mock_db)

    # 1. Target lookup
    targets = await SimulationService.get_target_entities("SIT-WURURZ4T", mock_db)
    assert targets.has_active_baseline is True
    assert targets.baseline_plan_id == "PLN-F0C4E729"
    assert targets.baseline_plan_version == 5

    # 2. Create simulation
    sim = await SimulationService.create_simulation(
        situation_id="SIT-WURURZ4T",
        name="Test Fire Cluster Simulation",
        db=mock_db,
    )
    assert sim.status == SimulationStatus.DRAFT
    assert sim.baseline_plan_id == "PLN-F0C4E729"
    assert sim.baseline_plan_version == 5

    # 3. Add ROUTE_BLOCKED scenario
    scenario = await SimulationService.add_scenario(
        simulation_id=sim.simulation_id,
        payload=AddScenarioRequest(
            scenario_type=ScenarioType.ROUTE_BLOCKED,
            target_entity_type="ROUTE",
            target_entity_id="ROUTE-CHEBROLU-01",
            target_entity_name="Chebrolu Main Expressway",
            simulated_value={"is_blocked": True, "status": "BLOCKED"},
            description="Bridge collapsed on main expressway",
        ),
        db=mock_db,
    )
    assert scenario.scenario_type == ScenarioType.ROUTE_BLOCKED

    # 4. Run simulation
    run_res = await SimulationService.run_simulation(
        simulation_id=sim.simulation_id,
        db=mock_db,
    )
    assert run_res.success is True
    assert run_res.status == SimulationStatus.COMPLETED
    assert run_res.baseline_plan_id == "PLN-F0C4E729"
    assert run_res.is_simulation is True
    assert run_res.diff_result is not None


@pytest.mark.asyncio
async def test_stale_baseline_detection_on_plan_upgrade(mock_db):
    """
    Test 4: If live plan upgrades from v5 to v6 after simulation is created, running simulation fails with SIMULATION_BASELINE_STALE.
    """
    await populate_db(mock_db)

    # 1. Create simulation against v5
    sim = await SimulationService.create_simulation(
        situation_id="SIT-WURURZ4T",
        name="Stale Test Simulation",
        db=mock_db,
    )
    await SimulationService.add_scenario(
        simulation_id=sim.simulation_id,
        payload=AddScenarioRequest(
            scenario_type=ScenarioType.ROUTE_BLOCKED,
            target_entity_type="ROUTE",
            target_entity_id="ROUTE-CHEBROLU-01",
            simulated_value={"is_blocked": True},
            description="Route blocked test",
        ),
        db=mock_db,
    )

    # 2. Simulate live upgrade: Mark v5 SUPERSEDED, insert v6 ACTIVE
    await mock_db["coordination_plans"].update_one(
        {"plan_id": "PLN-F0C4E729"},
        {"$set": {"status": CoordinationPlanStatus.SUPERSEDED.value}}
    )
    await mock_db["coordination_plans"].insert_one({
        "plan_id": "PLN-NEW-V6",
        "situation_id": "SIT-WURURZ4T",
        "version": 6,
        "status": CoordinationPlanStatus.ACTIVE.value,
        "assessed_priority": "HIGH",
        "state_fingerprint": "new-fp-v6",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_simulation": False,
        "reasoning": "Upgraded live response plan v6",
    })

    # 3. Attempt to run simulation created against v5
    with pytest.raises(ValueError) as exc_info:
        await SimulationService.run_simulation(
            simulation_id=sim.simulation_id,
            db=mock_db,
        )
    assert "SIMULATION_BASELINE_STALE" in str(exc_info.value)


@pytest.mark.asyncio
async def test_simulation_plan_cannot_be_activated(mock_db):
    """
    Test 5: Simulation results (is_simulation=True, status=SIMULATION_RESULT) can NEVER be activated.
    """
    await populate_db(mock_db)

    sim_plan_id = "PLN-SIM-RESULT-999"
    await mock_db["coordination_plans"].insert_one({
        "plan_id": sim_plan_id,
        "situation_id": "SIT-WURURZ4T",
        "version": 6,
        "status": CoordinationPlanStatus.SIMULATION_RESULT.value,
        "is_simulation": True,
        "assessed_priority": "HIGH",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reasoning": "Simulated plan result",
    })

    officer_actor = {"id": "OFF-001", "full_name": "Commander Chief", "role": "EMERGENCY_OFFICER"}

    with pytest.raises(ValueError) as exc_info:
        await PlanActivationService.approve_and_activate_plan(
            plan_id=sim_plan_id,
            officer_actor=officer_actor,
            db=mock_db,
        )
    assert "SIMULATION_CANNOT_ACTIVATE" in str(exc_info.value)
