import pytest
import uuid
from datetime import datetime, timezone
from httpx import AsyncClient
from app.models.enums import UserRole, EmergencyType, ReportStatus, ReportPriority, TimelineEventType
from app.db.mongodb import db_manager
from app.core.security import get_password_hash


@pytest.fixture
async def setup_test_officers():
    """Provisions two test officers in isolated test DB."""
    test_db = db_manager.db
    assert test_db is not None
    now = datetime.now(timezone.utc)
    
    # Officer 1: Dipesh Kumar
    await test_db["users"].update_one(
        {"phone": "9999999002"},
        {"$set": {
            "phone": "9999999002",
            "full_name": "Dipesh Kumar",
            "email": "dipesh.kumar@resilience.gov",
            "role": UserRole.EMERGENCY_OFFICER.value,
            "is_active": True,
            "badge_number": "EOC-408",
            "department_or_agency": "Incident Command Center",
            "hashed_password": get_password_hash("OfficerPassword@2026"),
            "volunteer_profile": None,
            "auth_provider": "local",
            "created_at": now,
            "updated_at": now,
        }},
        upsert=True
    )

    # Officer 2: Officer Jane Doe
    await test_db["users"].update_one(
        {"phone": "9999999098"},
        {"$set": {
            "phone": "9999999098",
            "full_name": "Officer Jane Doe",
            "email": "jane.doe@resilience.gov",
            "role": UserRole.EMERGENCY_OFFICER.value,
            "is_active": True,
            "badge_number": "EOC-512",
            "department_or_agency": "Regional Command Post",
            "hashed_password": get_password_hash("OfficerPassword@2026"),
            "volunteer_profile": None,
            "auth_provider": "local",
            "created_at": now,
            "updated_at": now,
        }},
        upsert=True
    )


async def get_auth_token(client: AsyncClient, phone: str, password: str = "OfficerPassword@2026") -> dict:
    res = await client.post("/api/v1/auth/login", json={"phone": phone, "password": password})
    assert res.status_code == 200
    token = res.json()["access_token"]
    user_data = res.json()["user"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "user": user_data}


@pytest.mark.anyio
async def test_dipesh_kumar_creates_events_with_correct_identity(client: AsyncClient, setup_test_officers):
    """1. Authenticated Dipesh Kumar creates events -> actor is Dipesh Kumar."""
    auth_dipesh = await get_auth_token(client, "9999999002")
    headers = auth_dipesh["headers"]

    # Submit test report
    rep_res = await client.post(
        "/api/v1/citizen/reports",
        json={
            "full_name": "Test Citizen",
            "phone": f"987{uuid.uuid4().int % 10000000:07d}",
            "emergency_type": EmergencyType.FLOOD.value,
            "description": "Rising waters on ground floor.",
            "location": {"latitude": 17.3850, "longitude": 78.4867, "city": "Hyderabad"},
            "media": []
        }
    )
    assert rep_res.status_code == 201
    report_id = rep_res.json()["report_id"]

    # Dipesh views report
    v_res = await client.get(f"/api/v1/officer/reports/{report_id}", headers=headers)
    assert v_res.status_code == 200
    v_event = [e for e in v_res.json()["timeline"] if e["event_type"] == TimelineEventType.REPORT_VIEWED.value][0]
    assert v_event["actor_name"] == "Dipesh Kumar"
    assert v_event["actor_id"] == auth_dipesh["user"]["id"]

    # Dipesh acknowledges report
    ack_res = await client.post(f"/api/v1/officer/reports/{report_id}/acknowledge", headers=headers)
    assert ack_res.status_code == 200
    ack_event = [e for e in ack_res.json()["timeline"] if e["event_type"] == TimelineEventType.REPORT_ACKNOWLEDGED.value][0]
    assert ack_event["actor_name"] == "Dipesh Kumar"
    assert ack_res.json()["acknowledged_by"] == "Dipesh Kumar"

    # Dipesh changes priority
    prio_res = await client.patch(
        f"/api/v1/officer/reports/{report_id}/priority",
        json={"priority": ReportPriority.HIGH.value},
        headers=headers
    )
    assert prio_res.status_code == 200
    prio_event = [e for e in prio_res.json()["timeline"] if e["event_type"] == TimelineEventType.PRIORITY_CHANGED.value][0]
    assert prio_event["actor_name"] == "Dipesh Kumar"

    # Dipesh adds note
    note_res = await client.post(
        f"/api/v1/officer/reports/{report_id}/notes",
        json={"note": "Monitoring area closely with quick response team."},
        headers=headers
    )
    assert note_res.status_code == 200
    note_event = [e for e in note_res.json()["timeline"] if e["event_type"] == TimelineEventType.NOTE_ADDED.value][0]
    assert note_event["actor_name"] == "Dipesh Kumar"


@pytest.mark.anyio
async def test_another_officer_creates_event_with_own_identity(client: AsyncClient, setup_test_officers):
    """2 & 5. Another authorized officer creates events -> actor is that officer."""
    auth_jane = await get_auth_token(client, "9999999098")
    headers = auth_jane["headers"]

    rep_res = await client.post(
        "/api/v1/citizen/reports",
        json={
            "full_name": "Test Citizen 2",
            "phone": f"987{uuid.uuid4().int % 10000000:07d}",
            "emergency_type": EmergencyType.FIRE.value,
            "description": "Small brush fire near park perimeter.",
            "location": {"latitude": 19.0760, "longitude": 72.8777, "city": "Mumbai"},
            "media": []
        }
    )
    report_id = rep_res.json()["report_id"]

    v_res = await client.get(f"/api/v1/officer/reports/{report_id}", headers=headers)
    assert v_res.status_code == 200
    v_event = [e for e in v_res.json()["timeline"] if e["event_type"] == TimelineEventType.REPORT_VIEWED.value][0]
    assert v_event["actor_name"] == "Officer Jane Doe"
    assert v_event["actor_id"] == auth_jane["user"]["id"]


@pytest.mark.anyio
async def test_duplicate_report_view_cooldown_deduplication(client: AsyncClient, setup_test_officers):
    """4. Duplicate report view within cooldown -> only one new REPORT_VIEWED event."""
    auth_dipesh = await get_auth_token(client, "9999999002")
    headers = auth_dipesh["headers"]

    rep_res = await client.post(
        "/api/v1/citizen/reports",
        json={
            "full_name": "Rapid View Citizen",
            "phone": f"987{uuid.uuid4().int % 10000000:07d}",
            "emergency_type": EmergencyType.MEDICAL_EMERGENCY.value,
            "description": "Ambulance requested for injured hiker.",
            "location": {"latitude": 13.0827, "longitude": 80.2707, "city": "Chennai"},
            "media": []
        }
    )
    report_id = rep_res.json()["report_id"]

    # Call GET 5 times rapidly
    for _ in range(5):
        await client.get(f"/api/v1/officer/reports/{report_id}", headers=headers)

    detail_res = await client.get(f"/api/v1/officer/reports/{report_id}", headers=headers)
    timeline = detail_res.json()["timeline"]
    view_events = [e for e in timeline if e["event_type"] == TimelineEventType.REPORT_VIEWED.value]
    assert len(view_events) == 1


@pytest.mark.anyio
async def test_different_officer_viewing_same_report_creates_separate_event(client: AsyncClient, setup_test_officers):
    """5. Different officer viewing same report -> separate legitimate actor event."""
    auth_dipesh = await get_auth_token(client, "9999999002")
    auth_jane = await get_auth_token(client, "9999999098")

    rep_res = await client.post(
        "/api/v1/citizen/reports",
        json={
            "full_name": "Multi Officer Citizen",
            "phone": f"987{uuid.uuid4().int % 10000000:07d}",
            "emergency_type": EmergencyType.OTHER.value,
            "description": "Power grid fluctuation reported.",
            "location": {"latitude": 22.5726, "longitude": 88.3639, "city": "Kolkata"},
            "media": []
        }
    )
    report_id = rep_res.json()["report_id"]

    # Dipesh views
    await client.get(f"/api/v1/officer/reports/{report_id}", headers=auth_dipesh["headers"])
    # Jane views
    await client.get(f"/api/v1/officer/reports/{report_id}", headers=auth_jane["headers"])

    detail_res = await client.get(f"/api/v1/officer/reports/{report_id}", headers=auth_dipesh["headers"])
    view_events = [e for e in detail_res.json()["timeline"] if e["event_type"] == TimelineEventType.REPORT_VIEWED.value]
    assert len(view_events) == 2
    actors = {v["actor_name"] for v in view_events}
    assert "Dipesh Kumar" in actors
    assert "Officer Jane Doe" in actors


@pytest.mark.anyio
async def test_timeline_sorted_by_canonical_timestamp(client: AsyncClient, setup_test_officers):
    """6 & 7. Timeline sorted by canonical timestamp and API returns timezone-aware ISO strings."""
    auth_dipesh = await get_auth_token(client, "9999999002")
    headers = auth_dipesh["headers"]

    rep_res = await client.post(
        "/api/v1/citizen/reports",
        json={
            "full_name": "Chronology Citizen",
            "phone": f"987{uuid.uuid4().int % 10000000:07d}",
            "emergency_type": EmergencyType.CYCLONE_STORM.value,
            "description": "High wind gusts knocking down power cables.",
            "location": {"latitude": 20.2961, "longitude": 85.8245, "city": "Bhubaneswar"},
            "media": []
        }
    )
    report_id = rep_res.json()["report_id"]

    # Execute workflow sequence
    await client.get(f"/api/v1/officer/reports/{report_id}", headers=headers)
    await client.post(f"/api/v1/officer/reports/{report_id}/acknowledge", headers=headers)
    await client.patch(f"/api/v1/officer/reports/{report_id}/priority", json={"priority": ReportPriority.CRITICAL.value}, headers=headers)
    await client.post(f"/api/v1/officer/reports/{report_id}/notes", json={"note": "Evacuation shelters active."}, headers=headers)
    await client.patch(f"/api/v1/officer/reports/{report_id}/status", json={"status": ReportStatus.UNDER_ASSESSMENT.value}, headers=headers)

    detail_res = await client.get(f"/api/v1/officer/reports/{report_id}", headers=headers)
    timeline = detail_res.json()["timeline"]

    # Verify strictly monotonic or non-decreasing timestamps
    for i in range(len(timeline) - 1):
        t1 = datetime.fromisoformat(timeline[i]["timestamp"])
        t2 = datetime.fromisoformat(timeline[i+1]["timestamp"])
        assert t1 <= t2
        assert t1.tzinfo is not None  # Must be timezone-aware
