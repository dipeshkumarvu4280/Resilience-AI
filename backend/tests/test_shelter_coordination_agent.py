import pytest
import uuid
from httpx import AsyncClient
from datetime import datetime, timezone

from app.models.enums import (
    AgentName,
    AgentRunStatus,
    CoordinationPlanStatus,
    EmergencyType,
    PlanReviewAction,
    SeverityLevel,
    NeedUrgency,
    ResourceType,
    ResourceStatus,
    ResourceCondition,
    ShelterConflictType,
    TimelineEventType,
    UserRole,
)
from app.models.agent import (
    AgentContext,
    CoordinationPlan,
    PlanRecommendedResource,
    RecommendedShelter,
    ShelterCoordinationSummary,
)
from app.services.agents.registry import agent_registry
from app.services.agents.adapters.shelter_agent import ShelterCoordinationAgent
from app.services.agents.orchestrator import central_orchestrator
from app.services.resource_matching import haversine_distance_km
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
            "full_name": f"Shelter Test Citizen {city}",
            "phone": test_phone,
            "emergency_type": EmergencyType.FLOOD.value,
            "description": f"Urgent severe flood requiring evacuation and shelter in {city}.",
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
# 1. BaseAgent Contract & Registration Tests
# ==============================================================================

@pytest.mark.anyio
async def test_shelter_agent_registration():
    """1. Verify ShelterCoordinationAgent registration and topological dependencies."""
    agent = ShelterCoordinationAgent()
    assert agent.name == AgentName.SHELTER_AGENT
    assert agent.is_enabled is True
    assert AgentName.PRIORITY_AGENT in agent.dependencies
    assert AgentName.NEEDS_AGENT in agent.dependencies
    assert AgentName.RESOURCE_COORDINATION_AGENT in agent.dependencies
    assert AgentName.CONFLICT_RESOLUTION_AGENT in agent.dependencies


@pytest.mark.anyio
async def test_shelter_not_required():
    """2. Non-displacement emergency type without shelter needs returns SHELTER_NOT_REQUIRED."""
    agent = ShelterCoordinationAgent()
    context = AgentContext(
        situation_id="SIT-TEST-001",
        situation_title="Minor Road Accident",
        emergency_type="Road Accident",
        description="Minor collision on clear roadway, no injuries.",
        location_summary="Main Highway Junction",
        center_latitude=16.5062,
        center_longitude=80.6480,
        report_count=1,
        officer_severity_override=SeverityLevel.LOW,
        existing_needs=[],
        parameters={
            "affected_population": 0,
            "available_shelters": [],
            "effective_priority": "LOW",
        },
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    output = result.structured_output
    assert output["shelter_required"] is False
    assert ShelterConflictType.SHELTER_NOT_REQUIRED.value in output["conflicts"]
    assert output["total_population_covered"] == 0.0
    assert output["total_shortfall"] == 0.0
    assert output["officer_attention_required"] is False


@pytest.mark.anyio
async def test_shelter_required_and_population_unavailable():
    """3. Disaster displacement risk exists but population is unknown: flag POPULATION_DATA_UNAVAILABLE."""
    agent = ShelterCoordinationAgent()
    context = AgentContext(
        situation_id="SIT-TEST-002",
        situation_title="Flash Flood Evacuation",
        emergency_type="Flood",
        description="River surge flooding residential colony.",
        location_summary="Riverbank Area",
        center_latitude=16.5062,
        center_longitude=80.6480,
        report_count=3,
        officer_severity_override=SeverityLevel.CRITICAL,
        existing_needs=[],
        parameters={
            "affected_population": 0,  # Unknown
            "available_shelters": [],
            "effective_priority": "CRITICAL",
        },
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    output = result.structured_output
    assert output["shelter_required"] is True
    assert ShelterConflictType.POPULATION_DATA_UNAVAILABLE.value in output["conflicts"]
    assert output["officer_attention_required"] is True


# ==============================================================================
# 2. Capacity, Eligibility & Ranking Logic Tests
# ==============================================================================

@pytest.mark.anyio
async def test_remaining_capacity_calculation_and_single_shelter_allocation():
    """4. Single suitable shelter with sufficient remaining capacity accommodates evacuees."""
    agent = ShelterCoordinationAgent()
    sample_shelters = [
        {
            "resource_id": "RES-SHL-001",
            "name": "Community Relief Center Alpha",
            "resource_type": "Shelter",
            "quantity_total": 100.0,
            "quantity_available": 80.0,
            "current_occupancy": 20.0,
            "unit": "Beds",
            "status": "AVAILABLE",
            "condition": "GOOD",
            "location": {
                "latitude": 16.5080,
                "longitude": 80.6490,
                "address": "42 Flood Relief Road",
            },
        }
    ]

    context = AgentContext(
        situation_id="SIT-TEST-003",
        situation_title="Coastal Surge Evacuation",
        emergency_type="Flood",
        description="Low-lying flood evacuation.",
        location_summary="Coastal Zone",
        center_latitude=16.5062,
        center_longitude=80.6480,
        report_count=4,
        officer_severity_override=SeverityLevel.HIGH,
        existing_needs=[],
        parameters={
            "affected_population": 50,
            "available_shelters": sample_shelters,
            "effective_priority": "HIGH",
        },
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    output = result.structured_output
    assert output["shelter_required"] is True
    assert len(output["shelters_recommended"]) == 1
    rec = output["shelters_recommended"][0]
    assert rec["shelter_id"] == "RES-SHL-001"
    assert rec["recommended_occupancy"] == 50.0
    assert rec["remaining_capacity"] == 80.0
    assert rec["coverage_percentage"] == 100.0
    assert output["total_population_covered"] == 50.0
    assert output["total_shortfall"] == 0.0
    assert output["officer_attention_required"] is False


@pytest.mark.anyio
async def test_multi_shelter_split():
    """5. Population exceeding single shelter capacity is split across multiple top-ranked facilities."""
    agent = ShelterCoordinationAgent()
    sample_shelters = [
        {
            "resource_id": "RES-SHL-001",
            "name": "Shelter Alpha",
            "resource_type": "Shelter",
            "quantity_total": 100.0,
            "quantity_available": 70.0,
            "current_occupancy": 30.0,
            "unit": "Beds",
            "status": "AVAILABLE",
            "condition": "GOOD",
            "location": {"latitude": 16.5080, "longitude": 80.6490, "address": "Alpha Way"},
        },
        {
            "resource_id": "RES-SHL-002",
            "name": "Shelter Bravo",
            "resource_type": "Shelter",
            "quantity_total": 100.0,
            "quantity_available": 80.0,
            "current_occupancy": 20.0,
            "unit": "Beds",
            "status": "AVAILABLE",
            "condition": "GOOD",
            "location": {"latitude": 16.5150, "longitude": 80.6550, "address": "Bravo Ave"},
        },
    ]

    context = AgentContext(
        situation_id="SIT-TEST-004",
        situation_title="Major Cyclone Displacement",
        emergency_type="Cyclone / Storm",
        description="High winds and surge require immediate evacuation.",
        location_summary="Coastal Zone",
        center_latitude=16.5062,
        center_longitude=80.6480,
        report_count=5,
        officer_severity_override=SeverityLevel.CRITICAL,
        existing_needs=[],
        parameters={
            "affected_population": 120,
            "available_shelters": sample_shelters,
            "effective_priority": "CRITICAL",
        },
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    output = result.structured_output
    assert output["shelter_required"] is True
    assert len(output["shelters_recommended"]) == 2
    rec1 = output["shelters_recommended"][0]
    rec2 = output["shelters_recommended"][1]

    # Both shelters are allocated to satisfy 120 total population without exceeding remaining capacity
    assert rec1["recommended_occupancy"] + rec2["recommended_occupancy"] == 120.0
    assert rec1["recommended_occupancy"] > 0
    assert rec2["recommended_occupancy"] > 0
    assert output["total_population_covered"] == 120.0
    assert output["total_shortfall"] == 0.0
    assert output["officer_attention_required"] is False


@pytest.mark.anyio
async def test_shelter_capacity_shortfall():
    """6. Total available capacity less than evacuee population yields shortfall and officer attention."""
    agent = ShelterCoordinationAgent()
    sample_shelters = [
        {
            "resource_id": "RES-SHL-001",
            "name": "Shelter Alpha",
            "resource_type": "Shelter",
            "quantity_total": 50.0,
            "quantity_available": 40.0,
            "current_occupancy": 10.0,
            "unit": "Beds",
            "status": "AVAILABLE",
            "condition": "GOOD",
            "location": {"latitude": 16.5080, "longitude": 80.6490},
        },
        {
            "resource_id": "RES-SHL-002",
            "name": "Shelter Bravo",
            "resource_type": "Shelter",
            "quantity_total": 60.0,
            "quantity_available": 30.0,
            "current_occupancy": 30.0,
            "unit": "Beds",
            "status": "AVAILABLE",
            "condition": "GOOD",
            "location": {"latitude": 16.5150, "longitude": 80.6550},
        },
    ]

    context = AgentContext(
        situation_id="SIT-TEST-005",
        situation_title="Severe Inundation",
        emergency_type="Flood",
        description="200 evacuees stranded, local shelter capacity limited.",
        location_summary="Lowlands",
        center_latitude=16.5062,
        center_longitude=80.6480,
        report_count=6,
        officer_severity_override=SeverityLevel.CRITICAL,
        existing_needs=[],
        parameters={
            "affected_population": 200,
            "available_shelters": sample_shelters,
            "effective_priority": "CRITICAL",
        },
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    output = result.structured_output
    assert output["shelter_required"] is True
    # Available = 40 + 30 = 70
    assert output["total_capacity_available"] == 70.0
    assert output["total_population_covered"] == 70.0
    assert output["total_shortfall"] == 130.0
    assert ShelterConflictType.SHELTER_CAPACITY_SHORTAGE.value in output["conflicts"]
    assert output["officer_attention_required"] is True


@pytest.mark.anyio
async def test_full_and_unavailable_shelters_excluded():
    """7. Full, closed, or maintenance shelters are excluded from recommendation."""
    agent = ShelterCoordinationAgent()
    sample_shelters = [
        {
            "resource_id": "RES-SHL-FULL",
            "name": "Full Shelter",
            "resource_type": "Shelter",
            "quantity_total": 100.0,
            "quantity_available": 0.0,
            "current_occupancy": 100.0,
            "unit": "Beds",
            "status": "IN_USE",
            "condition": "GOOD",
            "location": {"latitude": 16.5080, "longitude": 80.6490},
        },
        {
            "resource_id": "RES-SHL-MAINT",
            "name": "Maintenance Shelter",
            "resource_type": "Shelter",
            "quantity_total": 100.0,
            "quantity_available": 80.0,
            "current_occupancy": 0.0,
            "unit": "Beds",
            "status": "MAINTENANCE",
            "condition": "POOR",
            "location": {"latitude": 16.5080, "longitude": 80.6490},
        },
        {
            "resource_id": "RES-SHL-AVAIL",
            "name": "Operational Shelter",
            "resource_type": "Shelter",
            "quantity_total": 100.0,
            "quantity_available": 60.0,
            "current_occupancy": 40.0,
            "unit": "Beds",
            "status": "AVAILABLE",
            "condition": "GOOD",
            "location": {"latitude": 16.5080, "longitude": 80.6490},
        },
    ]

    context = AgentContext(
        situation_id="SIT-TEST-006",
        situation_title="Flood Relief Allocation",
        emergency_type="Flood",
        description="50 people needing shelter.",
        location_summary="Ward 4",
        center_latitude=16.5062,
        center_longitude=80.6480,
        report_count=2,
        officer_severity_override=SeverityLevel.HIGH,
        existing_needs=[],
        parameters={
            "affected_population": 50,
            "available_shelters": sample_shelters,
            "effective_priority": "HIGH",
        },
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    output = result.structured_output
    assert len(output["shelters_recommended"]) == 1
    assert output["shelters_recommended"][0]["shelter_id"] == "RES-SHL-AVAIL"
    assert output["total_population_covered"] == 50.0
    assert ShelterConflictType.SHELTER_FULL.value in output["conflicts"]
    assert ShelterConflictType.SHELTER_UNAVAILABLE.value in output["conflicts"]


@pytest.mark.anyio
async def test_distance_and_ranking_calculation():
    """8. Explainable ranking calculation ranks closer and higher capacity shelters higher."""
    agent = ShelterCoordinationAgent()
    sample_shelters = [
        {
            "resource_id": "RES-SHL-FAR",
            "name": "Far Shelter",
            "resource_type": "Shelter",
            "quantity_total": 200.0,
            "quantity_available": 100.0,
            "current_occupancy": 100.0,
            "unit": "Beds",
            "status": "AVAILABLE",
            "condition": "GOOD",
            "location": {"latitude": 16.6500, "longitude": 80.8000},  # ~22 km
        },
        {
            "resource_id": "RES-SHL-NEAR",
            "name": "Near Shelter",
            "resource_type": "Shelter",
            "quantity_total": 200.0,
            "quantity_available": 100.0,
            "current_occupancy": 100.0,
            "unit": "Beds",
            "status": "AVAILABLE",
            "condition": "GOOD",
            "location": {"latitude": 16.5070, "longitude": 80.6490},  # ~0.14 km
        },
    ]

    context = AgentContext(
        situation_id="SIT-TEST-007",
        situation_title="Proximity Test Incident",
        emergency_type="Earthquake",
        description="Building structural damage.",
        location_summary="Downtown",
        center_latitude=16.5062,
        center_longitude=80.6480,
        report_count=3,
        officer_severity_override=SeverityLevel.CRITICAL,
        existing_needs=[],
        parameters={
            "affected_population": 50,
            "available_shelters": sample_shelters,
            "effective_priority": "CRITICAL",
        },
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    output = result.structured_output
    assert len(output["shelters_recommended"]) == 1
    # Near shelter should be chosen
    assert output["shelters_recommended"][0]["shelter_id"] == "RES-SHL-NEAR"
    assert output["shelters_recommended"][0]["distance_km"] < 1.0


@pytest.mark.anyio
async def test_no_feasible_shelter():
    """9. When zero shelters are available or suitable, flags NO_FEASIBLE_SHELTER and OFFICER_ATTENTION_REQUIRED."""
    agent = ShelterCoordinationAgent()
    sample_shelters = [
        {
            "resource_id": "RES-SHL-CLOSED",
            "name": "Decommissioned Shelter",
            "resource_type": "Shelter",
            "quantity_total": 100.0,
            "quantity_available": 0.0,
            "current_occupancy": 0.0,
            "unit": "Beds",
            "status": "CLOSED",
            "condition": "UNUSABLE",
            "location": {"latitude": 16.5080, "longitude": 80.6490},
        }
    ]

    context = AgentContext(
        situation_id="SIT-TEST-008",
        situation_title="No Feasible Shelter Test",
        emergency_type="Flood",
        description="Lowland flood with 50 people displaced.",
        location_summary="Lowlands",
        center_latitude=16.5062,
        center_longitude=80.6480,
        report_count=2,
        officer_severity_override=SeverityLevel.HIGH,
        existing_needs=[],
        parameters={
            "affected_population": 50,
            "available_shelters": sample_shelters,
            "effective_priority": "HIGH",
        },
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    output = result.structured_output
    assert output["shelter_required"] is True
    assert len(output["shelters_recommended"]) == 0
    assert output["total_shortfall"] == 50.0
    assert ShelterConflictType.NO_FEASIBLE_SHELTER.value in output["conflicts"]
    assert output["officer_attention_required"] is True


# ==============================================================================
# 3. End-to-End Central Orchestrator & API Integration Tests
# ==============================================================================

@pytest.mark.anyio
async def test_end_to_end_orchestrator_shelter_integration(client: AsyncClient):
    """10. Central Orchestrator runs all 5 agents (Priority, Needs, Resource, Conflict, Shelter) and generates CoordinationPlan."""
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    # 1. Orchestrate situation
    res = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        json={"force_refresh": True},
        headers=headers
    )
    assert res.status_code == 200, res.text
    plan = res.json()

    assert AgentName.PRIORITY_AGENT.value in plan["participating_agents"]
    assert AgentName.NEEDS_AGENT.value in plan["participating_agents"]
    assert AgentName.RESOURCE_COORDINATION_AGENT.value in plan["participating_agents"]
    assert AgentName.CONFLICT_RESOLUTION_AGENT.value in plan["participating_agents"]
    assert AgentName.SHELTER_AGENT.value in plan["participating_agents"]

    # Verify shelter summary structure
    assert "shelter_summary" in plan
    assert "recommended_shelters" in plan

    # 2. Check dedicated shelters endpoint
    plan_id = plan["plan_id"]
    shelters_res = await client.get(
        f"/api/v1/officer/coordination/plans/{plan_id}/shelters",
        headers=headers
    )
    assert shelters_res.status_code == 200
    shelter_data = shelters_res.json()
    assert "shelter_required" in shelter_data
    assert "total_capacity_available" in shelter_data


@pytest.mark.anyio
async def test_officer_review_with_modified_shelters(client: AsyncClient):
    """11. Emergency Officer modifies shelter allocations during human-in-the-loop review."""
    headers = await get_officer_headers(client)
    sit_id = await create_test_situation_cluster(client, headers)

    # 1. Orchestrate
    res = await client.post(
        f"/api/v1/officer/coordination/situations/{sit_id}/orchestrate",
        json={"force_refresh": True},
        headers=headers
    )
    assert res.status_code == 200
    plan = res.json()
    plan_id = plan["plan_id"]

    # 2. Officer modifies shelter allocations
    review_res = await client.post(
        f"/api/v1/officer/coordination/plans/{plan_id}/review",
        json={
            "action": PlanReviewAction.MODIFY.value,
            "notes": "Adjusted shelter occupancy due to ground floor repairs.",
            "modified_shelters": [
                {
                    "shelter_id": "RES-SHL-MOD-01",
                    "shelter_name": "Relief High School",
                    "distance_km": 1.5,
                    "total_capacity": 100.0,
                    "current_occupancy": 10.0,
                    "remaining_capacity": 90.0,
                    "recommended_occupancy": 45.0,
                    "coverage_percentage": 50.0,
                    "suitability_score": 90.0,
                    "recommendation_reason": "Officer adjusted capacity.",
                    "status": "AVAILABLE",
                }
            ]
        },
        headers=headers
    )
    assert review_res.status_code == 200
    updated_plan = review_res.json()
    assert updated_plan["status"] == CoordinationPlanStatus.MODIFIED.value
    assert len(updated_plan["recommended_shelters"]) == 1
    assert updated_plan["recommended_shelters"][0]["recommended_occupancy"] == 45.0
    assert "shelters" in updated_plan["officer_review"]["modified_fields"]


@pytest.mark.anyio
async def test_unauthorized_user_cannot_orchestrate_shelters(client: AsyncClient):
    """12. Unauthorized role cannot execute shelter coordination."""
    rm_headers = await get_resource_manager_headers(client)
    res = await client.post(
        "/api/v1/officer/coordination/situations/SIT-UNAUTH/orchestrate",
        json={"force_refresh": True},
        headers=rm_headers
    )
    assert res.status_code in [403, 404]


@pytest.mark.anyio
async def test_zero_dummy_data_in_shelter_coordination(client: AsyncClient):
    """13. Ensure zero dummy or hardcoded shelter records are fabricated."""
    agent = ShelterCoordinationAgent()
    context = AgentContext(
        situation_id="SIT-ZERO-DUMMY",
        situation_title="Zero Dummy Data Test",
        emergency_type="Flood",
        description="Disaster situation with no shelters in database.",
        location_summary="Isolated Island",
        center_latitude=10.0000,
        center_longitude=70.0000,
        report_count=1,
        officer_severity_override=SeverityLevel.HIGH,
        existing_needs=[],
        parameters={
            "affected_population": 50,
            "available_shelters": [],  # Empty real database result
            "effective_priority": "HIGH",
        },
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    output = result.structured_output
    # Must NOT invent fake shelters
    assert len(output["shelters_recommended"]) == 0
    assert output["total_capacity_available"] == 0.0
    assert output["total_population_covered"] == 0.0
    assert output["total_shortfall"] == 50.0
