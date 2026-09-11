import uuid
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient

from app.db.mongodb import get_database
from app.models.enums import (
    SituationStatus,
    ResponseTaskStatus,
    TaskType,
    CoordinationPlanStatus,
    TimelineEventType,
    UserRole,
)
from app.models.task import (
    ResponseTask,
    IncidentResolutionRequest,
    IncidentCloseRequest,
)
from app.models.agent import CoordinationPlan
from app.services.field_operations_service import FieldOperationsService


async def get_auth_token(client: AsyncClient, phone: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"phone": phone, "password": password})
    assert res.status_code == 200, f"Login failed: {res.text}"
    return res.json()["access_token"]


@pytest.mark.anyio
async def test_a_valid_incident_closure_and_summary():
    """A. Test valid incident closure and authoritative post-incident summary compilation."""
    db = get_database()
    sit_id = f"SIT-{uuid.uuid4().hex[:6].upper()}"
    officer_actor = {"id": "OFF-001", "full_name": "Commander Varma", "role": "EMERGENCY_OFFICER"}

    now = datetime.now(timezone.utc)
    await db.situations.insert_one({
        "situation_id": sit_id,
        "title": "Severe Coastal Inundation",
        "emergency_type": "Flood",
        "status": SituationStatus.RESPONSE_IN_PROGRESS.value,
        "report_count": 4,
        "created_at": now,
        "updated_at": now,
    })

    # Add 2 tasks (1 completed, 1 completed with resources)
    task1 = ResponseTask(
        task_id=f"TSK-{uuid.uuid4().hex[:4].upper()}",
        situation_id=sit_id,
        plan_id="PLN-COAST-01",
        plan_version=1,
        task_type=TaskType.RESOURCE_DELIVERY,
        title="Distribute Inflatable Rafts",
        description="Deploy 5 rafts to flood zone",
        status=ResponseTaskStatus.COMPLETED,
        assigned_volunteer_ids=["VOL-001", "VOL-002"],
        assigned_vehicle_id="VEH-TRUCK-01",
        assigned_resources=[{
            "resource_id": "RES-RAFT-01",
            "resource_name": "Inflatable Raft",
            "resource_type": "EQUIPMENT",
            "allocated_quantity": 5.0,
            "consumed_quantity": 5.0,
            "unit": "units",
        }],
    )
    await db.response_tasks.insert_one(task1.model_dump())

    # First resolve incident
    await FieldOperationsService.resolve_incident(
        situation_id=sit_id,
        officer_actor=officer_actor,
        req=IncidentResolutionRequest(resolution_notes="Flood waters receded. Evacuations complete."),
        db=db,
    )

    # Now close incident
    summary = await FieldOperationsService.close_incident(
        situation_id=sit_id,
        officer_actor=officer_actor,
        req=IncidentCloseRequest(close_notes="Debrief concluded. All resources accounted for."),
        db=db,
    )

    assert summary.final_status == SituationStatus.CLOSED.value
    assert summary.situation_id == sit_id
    assert summary.tasks_completed == 1
    assert summary.total_tasks_created == 1
    assert summary.volunteers_involved_count == 2
    assert summary.vehicles_involved_count == 1
    assert len(summary.resources_utilized) == 1
    assert summary.resources_utilized[0]["resource_name"] == "Inflatable Raft"
    assert summary.resources_utilized[0]["quantity_consumed"] == 5.0

    # Direct DB verification
    sit_doc = await db.situations.find_one({"situation_id": sit_id})
    assert sit_doc["status"] == SituationStatus.CLOSED.value
    assert sit_doc["closed_by"] == "Commander Varma"


@pytest.mark.anyio
async def test_b_closure_blocked_by_incomplete_tasks():
    """B. Test that active/uncompleted tasks prevent incident closure unless explicitly overridden."""
    db = get_database()
    sit_id = f"SIT-{uuid.uuid4().hex[:6].upper()}"
    officer_actor = {"id": "OFF-001", "full_name": "Commander Varma", "role": "EMERGENCY_OFFICER"}

    await db.situations.insert_one({
        "situation_id": sit_id,
        "title": "Industrial Gas Explosion",
        "emergency_type": "Hazmat",
        "status": SituationStatus.RESPONSE_IN_PROGRESS.value,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    task = ResponseTask(
        task_id=f"TSK-{uuid.uuid4().hex[:4].upper()}",
        situation_id=sit_id,
        plan_id="PLN-HAZ-01",
        task_type=TaskType.PATIENT_EVACUATION,
        title="Evacuate Sector B",
        description="Air ambulance dispatch",
        status=ResponseTaskStatus.IN_PROGRESS,
    )
    await db.response_tasks.insert_one(task.model_dump())

    # Attempt close without override -> should fail
    with pytest.raises(ValueError) as exc:
        await FieldOperationsService.close_incident(
            situation_id=sit_id,
            officer_actor=officer_actor,
            req=IncidentCloseRequest(
                close_notes="Premature close attempt",
                force_override_uncompleted=False,
            ),
            db=db,
        )
    assert "UNCOMPLETED_OPERATIONS" in str(exc.value)

    # Attempt close WITH force_override_uncompleted -> should succeed
    summary = await FieldOperationsService.close_incident(
        situation_id=sit_id,
        officer_actor=officer_actor,
        req=IncidentCloseRequest(
            close_notes="Commander override: scene handed over to national guard.",
            force_override_uncompleted=True,
            override_reason="Jurisdiction transfer",
        ),
        db=db,
    )
    assert summary.final_status == SituationStatus.CLOSED.value


@pytest.mark.anyio
async def test_c_closure_already_closed_fails():
    """F & G. Test closing an already closed situation raises explainable error."""
    db = get_database()
    sit_id = f"SIT-{uuid.uuid4().hex[:6].upper()}"
    officer_actor = {"id": "OFF-001", "full_name": "Commander Varma", "role": "EMERGENCY_OFFICER"}

    await db.situations.insert_one({
        "situation_id": sit_id,
        "title": "Structure Collapse",
        "emergency_type": "Earthquake",
        "status": SituationStatus.CLOSED.value,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    with pytest.raises(ValueError) as exc:
        await FieldOperationsService.close_incident(
            situation_id=sit_id,
            officer_actor=officer_actor,
            req=IncidentCloseRequest(close_notes="Second close attempt"),
            db=db,
        )
    assert "already CLOSED" in str(exc.value)


@pytest.mark.anyio
async def test_d_closure_short_notes_pydantic_validation():
    """H. Test that closure notes under 5 characters fail Pydantic model validation."""
    with pytest.raises(Exception):
        IncidentCloseRequest(close_notes="bad")


@pytest.mark.anyio
async def test_e_legacy_situation_without_plan_closure():
    """E. Test closure of legacy situation with no AI plan but genuine completed operational tasks."""
    db = get_database()
    sit_id = f"SIT-{uuid.uuid4().hex[:6].upper()}"
    officer_actor = {"id": "OFF-001", "full_name": "Commander Varma", "role": "EMERGENCY_OFFICER"}

    # Insert situation without any coordination_plans document
    await db.situations.insert_one({
        "situation_id": sit_id,
        "title": "Legacy Storm Alert",
        "emergency_type": "Severe Weather",
        "status": SituationStatus.RESOLVED.value,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    # Direct manual task
    task = ResponseTask(
        task_id=f"TSK-{uuid.uuid4().hex[:4].upper()}",
        situation_id=sit_id,
        plan_id="DIRECT-DISPATCH",
        task_type=TaskType.ROUTE_CLEARANCE,
        title="Clear Tree Debris",
        description="Manual road clearing",
        status=ResponseTaskStatus.COMPLETED,
    )
    await db.response_tasks.insert_one(task.model_dump())

    summary = await FieldOperationsService.close_incident(
        situation_id=sit_id,
        officer_actor=officer_actor,
        req=IncidentCloseRequest(close_notes="Legacy storm incident successfully concluded and archived."),
        db=db,
    )
    assert summary.final_status == SituationStatus.CLOSED.value
    assert summary.active_plan_versions == 0
    assert summary.tasks_completed == 1


@pytest.mark.anyio
async def test_f_audit_timeline_event_creation():
    """M. Test that closing an incident writes an immutable timeline event with authenticated officer details."""
    db = get_database()
    sit_id = f"SIT-{uuid.uuid4().hex[:6].upper()}"
    officer_actor = {"id": "OFF-999", "full_name": "Captain Rogers", "role": "EMERGENCY_OFFICER"}

    await db.situations.insert_one({
        "situation_id": sit_id,
        "title": "Wildfire Zone A",
        "emergency_type": "Fire",
        "status": SituationStatus.RESOLVED.value,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    await FieldOperationsService.close_incident(
        situation_id=sit_id,
        officer_actor=officer_actor,
        req=IncidentCloseRequest(close_notes="Fire fully contained by perimeter trenches."),
        db=db,
    )

    timeline_event = await db.timeline_events.find_one({
        "report_id": sit_id,
        "event_type": TimelineEventType.INCIDENT_CLOSED.value,
    })
    assert timeline_event is not None
    assert timeline_event["actor_name"] == "Captain Rogers"
    assert timeline_event["actor_id"] == "OFF-999"
    assert "close_notes" in timeline_event["metadata"]


@pytest.mark.anyio
async def test_g_rest_api_closure_endpoint_and_validation_error_format(client: AsyncClient):
    """R & I. Test REST API /incidents/{situation_id}/close returns structured validation error."""
    token = await get_auth_token(client, "9999999002", "OfficerPassword@2026")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Invalid payload (short close_notes) -> HTTP 422 with structured errors
    res_422 = await client.post(
        "/api/v1/field-operations/incidents/SIT-TEST/close",
        json={"close_notes": "tiny"},
        headers=headers,
    )
    assert res_422.status_code == 422
    data_422 = res_422.json()
    assert "code" in data_422
    assert data_422["code"] == "VALIDATION_ERROR"
    assert "close_notes" in data_422["detail"]

    # 2. Non-existent situation -> HTTP 400 with detail
    res_400 = await client.post(
        "/api/v1/field-operations/incidents/SIT-NONEXISTENT/close",
        json={"close_notes": "Valid length notes for missing situation."},
        headers=headers,
    )
    assert res_400.status_code == 400
    assert "not found" in res_400.json()["detail"].lower()
