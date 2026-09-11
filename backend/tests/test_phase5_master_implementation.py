import pytest
import uuid
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.mongodb import db_manager
from app.models.enums import (
    AgentName,
    AgentRunStatus,
    CoordinationPlanStatus,
    PlanReviewAction,
    SeverityLevel,
    NeedUrgency,
    ResourceType,
    TimelineEventType,
    UserRole,
    HealthcareConflictType,
    VolunteerConflictType,
    RouteConflictType,
    ConflictType,
)
from app.models.agent import (
    AgentContext,
    CoordinationPlan,
    PlanRecommendedResource,
    RecommendedShelter,
    RecommendedHealthcareFacility,
    RecommendedVolunteerAssignment,
    RecommendedTransport,
    RecommendedRoute,
)
from app.services.agents.registry import agent_registry
from app.services.agents.orchestrator import central_orchestrator, compute_situation_state_fingerprint
from app.services.agents.adapters.healthcare_agent import HealthcareCoordinationAgent
from app.services.agents.adapters.volunteer_agent import VolunteerCoordinationAgent
from app.services.agents.adapters.route_agent import RouteTransportCoordinationAgent
from app.services.agents.adapters.conflict_agent import ConflictResolutionAgent


@pytest.mark.anyio
async def test_all_8_domain_agents_registered():
    """
    Validates that all 8 domain agent adapters are registered in the global registry
    with correct names, purposes, and dependency configurations.
    """
    expected_agents = [
        AgentName.PRIORITY_AGENT,
        AgentName.NEEDS_AGENT,
        AgentName.RESOURCE_COORDINATION_AGENT,
        AgentName.SHELTER_AGENT,
        AgentName.HEALTHCARE_AGENT,
        AgentName.VOLUNTEER_AGENT,
        AgentName.ROUTE_AGENT,
        AgentName.CONFLICT_RESOLUTION_AGENT,
    ]
    for agent_name in expected_agents:
        assert agent_registry.has_agent(agent_name), f"Agent {agent_name} must be registered."
        agent = agent_registry.get(agent_name)
        assert agent is not None
        assert agent.name == agent_name
        assert len(agent.purpose) > 0


@pytest.mark.anyio
async def test_healthcare_coordination_agent_logic():
    """
    Tests HealthcareCoordinationAgent:
    - Identifies casualties and medical need
    - Evaluates available hospitals by proximity and bed availability
    - Computes medical shortfall and casualty coverage
    """
    agent = HealthcareCoordinationAgent()
    
    mock_facilities = [
        {
            "resource_id": "HOSP-01",
            "name": "Central Memorial Hospital",
            "resource_type": "Hospital",
            "category": "Hospital",
            "quantity_total": 50.0,
            "quantity_available": 10.0,
            "location": {"latitude": 16.2400, "longitude": 80.6400, "address": "100 Medical Blvd"},
            "icu_available": 4,
            "oxygen_available": True,
            "trauma_capable": True,
            "status": "AVAILABLE",
        },
        {
            "resource_id": "HOSP-02",
            "name": "Suburban Health Center",
            "resource_type": "Hospital",
            "category": "Hospital",
            "quantity_total": 20.0,
            "quantity_available": 5.0,
            "location": {"latitude": 16.3000, "longitude": 80.7000, "address": "200 Health Way"},
            "icu_available": 1,
            "oxygen_available": True,
            "trauma_capable": False,
            "status": "AVAILABLE",
        },
    ]

    context = AgentContext(
        situation_id="SIT-TEST-MED1",
        situation_title="Building Collapse with Injuries",
        emergency_type="Building Collapse",
        description="Multi-story structure collapse with trapped civilians and multiple injuries.",
        location_summary="Downtown Sector 4",
        center_latitude=16.2415,
        center_longitude=80.6433,
        report_count=3,
        parameters={
            "effective_priority": "CRITICAL",
            "estimated_casualties": 25,
            "available_facilities": mock_facilities,
        },
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    assert result.confidence >= 0.85

    summary = result.structured_output
    assert summary["medical_required"] is True
    assert summary["estimated_casualties"] == 25
    assert len(summary["facilities_recommended"]) == 2
    # 10 + 5 = 15 total covered out of 25 -> 10 shortfall
    assert summary["total_patients_covered"] == 15.0
    assert summary["total_shortfall"] == 10.0
    assert summary["officer_attention_required"] is True
    assert HealthcareConflictType.HEALTHCARE_CAPACITY_SHORTAGE.value in summary["conflicts"]


@pytest.mark.anyio
async def test_volunteer_coordination_agent_logic():
    """
    Tests VolunteerCoordinationAgent:
    - Filters inactive or unavailable volunteers
    - Matches verified skill profile and proximity zone
    - Calculates assigned volunteer personnel and shortfalls
    """
    agent = VolunteerCoordinationAgent()

    mock_volunteers = [
        {
            "volunteer_id": "VOL-01",
            "full_name": "Ravi Kumar",
            "role": "VOLUNTEER",
            "is_active": True,
            "skills": ["Search and Rescue", "First Aid"],
            "availability": "Available Immediately",
            "zone_or_district": "Central District",
            "phone": "+919876543210",
        },
        {
            "volunteer_id": "VOL-02",
            "full_name": "Anita Roy",
            "role": "VOLUNTEER",
            "is_active": True,
            "skills": ["First Aid", "Medical Support"],
            "availability": "Available Immediately",
            "zone_or_district": "Central District",
            "phone": "+919876543211",
        },
        {
            "volunteer_id": "VOL-03",
            "full_name": "Suresh Patel",
            "role": "VOLUNTEER",
            "is_active": False,  # inactive
            "skills": ["Search and Rescue"],
            "availability": "Available Immediately",
        },
        {
            "volunteer_id": "VOL-04",
            "full_name": "Deepa Nair",
            "role": "VOLUNTEER",
            "is_active": True,
            "skills": ["Search and Rescue"],
            "availability": "Unavailable",  # unavailable
        },
    ]

    context = AgentContext(
        situation_id="SIT-TEST-VOL1",
        situation_title="Major Landslide Incident",
        emergency_type="Landslide",
        description="Massive mudslide blocking valley access with multiple affected households.",
        location_summary="Central District",
        center_latitude=16.2415,
        center_longitude=80.6433,
        report_count=2,
        parameters={
            "effective_priority": "CRITICAL",  # baseline 6 needed
            "available_volunteers": mock_volunteers,
        },
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    summary = result.structured_output
    assert summary["volunteers_required"] is True
    assert summary["estimated_volunteers_needed"] == 6
    assert summary["total_volunteers_assigned"] == 2  # VOL-01 & VOL-02
    assert summary["total_shortfall"] == 4
    assert summary["officer_attention_required"] is True
    assert VolunteerConflictType.VOLUNTEER_SHORTAGE.value in summary["conflicts"]


@pytest.mark.anyio
async def test_route_transport_coordination_agent_logic():
    """
    Tests RouteTransportCoordinationAgent:
    - Evaluates vehicles and calculates routes between origins and situation
    - Detects vehicle shortfall and maps transit corridors
    """
    agent = RouteTransportCoordinationAgent()

    mock_vehicles = [
        {
            "transport_id": "VEH-01",
            "name": "Heavy Supply Truck Alpha",
            "resource_type": "Transport",
            "category": "Vehicle",
            "quantity_available": 1.0,
            "location": {"latitude": 16.2100, "longitude": 80.6100, "address": "South Fleet Yard"},
            "status": "AVAILABLE",
        },
        {
            "transport_id": "VEH-02",
            "name": "Field Ambulance 01",
            "resource_type": "Transport",
            "category": "Vehicle",
            "quantity_available": 1.0,
            "location": {"latitude": 16.2200, "longitude": 80.6200, "address": "Metro Base"},
            "status": "AVAILABLE",
        },
    ]

    context = AgentContext(
        situation_id="SIT-TEST-ROT1",
        situation_title="Flood Disaster Logistics",
        emergency_type="Flood",
        description="Severe flooding requiring immediate food/water supply transit and casualty extraction.",
        location_summary="River Delta Zone",
        center_latitude=16.2415,
        center_longitude=80.6433,
        report_count=4,
        parameters={
            "effective_priority": "HIGH",
            "affected_population": 50,
            "estimated_casualties": 5,
            "available_vehicles": mock_vehicles,
            "recommended_allocations": [{"resource_type": "Water", "quantity": 100}],
        },
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    summary = result.structured_output
    assert summary["transport_required"] is True
    assert len(summary["transports_recommended"]) == 2
    assert len(summary["routes_recommended"]) >= 1


@pytest.mark.anyio
async def test_conflict_agent_cross_domain_consolidation():
    """
    Tests ConflictResolutionAgent with multi-domain inputs:
    - Resource supply deficits
    - Shelter capacity shortfalls
    - Hospital bed deficits
    - Volunteer shortages
    - Blocked routes
    """
    agent = ConflictResolutionAgent()

    context = AgentContext(
        situation_id="SIT-TEST-CNF1",
        situation_title="Cyclone Compound Emergency",
        emergency_type="Cyclone / Storm",
        description="High intensity cyclonic storm with widespread structural damage and flooding.",
        location_summary="Coastal Belt Area",
        center_latitude=16.2415,
        center_longitude=80.6433,
        report_count=5,
        parameters={
            "assessed_needs": [
                {"resource_type": "Water", "requested_quantity": 500, "urgency": "CRITICAL", "unit": "Liters"},
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Water",
                    "quantity_required": 500,
                    "available_in_inventory": 200,
                    "allocated_quantity": 200,
                    "matched_resource_id": "RES-WTR-01",
                    "matched_resource_name": "Central Water Depot",
                    "urgency": "CRITICAL",
                    "unit": "Liters",
                }
            ],
            "effective_priority": "CRITICAL",
            "shelter_shortfall": 30.0,
            "healthcare_shortfall": 12.0,
            "volunteer_shortfall": 4,
            "transport_shortfall": 2,
        },
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    summary = result.structured_output
    assert summary["conflicts_count"] >= 4
    assert summary["unresolved_conflicts"] >= 3
    assert summary["resolved_conflicts"] >= 1
    assert summary["officer_attention_required"] is True

    conflict_type_strs = [
        c["conflict_type"].value if hasattr(c["conflict_type"], "value") else str(c["conflict_type"])
        for c in summary["conflicts_detected"]
    ]
    assert (
        ConflictType.INSUFFICIENT_QUANTITY.value in conflict_type_strs
        or ConflictType.RESOURCE_SHORTAGE.value in conflict_type_strs
    )
    assert ConflictType.SHELTER_CAPACITY_CONFLICT.value in conflict_type_strs
    assert ConflictType.HEALTHCARE_TRANSPORT_MISMATCH.value in conflict_type_strs
    assert ConflictType.VOLUNTEER_AVAILABILITY_CONFLICT.value in conflict_type_strs


@pytest.mark.anyio
async def test_orchestrator_e2e_8_agent_pipeline():
    """
    Tests full Central Orchestrator executing all 8 domain agents end-to-end
    and generating an authoritative CoordinationPlan in MongoDB.
    """
    db = db_manager.db
    assert db is not None

    sit_id = f"SIT-{uuid.uuid4().hex[:8].upper()}"
    situation_doc = {
        "situation_id": sit_id,
        "title": "Severe Coastal Inundation Cluster",
        "emergency_type": "Flood",
        "status": "ACTIVE",
        "computed_severity_level": "HIGH",
        "computed_severity_score": 75,
        "report_ids": ["REP-001", "REP-002"],
        "report_count": 2,
        "center_location": {
            "latitude": 16.2415,
            "longitude": 80.6433,
            "address": "East Coast Sector",
        },
        "estimated_affected_population": 40,
        "estimated_casualties": 8,
        "assessed_needs": [
            {"resource_type": "Water", "requested_quantity": 100, "urgency": "HIGH", "unit": "Liters"},
            {"resource_type": "Blankets", "requested_quantity": 40, "urgency": "MEDIUM", "unit": "Units"},
        ],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db["situations"].insert_one(situation_doc)

    actor = {
        "id": "USR-OFFICER-01",
        "full_name": "Commander Sarah Jenkins",
        "role": "EMERGENCY_OFFICER",
    }

    # Run orchestration
    plan = await central_orchestrator.orchestrate_situation(
        situation_id=sit_id,
        actor=actor,
        force_refresh=True,
        db=db,
    )

    assert plan is not None
    assert plan.situation_id == sit_id
    assert plan.status == CoordinationPlanStatus.PENDING_OFFICER_REVIEW
    assert len(plan.participating_agents) == 8
    assert plan.healthcare_summary is not None
    assert plan.volunteer_summary is not None
    assert plan.route_summary is not None
    assert plan.shelter_summary is not None
    assert plan.conflict_summary is not None

    # Verify idempotency fingerprint
    fp = compute_situation_state_fingerprint(situation_doc)
    assert plan.state_fingerprint == fp

    # Re-running without force_refresh must return identical plan (idempotent)
    plan_repeat = await central_orchestrator.orchestrate_situation(
        situation_id=sit_id,
        actor=actor,
        force_refresh=False,
        db=db,
    )
    assert plan_repeat.plan_id == plan.plan_id
    assert plan_repeat.version == plan.version


@pytest.mark.anyio
async def test_human_officer_review_and_modifications():
    """
    Tests Emergency Officer review with domain modifications:
    - Modify allocations, shelters, facilities, and volunteers
    - Approves with officer operational notes
    - Verifies timeline audit event persistence
    """
    db = db_manager.db
    assert db is not None

    sit_id = f"SIT-{uuid.uuid4().hex[:8].upper()}"
    situation_doc = {
        "situation_id": sit_id,
        "title": "Multi-Zone Industrial Fire",
        "emergency_type": "Fire",
        "status": "ACTIVE",
        "computed_severity_level": "CRITICAL",
        "report_ids": ["REP-FIRE-01"],
        "report_count": 1,
        "center_location": {"latitude": 16.2415, "longitude": 80.6433},
        "estimated_affected_population": 20,
        "estimated_casualties": 4,
        "created_at": datetime.now(timezone.utc),
    }
    await db["situations"].insert_one(situation_doc)

    actor = {
        "id": "USR-OFFICER-02",
        "full_name": "Officer Marcus Vance",
        "role": "EMERGENCY_OFFICER",
    }

    plan = await central_orchestrator.orchestrate_situation(
        situation_id=sit_id,
        actor=actor,
        force_refresh=True,
        db=db,
    )

    # Perform modification review
    modified_allocations = [
        PlanRecommendedResource(
            resource_type=ResourceType.WATER,
            quantity_required=200.0,
            unit="Liters",
            urgency=NeedUrgency.CRITICAL,
            allocated_quantity=150.0,
            reasoning="Officer adjusted allocation based on high priority tanker availability.",
        )
    ]

    modified_facilities = [
        RecommendedHealthcareFacility(
            facility_id="HOSP-MOD-1",
            facility_name="Trauma Center North",
            distance_km=4.2,
            total_beds=40,
            available_beds=15,
            allocated_patients=4,
            coverage_percentage=100.0,
            icu_available=2,
            oxygen_available=True,
            trauma_capable=True,
            emergency_capable=True,
            suitability_score=95.0,
            ranking_factors={},
            recommendation_reason="Officer directed primary trauma routing.",
        )
    ]

    reviewed_plan = await central_orchestrator.review_coordination_plan(
        plan_id=plan.plan_id,
        action=PlanReviewAction.MODIFY,
        actor=actor,
        notes="Adjusted water tanker allocation and directed trauma routing to Trauma Center North.",
        modified_allocations=modified_allocations,
        modified_facilities=modified_facilities,
        db=db,
    )

    assert reviewed_plan.status == CoordinationPlanStatus.MODIFIED
    assert reviewed_plan.officer_review is not None
    assert reviewed_plan.officer_review.decision == PlanReviewAction.MODIFY
    assert reviewed_plan.officer_review.reviewed_by_name == "Officer Marcus Vance"
    assert len(reviewed_plan.recommended_allocations) == 1
    assert reviewed_plan.recommended_allocations[0].allocated_quantity == 150.0
    assert len(reviewed_plan.recommended_facilities) == 1
    assert reviewed_plan.recommended_facilities[0].facility_id == "HOSP-MOD-1"


@pytest.mark.anyio
async def test_officer_api_inspection_endpoints(client: AsyncClient):
    """
    Tests officer REST endpoints:
    - GET /coordination/plans/{id}/healthcare
    - GET /coordination/plans/{id}/volunteers
    - GET /coordination/plans/{id}/routes
    - POST /coordination/plans/{id}/review with modification payload
    """
    db = db_manager.db
    assert db is not None

    sit_id = f"SIT-{uuid.uuid4().hex[:8].upper()}"
    await db["situations"].insert_one({
        "situation_id": sit_id,
        "title": "Flash Flood Wave",
        "emergency_type": "Flood",
        "status": "ACTIVE",
        "computed_severity_level": "HIGH",
        "report_ids": ["REP-FF-01"],
        "report_count": 1,
        "center_location": {"latitude": 16.2415, "longitude": 80.6433},
        "estimated_affected_population": 15,
        "created_at": datetime.now(timezone.utc),
    })

    actor = {"id": "USR-OFFICER-01", "full_name": "Commander Sarah Jenkins", "role": "EMERGENCY_OFFICER"}
    plan = await central_orchestrator.orchestrate_situation(situation_id=sit_id, actor=actor, force_refresh=True, db=db)

    # Login as Emergency Officer to obtain bearer token
    login_res = await client.post("/api/v1/auth/login", json={
        "phone": "9999999002",
        "password": "OfficerPassword@2026",
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Test Healthcare Endpoint
    hlt_res = await client.get(f"/api/v1/officer/coordination/plans/{plan.plan_id}/healthcare", headers=headers)
    assert hlt_res.status_code == 200
    assert "medical_required" in hlt_res.json()

    # 2. Test Volunteers Endpoint
    vol_res = await client.get(f"/api/v1/officer/coordination/plans/{plan.plan_id}/volunteers", headers=headers)
    assert vol_res.status_code == 200
    assert "volunteers_required" in vol_res.json()

    # 3. Test Routes Endpoint
    rot_res = await client.get(f"/api/v1/officer/coordination/plans/{plan.plan_id}/routes", headers=headers)
    assert rot_res.status_code == 200
    assert "transport_required" in rot_res.json()

    # 4. Test Review Endpoint Approval
    rev_res = await client.post(
        f"/api/v1/officer/coordination/plans/{plan.plan_id}/review",
        headers=headers,
        json={
            "action": "APPROVE",
            "notes": "Plan approved for execution by Incident Commander.",
        },
    )
    assert rev_res.status_code == 200
    reviewed_data = rev_res.json()
    assert reviewed_data["status"] == "APPROVED"
    assert reviewed_data["officer_review"]["decision"] == "APPROVE"
