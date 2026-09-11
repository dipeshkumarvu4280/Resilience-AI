import pytest
import uuid
from httpx import AsyncClient
from app.models.enums import (
    EmergencyType,
    SeverityLevel,
    NeedUrgency,
    ResourceType,
    AgentName,
    AgentRunStatus,
    CoordinationPlanStatus,
    PlanReviewAction,
    ConflictType,
    ResolutionStrategy,
    ConflictStatus,
    TimelineEventType,
)
from app.models.agent import (
    AgentContext,
    AgentResult,
    DetectedConflict,
    ConflictResolutionSummary,
    PlanRecommendedResource,
)
from app.services.agents.registry import agent_registry, AgentRegistry
from app.services.agents.adapters.conflict_agent import ConflictResolutionAgent
from app.services.agents.adapters.priority_agent import PriorityAgent
from app.services.agents.adapters.needs_agent import NeedsAgent
from app.services.agents.adapters.resource_agent import ResourceCoordinationAgent
from app.services.agents.orchestrator import central_orchestrator, compute_situation_state_fingerprint
from app.db.mongodb import db_manager


async def get_officer_headers(client: AsyncClient):
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999002", "password": "OfficerPassword@2026"}
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def get_resource_manager_headers(client: AsyncClient):
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999003", "password": "ResourcePassword@2026"}
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


_CITY_COORDS = [
    (16.5062, 80.6480, "Vijayawada"),
    (17.6868, 83.2185, "Visakhapatnam"),
    (13.6288, 79.4192, "Tirupati"),
    (17.3850, 78.4867, "Hyderabad"),
    (16.9891, 82.2475, "Kakinada"),
    (17.0005, 81.8040, "Rajahmundry"),
    (14.4426, 79.9865, "Nellore"),
    (15.8281, 78.0373, "Kurnool"),
]
_coord_idx = 0


async def create_test_situation_cluster(client: AsyncClient, headers: dict) -> str:
    """Helper to create a fresh, isolated test situation from citizen report."""
    global _coord_idx
    lat, lng, city = _CITY_COORDS[_coord_idx % len(_CITY_COORDS)]
    _coord_idx += 1

    test_phone = f"986{uuid.uuid4().int % 10000000:07d}"
    rep_res = await client.post(
        "/api/v1/citizen/reports",
        json={
            "full_name": f"Conflict Test Citizen {city}",
            "phone": test_phone,
            "emergency_type": EmergencyType.FLOOD.value,
            "description": f"Urgent flash flood situation requiring supplies in {city}.",
            "location": {"latitude": lat, "longitude": lng, "city": city},
            "media": []
        }
    )
    assert rep_res.status_code == 201, rep_res.text
    rep_id = rep_res.json()["report_id"]

    sit_res = await client.get("/api/v1/officer/situations", headers=headers)
    assert sit_res.status_code == 200
    items = sit_res.json()["items"]
    for s in items:
        if rep_id in s.get("report_ids", []):
            return s["situation_id"]
    if items:
        return items[0]["situation_id"]
    raise RuntimeError("No situation cluster created for report")


# ==============================================================================
# 1. Registration & BaseAgent Contract Tests
# ==============================================================================

@pytest.mark.anyio
async def test_conflict_agent_registration_and_metadata():
    agent = ConflictResolutionAgent()
    assert agent.name == AgentName.CONFLICT_RESOLUTION_AGENT
    assert "shortages" in agent.purpose.lower() or "conflict" in agent.purpose.lower()
    assert AgentName.RESOURCE_COORDINATION_AGENT in agent.dependencies
    assert AgentName.NEEDS_AGENT in agent.dependencies
    assert AgentName.PRIORITY_AGENT in agent.dependencies
    assert "assessed_needs" in agent.required_inputs
    assert "recommended_allocations" in agent.required_inputs


@pytest.mark.anyio
async def test_conflict_agent_registry_integration():
    registry = AgentRegistry()
    agent = ConflictResolutionAgent()
    registry.register(agent)
    assert registry.has_agent(AgentName.CONFLICT_RESOLUTION_AGENT)
    assert registry.get(AgentName.CONFLICT_RESOLUTION_AGENT) is agent


# ==============================================================================
# 2. Deterministic Conflict Detection & Resolution Strategy Tests
# ==============================================================================

@pytest.mark.anyio
async def test_conflict_detection_no_conflicts():
    """When all needs are fully satisfied by available stock, 0 conflicts detected."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CONF-001",
        situation_title="Test Adequate Stock",
        emergency_type=EmergencyType.FLOOD.value,
        description="Minor flood situation.",
        location_summary="Vijayawada Central",
        parameters={
            "assessed_needs": [
                {"resource_type": "Water", "quantity": 50.0, "unit": "Litres", "urgency": "HIGH"}
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Water",
                    "quantity_required": 50.0,
                    "unit": "Litres",
                    "urgency": "HIGH",
                    "matched_resource_id": "RES-001",
                    "matched_resource_name": "Vijayawada Central Depot",
                    "available_in_inventory": 200.0,
                    "allocated_quantity": 50.0,
                    "distance_km": 5.2,
                }
            ],
            "effective_priority": "MEDIUM",
        }
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    summary = ConflictResolutionSummary(**result.structured_output)
    assert summary.conflicts_count == 0
    assert summary.officer_attention_required is False
    assert "Zero" in summary.explanation or "No coordination conflicts" in summary.explanation


@pytest.mark.anyio
async def test_conflict_detection_total_resource_shortage():
    """When a need has zero inventory available in depots -> RESOURCE_SHORTAGE & NO_FEASIBLE_RESOLUTION."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CONF-002",
        situation_title="Test Zero Stock",
        emergency_type=EmergencyType.FIRE.value,
        description="Fire requiring specialized foam extinguishers.",
        location_summary="Industrial Zone",
        parameters={
            "assessed_needs": [
                {"resource_type": "Rescue Equipment", "quantity": 20.0, "unit": "Units", "urgency": "CRITICAL"}
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Rescue Equipment",
                    "quantity_required": 20.0,
                    "unit": "Units",
                    "urgency": "CRITICAL",
                    "matched_resource_id": None,
                    "matched_resource_name": None,
                    "available_in_inventory": 0.0,
                    "allocated_quantity": 0.0,
                    "distance_km": None,
                }
            ],
            "effective_priority": "CRITICAL",
        }
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    summary = ConflictResolutionSummary(**result.structured_output)
    assert summary.conflicts_count == 1
    conf = summary.conflicts_detected[0]
    assert conf.conflict_type == ConflictType.RESOURCE_SHORTAGE
    assert conf.shortfall == 20.0
    assert conf.resolution_strategy == ResolutionStrategy.NO_FEASIBLE_RESOLUTION
    assert conf.resolution_status == ConflictStatus.UNRESOLVED
    assert conf.officer_attention_required is True


@pytest.mark.anyio
async def test_conflict_detection_insufficient_quantity_partial_allocation():
    """
    When required = 100, available = 60:
    -> INSUFFICIENT_QUANTITY, shortfall = 40, resolution = PARTIAL_ALLOCATION, officer_attention = True
    """
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CONF-003",
        situation_title="Test Partial Stock",
        emergency_type=EmergencyType.FLOOD.value,
        description="Hydration supplies for trapped residents.",
        location_summary="River Ward",
        parameters={
            "assessed_needs": [
                {"resource_type": "Water", "quantity": 100.0, "unit": "Litres", "urgency": "HIGH"}
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Water",
                    "quantity_required": 100.0,
                    "unit": "Litres",
                    "urgency": "HIGH",
                    "matched_resource_id": "RES-WTR-01",
                    "matched_resource_name": "River Depot",
                    "available_in_inventory": 60.0,
                    "allocated_quantity": 60.0,
                    "distance_km": 4.5,
                }
            ],
            "effective_priority": "HIGH",
        }
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    summary = ConflictResolutionSummary(**result.structured_output)
    assert summary.conflicts_count == 1
    conf = summary.conflicts_detected[0]
    assert conf.conflict_type == ConflictType.INSUFFICIENT_QUANTITY
    assert conf.detected_quantity == 100.0
    assert conf.available_quantity == 60.0
    assert conf.shortfall == 40.0
    assert conf.resolution_strategy == ResolutionStrategy.PARTIAL_ALLOCATION
    assert conf.resolution_status == ConflictStatus.PARTIALLY_RESOLVED
    assert conf.officer_attention_required is True


@pytest.mark.anyio
async def test_conflict_detection_competing_resource_demand():
    """
    When two demands compete for the same limited inventory depot:
    -> COMPETING_RESOURCE_DEMAND, PRIORITY_FIRST
    """
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CONF-004",
        situation_title="Test Competing Demand",
        emergency_type=EmergencyType.BUILDING_COLLAPSE.value,
        description="Multiple teams requiring generator stock.",
        location_summary="Sector 4",
        parameters={
            "assessed_needs": [
                {"resource_type": "Generator", "quantity": 3.0, "unit": "Units", "urgency": "CRITICAL"},
                {"resource_type": "Generator", "quantity": 2.0, "unit": "Units", "urgency": "HIGH"},
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Generator",
                    "quantity_required": 3.0,
                    "unit": "Units",
                    "urgency": "CRITICAL",
                    "matched_resource_id": "RES-GEN-01",
                    "matched_resource_name": "Heavy Equipment Hub",
                    "available_in_inventory": 4.0,  # Demanded: 3 + 2 = 5 > 4
                    "allocated_quantity": 3.0,
                    "distance_km": 8.0,
                },
                {
                    "resource_type": "Generator",
                    "quantity_required": 2.0,
                    "unit": "Units",
                    "urgency": "HIGH",
                    "matched_resource_id": "RES-GEN-01",
                    "matched_resource_name": "Heavy Equipment Hub",
                    "available_in_inventory": 4.0,
                    "allocated_quantity": 1.0,
                    "distance_km": 8.0,
                },
            ],
            "effective_priority": "CRITICAL",
        }
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    summary = ConflictResolutionSummary(**result.structured_output)
    comp_confs = [c for c in summary.conflicts_detected if c.conflict_type == ConflictType.COMPETING_RESOURCE_DEMAND]
    assert len(comp_confs) >= 1
    conf = comp_confs[0]
    assert conf.resolution_strategy == ResolutionStrategy.PRIORITY_FIRST
    assert conf.officer_attention_required is True


@pytest.mark.anyio
async def test_conflict_detection_geographic_mismatch():
    """
    When matched depot is located > 100km away:
    -> GEOGRAPHIC_MISMATCH & UNRESOLVED_ESCALATION
    """
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CONF-005",
        situation_title="Test Long Distance",
        emergency_type=EmergencyType.CYCLONE_STORM.value,
        description="Coastal storm response.",
        location_summary="Remote Coastal Point",
        parameters={
            "assessed_needs": [
                {"resource_type": "Blankets", "quantity": 100.0, "unit": "Units", "urgency": "HIGH"}
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Blankets",
                    "quantity_required": 100.0,
                    "unit": "Units",
                    "urgency": "HIGH",
                    "matched_resource_id": "RES-BLKT-01",
                    "matched_resource_name": "Distant State Warehouse",
                    "available_in_inventory": 500.0,
                    "allocated_quantity": 100.0,
                    "distance_km": 165.4,  # > 100km threshold
                }
            ],
            "effective_priority": "HIGH",
        }
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    summary = ConflictResolutionSummary(**result.structured_output)
    geo_confs = [c for c in summary.conflicts_detected if c.conflict_type == ConflictType.GEOGRAPHIC_MISMATCH]
    assert len(geo_confs) == 1
    conf = geo_confs[0]
    assert conf.resolution_strategy == ResolutionStrategy.UNRESOLVED_ESCALATION
    assert conf.resolution_status == ConflictStatus.ESCALATED
    assert conf.officer_attention_required is True


@pytest.mark.anyio
async def test_conflict_agent_preserves_officer_override_authority():
    """Officer override is preserved in conflict agent evidence and priority logic."""
    agent = ConflictResolutionAgent()
    context = AgentContext(
        situation_id="SIT-CONF-006",
        situation_title="Test Officer Override",
        emergency_type=EmergencyType.FIRE.value,
        description="Small incident manually upgraded by officer.",
        location_summary="Main Street",
        officer_severity_override=SeverityLevel.CRITICAL,
        parameters={
            "assessed_needs": [
                {"resource_type": "Water", "quantity": 100.0, "unit": "Litres", "urgency": "CRITICAL"}
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Water",
                    "quantity_required": 100.0,
                    "unit": "Litres",
                    "urgency": "CRITICAL",
                    "matched_resource_id": "RES-002",
                    "matched_resource_name": "Central Depot",
                    "available_in_inventory": 100.0,
                    "allocated_quantity": 100.0,
                    "distance_km": 2.0,
                }
            ],
            "effective_priority": "CRITICAL",
        }
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    assert any("CRITICAL" in ev for ev in result.evidence)


# ==============================================================================
# 3. Central Orchestrator Integration & End-to-End API Tests
# ==============================================================================

@pytest.mark.anyio
async def test_orchestrator_pipeline_includes_conflict_agent(client: AsyncClient):
    """End-to-end orchestration includes Conflict Resolution Agent and populates conflict fields."""
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    res = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        json={"force_refresh": True},
        headers=headers
    )
    assert res.status_code == 200, res.text
    plan = res.json()

    assert AgentName.CONFLICT_RESOLUTION_AGENT.value in plan["participating_agents"]
    assert AgentName.CONFLICT_RESOLUTION_AGENT.value in plan["agent_results"]
    assert "conflicts" in plan
    assert "conflict_summary" in plan
    assert "officer_attention_required" in plan
    assert "has_unresolved_conflicts" in plan


@pytest.mark.anyio
async def test_orchestrator_conflict_inspection_api_endpoint(client: AsyncClient):
    """GET /coordination/plans/{plan_id}/conflicts returns conflict resolution summary."""
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    # 1. Orchestrate
    res = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        json={"force_refresh": True},
        headers=headers
    )
    assert res.status_code == 200
    plan_id = res.json()["plan_id"]

    # 2. Query conflicts endpoint
    conf_res = await client.get(
        f"/api/v1/officer/coordination/plans/{plan_id}/conflicts",
        headers=headers
    )
    assert conf_res.status_code == 200
    summary = conf_res.json()
    if summary:
        assert "conflicts_detected" in summary
        assert "conflicts_count" in summary
        assert "officer_attention_required" in summary


@pytest.mark.anyio
async def test_orchestrator_idempotency_with_conflict_agent(client: AsyncClient):
    """Repeated calls for the same situation state return the same plan without duplicate runs."""
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    # Call 1
    res1 = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        headers=headers
    )
    assert res1.status_code == 200
    p1 = res1.json()

    # Call 2
    res2 = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        headers=headers
    )
    assert res2.status_code == 200
    p2 = res2.json()

    assert p1["plan_id"] == p2["plan_id"]
    assert p1["version"] == p2["version"]


@pytest.mark.anyio
async def test_unauthorized_user_cannot_access_conflicts(client: AsyncClient):
    """Resource Managers or unauthenticated callers cannot access officer coordination conflict endpoints."""
    # 1. No Auth -> 401
    res_no_auth = await client.get("/api/v1/officer/coordination/plans/PLN-TEST/conflicts")
    assert res_no_auth.status_code == 401

    # 2. Forbidden Role -> 403
    rm_headers = await get_resource_manager_headers(client)
    res_forbidden = await client.get(
        "/api/v1/officer/coordination/plans/PLN-TEST/conflicts",
        headers=rm_headers
    )
    assert res_forbidden.status_code == 403


@pytest.mark.anyio
async def test_zero_dummy_data_in_conflict_coordination(client: AsyncClient):
    """Ensure no fake demo/mock/seed strings in conflict summaries."""
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    res = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        json={"force_refresh": True},
        headers=headers
    )
    assert res.status_code == 200
    plan = res.json()

    plan_str = str(plan).lower()
    for forbidden in ["dummy", "fake", "placeholder", "lorem ipsum", "mock_data", "sample_situation"]:
        assert forbidden not in plan_str
