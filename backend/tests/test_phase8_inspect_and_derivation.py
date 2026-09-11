import pytest
import uuid
from datetime import datetime, timezone

from app.db.mongodb import get_database
from app.models.enums import (
    SeverityLevel,
    NeedUrgency,
    ResourceType,
    CoordinationPlanStatus,
    PlanReviewAction,
    TaskType,
    ResponseTaskStatus,
    UserRole,
    AgentName,
)
from app.models.agent import (
    CoordinationPlan,
    PlanRecommendedResource,
    RecommendedShelter,
    RecommendedHealthcareFacility,
    RecommendedVolunteerAssignment,
    RecommendedRoute,
)
from app.services.field_operations_service import FieldOperationsService
from app.services.agents.orchestrator import central_orchestrator
from app.services.notification.whatsapp_provider import MockableWhatsAppProvider
from app.services.notification import set_whatsapp_provider_override


@pytest.fixture(autouse=True)
def setup_test_provider():
    mock_provider = MockableWhatsAppProvider(configured=True, should_succeed=True)
    set_whatsapp_provider_override(mock_provider)
    yield mock_provider
    set_whatsapp_provider_override(None)


def build_sample_coordination_plan():
    situation_id = f"SIT-INSP-{uuid.uuid4().hex[:6].upper()}"
    plan_id = f"PLN-INSP-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now(timezone.utc)

    allocations = [
        PlanRecommendedResource(
            resource_type=ResourceType.WATER,
            quantity_required=500.0,
            unit="Liters",
            urgency=NeedUrgency.HIGH,
            matched_resource_id=f"RES-WAT-{uuid.uuid4().hex[:4].upper()}",
            matched_resource_name="Clean Bottled Water",
            available_in_inventory=1000.0,
            allocated_quantity=500.0,
            depot_location="Main Regional Depot",
            distance_km=4.2,
        ),
        PlanRecommendedResource(
            resource_type=ResourceType.FOOD,
            quantity_required=200.0,
            unit="Kits",
            urgency=NeedUrgency.HIGH,
            matched_resource_id=f"RES-FOOD-{uuid.uuid4().hex[:4].upper()}",
            matched_resource_name="Emergency Food Rations",
            available_in_inventory=500.0,
            allocated_quantity=200.0,
            depot_location="North Stockpile",
            distance_km=6.0,
        ),
    ]

    shelters = [
        RecommendedShelter(
            shelter_id=f"SHL-{uuid.uuid4().hex[:4].upper()}",
            shelter_name="Community Center Shelter",
            distance_km=3.5,
            total_capacity=200.0,
            current_occupancy=48.0,
            remaining_capacity=152.0,
            recommended_occupancy=150.0,
            coverage_percentage=100.0,
            suitability_score=95.0,
            recommendation_reason="Primary evacuation facility.",
        )
    ]

    facilities = [
        RecommendedHealthcareFacility(
            facility_id=f"HCF-{uuid.uuid4().hex[:4].upper()}",
            facility_name="District General Hospital",
            distance_km=5.0,
            total_beds=100.0,
            available_beds=30.0,
            allocated_patients=15.0,
            suitability_score=92.0,
            recommendation_reason="Trauma capability & ICU readiness verified.",
        )
    ]

    volunteers = [
        RecommendedVolunteerAssignment(
            volunteer_id=f"VOL-{uuid.uuid4().hex[:4].upper()}",
            volunteer_name="Dr. Sarah Connor",
            role_or_skill="Medical First Responder",
            assigned_operation="Casualty Triage",
            suitability_score=98.0,
            availability_status="Available Immediately",
            recommendation_reason="Certified emergency doctor.",
        )
    ]

    routes = [
        RecommendedRoute(
            route_id=f"ROT-{uuid.uuid4().hex[:4].upper()}",
            origin_name="Main Depot",
            destination_name="Community Center",
            origin_coordinates={"latitude": 16.3, "longitude": 80.4},
            destination_coordinates={"latitude": 16.32, "longitude": 80.42},
            distance_km=4.5,
            estimated_duration_minutes=15.0,
            assigned_mission="Supply Logistics Corridor",
            recommendation_reason="Clear highway route.",
        )
    ]

    return CoordinationPlan(
        plan_id=plan_id,
        situation_id=situation_id,
        version=5,
        state_fingerprint=f"FINGERPRINT_{uuid.uuid4().hex[:6]}",
        generated_at=now,
        participating_agents=[
            AgentName.PRIORITY_AGENT,
            AgentName.NEEDS_AGENT,
            AgentName.RESOURCE_COORDINATION_AGENT,
            AgentName.SHELTER_AGENT,
            AgentName.HEALTHCARE_AGENT,
            AgentName.VOLUNTEER_AGENT,
            AgentName.ROUTE_AGENT,
            AgentName.CONFLICT_RESOLUTION_AGENT,
        ],
        assessed_priority=SeverityLevel.HIGH,
        assessed_needs=[],
        recommended_allocations=allocations,
        recommended_shelters=shelters,
        recommended_facilities=facilities,
        recommended_volunteers=volunteers,
        recommended_routes=routes,
        reasoning="Test active coordination plan v5 with multi-domain allocations.",
        constraints=["Advisory only."],
        confidence=0.96,
        status=CoordinationPlanStatus.ACTIVE,
    )


@pytest.mark.anyio
async def test_01_derive_tasks_from_active_response_plan_idempotency():
    """
    Verifies that derive_tasks_from_plan deterministically produces tasks across all domains
    and does NOT duplicate tasks on repeated calls.
    """
    db = get_database()
    sample_plan = build_sample_coordination_plan()

    officer_actor = {
        "id": "OFFICER-001",
        "full_name": "Chief Operations Officer",
        "role": UserRole.EMERGENCY_OFFICER.value,
    }

    # First derivation
    tasks_1 = await FieldOperationsService.derive_tasks_from_plan(
        plan=sample_plan,
        officer_actor=officer_actor,
        db=db,
    )

    # 2 resource deliveries + 1 shelter + 1 healthcare + 1 volunteer + 1 route = 6 tasks
    assert len(tasks_1) == 6

    # Verify task types
    types = [t.task_type for t in tasks_1]
    assert TaskType.RESOURCE_DELIVERY in types
    assert TaskType.SHELTER_ACTIVATION in types
    assert TaskType.PATIENT_EVACUATION in types
    assert TaskType.ROUTE_CLEARANCE in types

    total_in_db = await db["response_tasks"].count_documents({"plan_id": sample_plan.plan_id})
    assert total_in_db == 6

    # Second derivation (Idempotency test)
    tasks_2 = await FieldOperationsService.derive_tasks_from_plan(
        plan=sample_plan,
        officer_actor=officer_actor,
        db=db,
    )

    assert len(tasks_2) == 6
    total_in_db_after = await db["response_tasks"].count_documents({"plan_id": sample_plan.plan_id})
    assert total_in_db_after == 6, "Repeated derivation must NOT create duplicate tasks in database."


@pytest.mark.anyio
async def test_02_field_operations_overview_auto_derivation_and_kpis():
    """
    Verifies that get_overview accurately counts ACTIVE plans and automatically derives tasks
    when an active plan is present for a situation.
    """
    db = get_database()
    sample_plan = build_sample_coordination_plan()

    # Insert active plan into coordination_plans
    plan_dict = sample_plan.model_dump()
    plan_dict["generated_at"] = plan_dict["generated_at"].isoformat()
    await db["coordination_plans"].insert_one(plan_dict)

    sit_id = sample_plan.situation_id

    # Call get_overview for the situation
    overview = await FieldOperationsService.get_overview(situation_id=sit_id, db=db)

    # Verify KPIs
    assert overview.active_plans_count >= 1, "Active plan count must reflect the real active plan."
    assert overview.total_tasks_count == 6, "Total tasks count must match derived operational tasks."
    assert overview.approved_tasks_count + overview.assigned_tasks_count == 6
    assert overview.active_volunteers_count >= 1, "Assigned volunteers must be counted."


@pytest.mark.anyio
async def test_03_list_tasks_auto_derivation():
    """
    Verifies that list_tasks returns genuine derived tasks for an active incident situation.
    """
    db = get_database()
    sample_plan = build_sample_coordination_plan()

    # Insert active plan into coordination_plans
    plan_dict = sample_plan.model_dump()
    plan_dict["generated_at"] = plan_dict["generated_at"].isoformat()
    await db["coordination_plans"].insert_one(plan_dict)

    sit_id = sample_plan.situation_id

    # List tasks for this situation
    paginated = await FieldOperationsService.list_tasks(situation_id=sit_id, db=db)

    assert paginated.total == 6
    assert len(paginated.items) == 6
    for item in paginated.items:
        assert item.situation_id == sit_id
        assert item.plan_id == sample_plan.plan_id


@pytest.mark.anyio
async def test_04_central_orchestrator_review_approval_task_derivation():
    """
    Verifies that officer review approval in CentralOrchestrator transitions plan to ACTIVE
    and triggers task derivation.
    """
    db = get_database()
    sample_plan = build_sample_coordination_plan()

    # Create pending review plan
    pending_plan = sample_plan.model_copy()
    pending_plan.plan_id = f"PLN-PENDING-{uuid.uuid4().hex[:4].upper()}"
    pending_plan.status = CoordinationPlanStatus.PENDING_OFFICER_REVIEW

    plan_dict = pending_plan.model_dump()
    plan_dict["generated_at"] = plan_dict["generated_at"].isoformat()
    await db["coordination_plans"].insert_one(plan_dict)

    actor = {
        "id": "OFFICER-002",
        "full_name": "Emergency Officer Commander",
        "role": UserRole.EMERGENCY_OFFICER.value,
    }

    reviewed = await central_orchestrator.review_coordination_plan(
        plan_id=pending_plan.plan_id,
        action=PlanReviewAction.APPROVE,
        actor=actor,
        notes="Approved for full ground deployment.",
        db=db,
    )

    assert reviewed.status == CoordinationPlanStatus.APPROVED

    # Check that tasks were derived
    tasks = await FieldOperationsService.list_tasks(situation_id=pending_plan.situation_id, db=db)
    assert tasks.total == 6


@pytest.mark.anyio
async def test_05_empty_optional_domains_safety():
    """
    Verifies that plans with completely empty domain lists or missing summaries
    still derive valid tasks without errors or crashes.
    """
    db = get_database()
    sit_id = f"SIT-EMPTY-{uuid.uuid4().hex[:4].upper()}"
    plan_id = f"PLN-EMPTY-{uuid.uuid4().hex[:4].upper()}"

    empty_plan = CoordinationPlan(
        plan_id=plan_id,
        situation_id=sit_id,
        version=1,
        generated_at=datetime.now(timezone.utc),
        participating_agents=[],
        assessed_priority=SeverityLevel.LOW,
        assessed_needs=[],
        recommended_allocations=[],
        recommended_shelters=[],
        recommended_facilities=[],
        recommended_volunteers=[],
        recommended_transports=[],
        recommended_routes=[],
        reasoning="General monitoring plan with no active resource demand.",
        status=CoordinationPlanStatus.ACTIVE,
    )

    actor = {
        "id": "SYS",
        "full_name": "System Operations",
        "role": UserRole.EMERGENCY_OFFICER.value,
    }

    derived = await FieldOperationsService.derive_tasks_from_plan(
        plan=empty_plan,
        officer_actor=actor,
        db=db,
    )

    # General command fallback task created
    assert len(derived) == 1
    assert derived[0].task_type == TaskType.GENERAL_FIELD_OPERATION

    overview = await FieldOperationsService.get_overview(situation_id=sit_id, db=db)
    assert overview.total_tasks_count >= 1


@pytest.mark.anyio
async def test_06_real_database_plans_serialization_and_contract():
    """
    Verifies that all real coordination plans in MongoDB Atlas (including v5)
    serialize cleanly to JSON and adhere to the canonical schema required by
    CoordinationPlanModal.
    """
    db = get_database()
    cursor = db["coordination_plans"].find().sort("generated_at", -1).limit(20)
    async for doc in cursor:
        plan = CoordinationPlan(**doc)
        data = plan.model_dump()
        assert "plan_id" in data
        assert "situation_id" in data
        assert "version" in data
        assert "status" in data
        assert isinstance(data.get("recommended_allocations", []), list)
        assert isinstance(data.get("recommended_shelters", []), list)
        assert isinstance(data.get("recommended_facilities", []), list)
        assert isinstance(data.get("recommended_volunteers", []), list)
        assert isinstance(data.get("recommended_transports", []), list)
        assert isinstance(data.get("recommended_routes", []), list)
        assert isinstance(data.get("conflicts", []), list)

