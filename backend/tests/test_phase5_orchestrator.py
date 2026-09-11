import pytest
import uuid
from httpx import AsyncClient
from app.models.enums import (
    UserRole,
    EmergencyType,
    SeverityLevel,
    AgentName,
    AgentRunStatus,
    CoordinationPlanStatus,
    PlanReviewAction,
    OfficerReviewAction,
    TimelineEventType,
)
from app.models.agent import AgentContext, AgentResult, OrchestrateSituationRequest, PlanReviewRequest
from app.services.agents.registry import agent_registry, AgentRegistry
from app.services.agents.base import BaseAgent
from app.services.agents.adapters.priority_agent import PriorityAgent
from app.services.agents.adapters.needs_agent import NeedsAgent
from app.services.agents.adapters.resource_agent import ResourceCoordinationAgent
from app.services.agents.orchestrator import central_orchestrator


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
    (14.6819, 77.6006, "Anantapur"),
    (18.1067, 83.3956, "Vizianagaram"),
    (18.2949, 83.8938, "Srikakulam"),
    (15.5057, 80.0499, "Ongole"),
    (16.7107, 81.0952, "Eluru"),
    (15.3050, 78.4350, "Nandyal"),
    (16.1800, 81.1300, "Machilipatnam"),
    (14.4700, 78.8200, "Kadapa"),
    (15.8300, 80.3500, "Bapatla"),
    (16.7700, 80.8400, "Nuzvid"),
    (17.2700, 82.4000, "Tuni"),
    (18.6000, 84.1800, "Palasa"),
]
_coord_idx = 0


async def create_test_situation_cluster(client: AsyncClient, headers: dict) -> str:
    """Helper to create a fresh, isolated test situation from citizen report."""
    global _coord_idx
    lat, lng, city = _CITY_COORDS[_coord_idx % len(_CITY_COORDS)]
    _coord_idx += 1

    test_phone = f"987{uuid.uuid4().int % 10000000:07d}"
    rep_res = await client.post(
        "/api/v1/citizen/reports",
        json={
            "full_name": f"Test Citizen {city}",
            "phone": test_phone,
            "emergency_type": EmergencyType.FLOOD.value,
            "description": f"Rising floodwaters trapped 5 families in {city}.",
            "location": {"latitude": lat, "longitude": lng, "city": city},
            "media": []
        }
    )
    assert rep_res.status_code == 201, rep_res.text
    rep_id = rep_res.json()["report_id"]

    # Fetch situation cluster containing this specific report
    sit_res = await client.get("/api/v1/officer/situations", headers=headers)
    assert sit_res.status_code == 200
    items = sit_res.json()["items"]
    for s in items:
        if rep_id in s.get("report_ids", []):
            return s["situation_id"]
    if items:
        return items[0]["situation_id"]
    raise RuntimeError("No situation cluster created for report")


# 1. Agent Registry Tests
@pytest.mark.anyio
async def test_agent_registry_registration_and_retrieval():
    registry = AgentRegistry()
    agent = PriorityAgent()
    registry.register(agent)
    assert registry.has_agent(AgentName.PRIORITY_AGENT)
    assert registry.get(AgentName.PRIORITY_AGENT) is agent
    assert len(registry.list_agents()) == 1


@pytest.mark.anyio
async def test_agent_registry_rejects_invalid_agent():
    registry = AgentRegistry()
    with pytest.raises(TypeError):
        registry.register("not an agent instance")  # type: ignore


@pytest.mark.anyio
async def test_unknown_agent_cannot_execute():
    registry = AgentRegistry()
    assert registry.is_registered("fake_unregistered_agent") is False


# 2. Priority Agent Adapter Tests
@pytest.mark.anyio
async def test_priority_agent_preserves_officer_override():
    agent = PriorityAgent()
    context = AgentContext(
        situation_id="SIT-TEST-001",
        situation_title="Test Fire Situation",
        emergency_type=EmergencyType.FIRE.value,
        description="Minor smoke detected.",
        location_summary="Depot Road",
        officer_severity_override=SeverityLevel.CRITICAL,
    )
    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    assert result.structured_output["severity_level"] == SeverityLevel.CRITICAL.value
    assert result.structured_output["is_officer_override"] is True
    assert result.confidence == 1.0


@pytest.mark.anyio
async def test_priority_agent_deterministic_calculation():
    agent = PriorityAgent()
    context = AgentContext(
        situation_id="SIT-TEST-002",
        situation_title="Test Flood Situation",
        emergency_type=EmergencyType.FLOOD.value,
        description="Severe flooding submerging residential district.",
        location_summary="River Zone",
        report_count=3,
    )
    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    assert result.structured_output["severity_level"] in [SeverityLevel.HIGH.value, SeverityLevel.CRITICAL.value]
    assert result.structured_output["is_officer_override"] is False


# 3. Needs Agent Adapter Tests
@pytest.mark.anyio
async def test_needs_agent_generates_valid_items():
    agent = NeedsAgent()
    context = AgentContext(
        situation_id="SIT-TEST-003",
        situation_title="Test Flood Situation",
        emergency_type=EmergencyType.FLOOD.value,
        description="Water rising rapidly, boats and potable water required.",
        location_summary="Lowland area",
    )
    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    assert result.structured_output["need_count"] > 0
    needs = result.structured_output["needs"]
    for n in needs:
        assert "resource_type" in n
        assert "quantity" in n
        assert "unit" in n
        assert "urgency" in n


# 4. Resource Coordination Agent Tests
@pytest.mark.anyio
async def test_resource_agent_matching_against_real_inventory():
    agent = ResourceCoordinationAgent()
    context = AgentContext(
        situation_id="SIT-TEST-004",
        situation_title="Test Medical Situation",
        emergency_type=EmergencyType.MEDICAL_EMERGENCY.value,
        description="Mass casualty medical triage.",
        location_summary="Main Hospital",
        parameters={
            "assessed_needs": [
                {"resource_type": "Medicine", "quantity": 10.0, "unit": "Kits", "urgency": "CRITICAL"},
                {"resource_type": "Water", "quantity": 50.0, "unit": "Litres", "urgency": "HIGH"},
            ]
        }
    )
    result = await agent.execute(context)
    assert result.status in [AgentRunStatus.COMPLETED, AgentRunStatus.NOT_REQUIRED]
    assert "matches" in result.structured_output


# 5. Central Orchestrator Pipeline & End-to-End API Tests
@pytest.mark.anyio
async def test_orchestrator_deterministic_agent_selection():
    situation = {"status": "ACTIVE", "emergency_type": "Flood"}
    selected = central_orchestrator.select_required_agents(situation)
    assert AgentName.PRIORITY_AGENT in selected
    assert AgentName.NEEDS_AGENT in selected
    assert AgentName.RESOURCE_COORDINATION_AGENT in selected


@pytest.mark.anyio
async def test_officer_can_orchestrate_and_generate_plan(client: AsyncClient):
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    # Call Orchestrator API
    res = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        json={"force_refresh": True},
        headers=headers
    )
    assert res.status_code == 200, res.text
    plan = res.json()
    assert "plan_id" in plan
    assert plan["situation_id"] == sit_id
    assert plan["status"] == CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value
    assert len(plan["participating_agents"]) >= 2
    assert "assessed_priority" in plan
    assert "assessed_needs" in plan
    assert "recommended_allocations" in plan
    assert plan["confidence"] > 0.0


@pytest.mark.anyio
async def test_orchestrator_idempotency_prevents_duplicate_runs(client: AsyncClient):
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    # First call
    res1 = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        json={"force_refresh": True},
        headers=headers
    )
    assert res1.status_code == 200
    plan1_id = res1.json()["plan_id"]

    # Immediate second call without force_refresh must return existing plan
    res2 = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        json={"force_refresh": False},
        headers=headers
    )
    assert res2.status_code == 200
    plan2_id = res2.json()["plan_id"]
    assert plan1_id == plan2_id


@pytest.mark.anyio
async def test_officer_can_approve_coordination_plan(client: AsyncClient):
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    # Orchestrate
    orch_res = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        json={"force_refresh": True},
        headers=headers
    )
    assert orch_res.status_code == 200
    plan_id = orch_res.json()["plan_id"]

    # Officer Approves Plan
    review_res = await client.post(
        f"/api/v1/officer/coordination/plans/{plan_id}/review",
        json={
            "action": PlanReviewAction.APPROVE.value,
            "notes": "Plan approved for deployment."
        },
        headers=headers
    )
    assert review_res.status_code == 200
    plan_data = review_res.json()
    assert plan_data["status"] == CoordinationPlanStatus.APPROVED.value
    assert plan_data["officer_review"]["decision"] == PlanReviewAction.APPROVE.value
    assert plan_data["officer_review"]["officer_notes"] == "Plan approved for deployment."


@pytest.mark.anyio
async def test_officer_can_modify_coordination_plan(client: AsyncClient):
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    orch_res = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        json={"force_refresh": True},
        headers=headers
    )
    assert orch_res.status_code == 200
    plan_id = orch_res.json()["plan_id"]

    # Officer Modifies Plan
    review_res = await client.post(
        f"/api/v1/officer/coordination/plans/{plan_id}/review",
        json={
            "action": PlanReviewAction.MODIFY.value,
            "notes": "Modified water quantity to 200 litres.",
            "modified_needs": [
                {"resource_type": "Water", "quantity": 200.0, "unit": "Litres", "urgency": "CRITICAL"}
            ]
        },
        headers=headers
    )
    assert review_res.status_code == 200
    plan_data = review_res.json()
    assert plan_data["status"] == CoordinationPlanStatus.MODIFIED.value
    assert plan_data["officer_review"]["decision"] == PlanReviewAction.MODIFY.value
    assert len(plan_data["assessed_needs"]) == 1
    assert plan_data["assessed_needs"][0]["quantity"] == 200.0


@pytest.mark.anyio
async def test_officer_can_reject_coordination_plan(client: AsyncClient):
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    orch_res = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        json={"force_refresh": True},
        headers=headers
    )
    assert orch_res.status_code == 200
    plan_id = orch_res.json()["plan_id"]

    # Officer Rejects Plan
    review_res = await client.post(
        f"/api/v1/officer/coordination/plans/{plan_id}/review",
        json={
            "action": PlanReviewAction.REJECT.value,
            "notes": "Situation contained locally; external resource allocation rejected."
        },
        headers=headers
    )
    assert review_res.status_code == 200
    plan_data = review_res.json()
    assert plan_data["status"] == CoordinationPlanStatus.REJECTED.value
    assert plan_data["officer_review"]["decision"] == PlanReviewAction.REJECT.value


@pytest.mark.anyio
async def test_unauthorized_user_cannot_orchestrate_or_review(client: AsyncClient):
    rm_headers = await get_resource_manager_headers(client)

    # No Auth
    res_no_auth = await client.post("/api/v1/officer/coordination/situations/SIT-TEST/orchestrate")
    assert res_no_auth.status_code == 401

    # Forbidden Role
    res_forbidden = await client.post(
        "/api/v1/officer/coordination/situations/SIT-TEST/orchestrate",
        headers=rm_headers
    )
    assert res_forbidden.status_code == 403


@pytest.mark.anyio
async def test_orchestrator_triple_click_and_state_idempotency(client: AsyncClient):
    """
    Validates:
    - 1st call creates Plan PLN-A
    - 2nd call (same state) returns PLN-A
    - 3rd call (same state) returns PLN-A
    - No duplicate plans created in database
    """
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    # Click 1
    res1 = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        headers=headers
    )
    assert res1.status_code == 200
    p1 = res1.json()
    p1_id = p1["plan_id"]
    assert p1["version"] == 1
    assert p1["status"] == CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value

    # Click 2
    res2 = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        headers=headers
    )
    assert res2.status_code == 200
    p2 = res2.json()
    assert p2["plan_id"] == p1_id

    # Click 3
    res3 = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        headers=headers
    )
    assert res3.status_code == 200
    p3 = res3.json()
    assert p3["plan_id"] == p1_id

    # Verify history in database only has 1 plan
    hist_res = await client.get(
        f"/api/v1/officer/coordination/situations/{sit_id}/plans",
        headers=headers
    )
    assert hist_res.status_code == 200
    plans = hist_res.json()
    assert len(plans) == 1
    assert plans[0]["plan_id"] == p1_id


@pytest.mark.anyio
async def test_orchestrator_concurrent_requests_create_only_one_plan(client: AsyncClient):
    """
    Simulates rapid double-click or simultaneous concurrent requests.
    Validates that only ONE active plan is created and no DuplicateKey error reaches caller.
    """
    import asyncio
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    # Fire 3 concurrent orchestration requests
    tasks = [
        client.post(f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate", headers=headers)
        for _ in range(3)
    ]
    responses = await asyncio.gather(*tasks)

    for r in responses:
        assert r.status_code == 200

    plan_ids = [r.json()["plan_id"] for r in responses]
    # All concurrent requests must resolve to the exact same plan ID
    assert len(set(plan_ids)) == 1, f"Expected 1 unique plan ID, got: {plan_ids}"

    # Verify database has exactly 1 plan for this situation
    hist_res = await client.get(
        f"/api/v1/officer/coordination/situations/{sit_id}/plans",
        headers=headers
    )
    assert hist_res.status_code == 200
    assert len(hist_res.json()) == 1


@pytest.mark.anyio
async def test_orchestrator_state_change_generates_new_version(client: AsyncClient):
    """
    Validates that when the situation state materially changes (e.g. officer severity override):
    - A new version (v2) is allowed
    - Old plan is superseded or kept as history
    """
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    # Initial plan (v1)
    res1 = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        headers=headers
    )
    assert res1.status_code == 200
    p1 = res1.json()
    p1_id = p1["plan_id"]
    assert p1["version"] == 1

    # Officer updates severity override on the situation
    override_res = await client.post(
        f"/api/v1/officer/situations/{sit_id}/review",
        json={
            "action": OfficerReviewAction.MODIFY.value,
            "modified_severity_level": SeverityLevel.CRITICAL.value,
            "modified_severity_score": 9.5,
            "notes": "Urgent escalation",
        },
        headers=headers
    )
    assert override_res.status_code == 200

    # Next orchestration request with force_refresh=True produces v2
    res2 = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        json={"force_refresh": True},
        headers=headers
    )
    assert res2.status_code == 200
    p2 = res2.json()
    assert p2["plan_id"] != p1_id
    assert p2["version"] == 2
    assert p2["assessed_priority"] == SeverityLevel.CRITICAL.value


@pytest.mark.anyio
async def test_orchestrator_approved_plan_historical_preservation(client: AsyncClient):
    """
    Validates that approved plans remain in history and are not overwritten.
    """
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    # 1. Generate plan
    res1 = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        headers=headers
    )
    p1_id = res1.json()["plan_id"]

    # 2. Approve plan
    app_res = await client.post(
        f"/api/v1/officer/coordination/plans/{p1_id}/review",
        json={"action": PlanReviewAction.APPROVE.value, "notes": "Approved for operations"},
        headers=headers
    )
    assert app_res.status_code == 200
    assert app_res.json()["status"] == CoordinationPlanStatus.APPROVED.value

    # 3. Request orchestration again (without state change) -> returns approved plan
    res2 = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        headers=headers
    )
    assert res2.status_code == 200
    assert res2.json()["plan_id"] == p1_id
    assert res2.json()["status"] == CoordinationPlanStatus.APPROVED.value


@pytest.mark.anyio
async def test_coordination_agent_runs_inspection(client: AsyncClient):
    """
    Validates that agent runs are recorded, tagged with state_fingerprint, and inspectable via API.
    """
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        json={"force_refresh": True},
        headers=headers
    )

    # Inspect situation agent runs
    runs_res = await client.get(
        f"/api/v1/officer/coordination/situations/{sit_id}/agent-runs",
        headers=headers
    )
    assert runs_res.status_code == 200
    runs = runs_res.json()
    assert len(runs) >= 2
    for r in runs:
        assert "run_id" in r
        assert "agent_name" in r
        assert "status" in r
        assert "confidence" in r
        assert "state_fingerprint" in r
