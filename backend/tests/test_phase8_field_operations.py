import pytest
import uuid
from datetime import datetime, timezone
from httpx import AsyncClient

from app.db.mongodb import get_database, db_manager
from app.models.enums import (
    UserRole,
    SeverityLevel,
    SituationStatus,
    CoordinationPlanStatus,
    ResponseTaskStatus,
    TaskType,
    FieldUpdateType,
    ResourceType,
    ResourceStatus,
    NeedUrgency,
)
from app.models.agent import (
    CoordinationPlan,
    PlanRecommendedResource,
    RecommendedShelter,
    RecommendedHealthcareFacility,
    RecommendedVolunteerAssignment,
    RecommendedRoute,
)
from app.models.task import (
    ResponseTask,
    TaskAssignmentRequest,
    TaskStatusTransitionRequest,
    FieldUpdateCreateRequest,
    IncidentResolutionRequest,
    IncidentCloseRequest,
)
from app.services.field_operations_service import FieldOperationsService
from app.services.notification.whatsapp_provider import MockableWhatsAppProvider
from app.services.notification import set_whatsapp_provider_override


@pytest.fixture(autouse=True)
def setup_test_provider():
    mock_provider = MockableWhatsAppProvider(configured=True, should_succeed=True)
    set_whatsapp_provider_override(mock_provider)
    yield mock_provider
    set_whatsapp_provider_override(None)


async def get_auth_token(client: AsyncClient, phone: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"phone": phone, "password": password})
    assert res.status_code == 200, f"Login failed: {res.text}"
    return res.json()["access_token"]


@pytest.mark.anyio
async def test_01_derive_tasks_from_active_response_plan():
    """1. Test deriving executable ResponseTasks from an approved CoordinationPlan."""
    db = get_database()
    await FieldOperationsService.ensure_indexes(db)

    sit_id = f"SIT-PH8-{uuid.uuid4().hex[:6].upper()}"
    plan_id = f"PLN-{uuid.uuid4().hex[:6].upper()}"

    # Insert Situation
    await db.situations.insert_one({
        "situation_id": sit_id,
        "title": "Severe Coastal Inundation",
        "emergency_type": "Flood",
        "status": SituationStatus.ACTIVE.value,
        "center_location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "address": "Bunder Road, Vijayawada",
        },
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    plan = CoordinationPlan(
        plan_id=plan_id,
        situation_id=sit_id,
        version=1,
        assessed_priority=SeverityLevel.HIGH,
        reasoning="Multi-domain emergency response for severe coastal flood.",
        recommended_allocations=[
            PlanRecommendedResource(
                resource_type=ResourceType.WATER,
                quantity_required=500.0,
                unit="Liters",
                urgency=NeedUrgency.CRITICAL,
                matched_resource_id="RES-WTR-01",
                matched_resource_name="Potable Water Tanker 01",
                allocated_quantity=500.0,
                depot_location="Central Depot North",
                distance_km=4.2,
                reasoning="Emergency drinking water deployment for inundated sectors.",
            )
        ],
        recommended_shelters=[
            RecommendedShelter(
                shelter_id="SHL-01",
                shelter_name="Community High School Shelter",
                distance_km=2.5,
                total_capacity=200.0,
                current_occupancy=20.0,
                remaining_capacity=180.0,
                recommended_occupancy=100.0,
                coverage_percentage=100.0,
                suitability_score=95.0,
                recommendation_reason="Primary high ground evacuation shelter.",
                location_address="School Road Sector 2",
                latitude=16.5120,
                longitude=80.6550,
            )
        ],
        recommended_facilities=[
            RecommendedHealthcareFacility(
                facility_id="HSP-01",
                facility_name="District General Hospital",
                distance_km=3.8,
                total_beds=150.0,
                available_beds=40.0,
                allocated_patients=10.0,
                recommendation_reason="Trauma and casualty intake.",
            )
        ],
        recommended_volunteers=[
            RecommendedVolunteerAssignment(
                volunteer_id="VOL-01",
                volunteer_name="John Doe",
                role_or_skill="Search and Rescue",
                assigned_operation="Water Rescue & Evacuation Assistance",
                recommendation_reason="Certified swift water rescue responder.",
            )
        ],
        recommended_routes=[
            RecommendedRoute(
                route_id="ROT-01",
                origin_name="Central Depot North",
                destination_name="Bunder Road, Vijayawada",
                origin_coordinates={"latitude": 16.5000, "longitude": 80.6400},
                destination_coordinates={"latitude": 16.5062, "longitude": 80.6480},
                distance_km=4.2,
                estimated_duration_minutes=15.0,
                transport_id="VEH-TRK-01",
                assigned_mission="Supply Transit Corridor",
                recommendation_reason="Fastest clearance corridor.",
            )
        ],
    )

    officer_actor = {"id": "OFF-001", "full_name": "Commander Varma", "role": "EMERGENCY_OFFICER"}

    tasks = await FieldOperationsService.derive_tasks_from_plan(
        plan=plan,
        officer_actor=officer_actor,
        db=db,
    )

    assert len(tasks) == 5
    task_types = [t.task_type for t in tasks]
    assert TaskType.RESOURCE_DELIVERY in task_types
    assert TaskType.SHELTER_ACTIVATION in task_types
    assert TaskType.PATIENT_EVACUATION in task_types
    assert TaskType.SEARCH_AND_RESCUE in task_types
    assert TaskType.ROUTE_CLEARANCE in task_types

    # Verify tasks persisted in MongoDB
    saved_tasks = await db.response_tasks.find({"situation_id": sit_id}).to_list(10)
    assert len(saved_tasks) == 5

    # Verify situation updated to RESPONSE_IN_PROGRESS
    sit_check = await db.situations.find_one({"situation_id": sit_id})
    assert sit_check["status"] == SituationStatus.RESPONSE_IN_PROGRESS.value


@pytest.mark.anyio
async def test_02_task_lifecycle_state_machine():
    """2. Test strict task state machine transitions (legal and illegal)."""
    db = get_database()
    task_id = f"TSK-{uuid.uuid4().hex[:6].upper()}"
    sit_id = f"SIT-{uuid.uuid4().hex[:6].upper()}"

    task = ResponseTask(
        task_id=task_id,
        situation_id=sit_id,
        plan_id="PLN-01",
        plan_version=1,
        task_type=TaskType.RESOURCE_DELIVERY,
        title="Distribute Clean Water",
        description="Deliver 500L clean water",
        status=ResponseTaskStatus.PENDING_APPROVAL,
    )
    await db.response_tasks.insert_one(task.model_dump())

    actor = {"id": "OFF-001", "full_name": "Commander Varma", "role": "EMERGENCY_OFFICER"}
    vol_actor = {"id": "VOL-001", "full_name": "Responder Alice", "role": "VOLUNTEER"}

    # 1. Legal: PENDING_APPROVAL -> APPROVED
    t1 = await FieldOperationsService.transition_task_status(
        task_id=task_id,
        new_status=ResponseTaskStatus.APPROVED,
        actor=actor,
        db=db,
    )
    assert t1.status == ResponseTaskStatus.APPROVED

    # 2. Illegal: Cannot jump directly from APPROVED to COMPLETED
    with pytest.raises(ValueError) as exc:
        await FieldOperationsService.transition_task_status(
            task_id=task_id,
            new_status=ResponseTaskStatus.COMPLETED,
            actor=actor,
            db=db,
        )
    assert "INVALID_TASK_TRANSITION" in str(exc.value)

    # 3. Legal: APPROVED -> ASSIGNED
    t2 = await FieldOperationsService.transition_task_status(
        task_id=task_id,
        new_status=ResponseTaskStatus.ASSIGNED,
        actor=actor,
        db=db,
    )
    assert t2.status == ResponseTaskStatus.ASSIGNED

    # 4. Legal: ASSIGNED -> ACCEPTED
    t3 = await FieldOperationsService.transition_task_status(
        task_id=task_id,
        new_status=ResponseTaskStatus.ACCEPTED,
        actor=vol_actor,
        db=db,
    )
    assert t3.status == ResponseTaskStatus.ACCEPTED

    # 5. Legal: ACCEPTED -> IN_PROGRESS
    t4 = await FieldOperationsService.transition_task_status(
        task_id=task_id,
        new_status=ResponseTaskStatus.IN_PROGRESS,
        actor=vol_actor,
        db=db,
    )
    assert t4.status == ResponseTaskStatus.IN_PROGRESS
    assert t4.started_at is not None

    # 6. Legal: IN_PROGRESS -> BLOCKED
    t5 = await FieldOperationsService.transition_task_status(
        task_id=task_id,
        new_status=ResponseTaskStatus.BLOCKED,
        actor=vol_actor,
        reason="Debris blocking main delivery corridor",
        db=db,
    )
    assert t5.status == ResponseTaskStatus.BLOCKED
    assert t5.blocked_reason == "Debris blocking main delivery corridor"

    # 7. Legal: BLOCKED -> IN_PROGRESS
    t6 = await FieldOperationsService.transition_task_status(
        task_id=task_id,
        new_status=ResponseTaskStatus.IN_PROGRESS,
        actor=vol_actor,
        notes="Corridor cleared, resuming delivery",
        db=db,
    )
    assert t6.status == ResponseTaskStatus.IN_PROGRESS

    # 8. Legal: IN_PROGRESS -> COMPLETED
    t7 = await FieldOperationsService.transition_task_status(
        task_id=task_id,
        new_status=ResponseTaskStatus.COMPLETED,
        actor=vol_actor,
        completion_notes="Successfully delivered 500L clean water",
        db=db,
    )
    assert t7.status == ResponseTaskStatus.COMPLETED
    assert t7.completed_at is not None

    # 9. Illegal: Cannot transition out of COMPLETED (terminal state)
    with pytest.raises(ValueError) as exc2:
        await FieldOperationsService.transition_task_status(
            task_id=task_id,
            new_status=ResponseTaskStatus.IN_PROGRESS,
            actor=vol_actor,
            db=db,
        )
    assert "INVALID_TASK_TRANSITION" in str(exc2.value)


@pytest.mark.anyio
async def test_03_atomic_resource_consumption():
    """3. Test atomic resource consumption preventing negative inventory."""
    db = get_database()
    res_id = f"RES-WTR-{uuid.uuid4().hex[:6].upper()}"

    # Create resource in DB with 100 available
    await db.resources.insert_one({
        "resource_id": res_id,
        "name": "Mineral Water Gallons",
        "resource_type": "Water",
        "quantity_total": 100.0,
        "quantity_available": 100.0,
        "unit": "Gallons",
        "status": ResourceStatus.AVAILABLE.value,
        "location": {"latitude": 16.5, "longitude": 80.6},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    # Legal: Consume 40 units
    await FieldOperationsService.consume_resource_atomic(resource_id=res_id, quantity=40.0, db=db)
    doc = await db.resources.find_one({"resource_id": res_id})
    assert doc["quantity_available"] == 60.0

    # Illegal: Attempt to consume 70 units (more than 60 available)
    with pytest.raises(ValueError) as exc:
        await FieldOperationsService.consume_resource_atomic(resource_id=res_id, quantity=70.0, db=db)
    assert "INSUFFICIENT_INVENTORY" in str(exc.value)

    # Quantity should remain 60.0
    doc2 = await db.resources.find_one({"resource_id": res_id})
    assert doc2["quantity_available"] == 60.0


@pytest.mark.anyio
async def test_04_vehicle_assignment_conflict_prevention():
    """4. Test vehicle assignment prevents simultaneous allocation of the same vehicle to multiple active tasks."""
    db = get_database()
    veh_id = f"VEH-AMB-{uuid.uuid4().hex[:6].upper()}"

    task1 = ResponseTask(
        task_id=f"TSK-V1-{uuid.uuid4().hex[:4].upper()}",
        situation_id="SIT-01",
        plan_id="PLN-01",
        task_type=TaskType.PATIENT_EVACUATION,
        title="Evacuate Critical Patients",
        description="Patient transfer",
        status=ResponseTaskStatus.ASSIGNED,
        assigned_vehicle_id=veh_id,
        assigned_vehicle_name="Advanced Life Support Ambulance 01",
    )
    await db.response_tasks.insert_one(task1.model_dump())

    task2 = ResponseTask(
        task_id=f"TSK-V2-{uuid.uuid4().hex[:4].upper()}",
        situation_id="SIT-02",
        plan_id="PLN-02",
        task_type=TaskType.PATIENT_EVACUATION,
        title="Evacuate Secondary Ward",
        description="Patient transfer 2",
        status=ResponseTaskStatus.APPROVED,
    )
    await db.response_tasks.insert_one(task2.model_dump())

    officer_actor = {"id": "OFF-001", "full_name": "Commander Varma", "role": "EMERGENCY_OFFICER"}

    # Attempt to assign the same busy vehicle to task2
    with pytest.raises(ValueError) as exc:
        await FieldOperationsService.assign_task(
            task_id=task2.task_id,
            assignment=TaskAssignmentRequest(
                assigned_vehicle_id=veh_id,
                assigned_vehicle_name="Advanced Life Support Ambulance 01",
            ),
            officer_actor=officer_actor,
            db=db,
        )
    assert "VEHICLE_UNAVAILABLE" in str(exc.value)


@pytest.mark.anyio
async def test_05_field_updates_and_live_monitoring_hook():
    """5. Test submitting field updates and their propagation to timeline and Live Monitoring."""
    db = get_database()
    task_id = f"TSK-{uuid.uuid4().hex[:6].upper()}"
    sit_id = f"SIT-{uuid.uuid4().hex[:6].upper()}"

    task = ResponseTask(
        task_id=task_id,
        situation_id=sit_id,
        plan_id="PLN-01",
        task_type=TaskType.ROUTE_CLEARANCE,
        title="Corridor Alpha Clearance",
        description="Clear flood debris",
        status=ResponseTaskStatus.IN_PROGRESS,
    )
    await db.response_tasks.insert_one(task.model_dump())

    vol_actor = {"id": "VOL-101", "full_name": "Officer Mike", "role": "VOLUNTEER"}

    # Submit ROUTE_BLOCKED field update
    update = await FieldOperationsService.record_field_update(
        task_id=task_id,
        update_req=FieldUpdateCreateRequest(
            event_type=FieldUpdateType.ROUTE_BLOCKED,
            message="Downed high-voltage power lines blocking Highway 65.",
            details={"obstruction_type": "POWER_LINE", "severity": "CRITICAL"},
        ),
        actor=vol_actor,
        db=db,
    )

    assert update.event_type == FieldUpdateType.ROUTE_BLOCKED
    assert update.task_id == task_id

    # Verify update appended to task in DB
    updated_doc = await db.response_tasks.find_one({"task_id": task_id})
    assert len(updated_doc.get("field_updates", [])) == 1
    assert updated_doc["field_updates"][0]["message"] == "Downed high-voltage power lines blocking Highway 65."

    # Verify timeline event created
    timeline_event = await db.timeline_events.find_one({"report_id": sit_id, "metadata.task_id": task_id})
    assert timeline_event is not None


@pytest.mark.anyio
async def test_06_incident_resolution_and_closure_workflow():
    """6. Test incident resolution requirements (tasks completion guard and override) and closure summary."""
    db = get_database()
    sit_id = f"SIT-{uuid.uuid4().hex[:6].upper()}"

    # Insert active situation
    await db.situations.insert_one({
        "situation_id": sit_id,
        "title": "Industrial Hazmat Leak",
        "emergency_type": "Hazardous Materials",
        "status": SituationStatus.RESPONSE_IN_PROGRESS.value,
        "report_count": 3,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    # Insert an uncompleted task for this situation
    task = ResponseTask(
        task_id=f"TSK-ACT-{uuid.uuid4().hex[:4].upper()}",
        situation_id=sit_id,
        plan_id="PLN-HAZ-01",
        task_type=TaskType.SEARCH_AND_RESCUE,
        title="Perimeter Gas Scrubbing",
        description="Deploy chemical neutralizers",
        status=ResponseTaskStatus.IN_PROGRESS,
    )
    await db.response_tasks.insert_one(task.model_dump())

    officer_actor = {"id": "OFF-001", "full_name": "Commander Varma", "role": "EMERGENCY_OFFICER"}

    # 1. Resolve should fail because task is still IN_PROGRESS
    with pytest.raises(ValueError) as exc:
        await FieldOperationsService.resolve_incident(
            situation_id=sit_id,
            officer_actor=officer_actor,
            req=IncidentResolutionRequest(
                resolution_notes="Gas leak contained.",
                force_override_uncompleted=False,
            ),
            db=db,
        )
    assert "UNRESOLVED_OPERATIONS" in str(exc.value)

    # 2. Complete the task
    await FieldOperationsService.transition_task_status(
        task_id=task.task_id,
        new_status=ResponseTaskStatus.COMPLETED,
        actor=officer_actor,
        completion_notes="Chemical neutralizers fully deployed.",
        db=db,
    )

    # 3. Resolve now succeeds
    res = await FieldOperationsService.resolve_incident(
        situation_id=sit_id,
        officer_actor=officer_actor,
        req=IncidentResolutionRequest(
            resolution_notes="Hazard neutralized. Air quality sensors safe.",
            force_override_uncompleted=False,
        ),
        db=db,
    )
    assert res["status"] == SituationStatus.RESOLVED.value

    # 4. Close incident and generate comprehensive summary
    summary = await FieldOperationsService.close_incident(
        situation_id=sit_id,
        officer_actor=officer_actor,
        req=IncidentCloseRequest(
            close_notes="Formal post-incident review completed. Incident closed.",
        ),
        db=db,
    )
    assert summary.final_status == SituationStatus.CLOSED.value
    assert summary.tasks_completed == 1
    assert summary.total_tasks_created == 1
    assert summary.closed_by == "Commander Varma"

    # Verify situation is CLOSED in DB
    sit_doc = await db.situations.find_one({"situation_id": sit_id})
    assert sit_doc["status"] == SituationStatus.CLOSED.value


@pytest.mark.anyio
async def test_07_rest_api_field_operations_endpoints(client: AsyncClient):
    """7. Test REST API endpoints with authentication and RBAC."""
    token = await get_auth_token(client, "9999999002", "OfficerPassword@2026")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Overview
    res_ov = await client.get("/api/v1/field-operations/overview", headers=headers)
    assert res_ov.status_code == 200
    ov_data = res_ov.json()
    assert "total_tasks_count" in ov_data
    assert "active_plans_count" in ov_data

    # 2. List Tasks
    res_tasks = await client.get("/api/v1/field-operations/tasks", headers=headers)
    assert res_tasks.status_code == 200
    assert "items" in res_tasks.json()
    assert "total" in res_tasks.json()
