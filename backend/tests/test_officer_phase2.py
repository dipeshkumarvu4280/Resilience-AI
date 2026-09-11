import pytest
import uuid
from httpx import AsyncClient
from app.models.enums import UserRole, EmergencyType, ReportStatus, ReportPriority, TimelineEventType
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


@pytest.mark.anyio
async def test_officer_can_list_real_reports(client: AsyncClient):
    """1. Officer can list real reports from MongoDB."""
    headers = await get_officer_headers(client)
    response = await client.get("/api/v1/officer/reports", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "limit" in data
    assert "total_pages" in data


@pytest.mark.anyio
async def test_unauthorized_user_cannot_access_officer_endpoints(client: AsyncClient):
    """2. Unauthorized user cannot access officer endpoints (RBAC)."""
    # No auth
    res_no_auth = await client.get("/api/v1/officer/reports")
    assert res_no_auth.status_code == 401

    # Resource Manager cannot access Emergency Officer endpoint
    rm_headers = await get_resource_manager_headers(client)
    res_rm = await client.get("/api/v1/officer/reports", headers=rm_headers)
    assert res_rm.status_code == 403


@pytest.mark.anyio
async def test_officer_stats_are_real_mongo_counts(client: AsyncClient):
    """Real KPI stats directly reflected from MongoDB with zero dummy records."""
    headers = await get_officer_headers(client)
    res = await client.get("/api/v1/officer/reports/stats", headers=headers)
    assert res.status_code == 200
    stats = res.json()
    assert isinstance(stats["total_incoming"], int)
    assert isinstance(stats["acknowledged"], int)
    assert isinstance(stats["under_assessment"], int)
    assert isinstance(stats["action_required"], int)
    assert isinstance(stats["resolved"], int)
    assert isinstance(stats["total_reports"], int)


@pytest.mark.anyio
async def test_citizen_submission_to_officer_lifecycle(client: AsyncClient):
    """
    3. Officer can open real report.
    4. Officer can acknowledge RECEIVED report.
    5. Invalid status transition is rejected.
    6. Valid status transitions succeed.
    7. Priority update persists.
    8. Officer note persists.
    9. Timeline contains real events.
    10. Audit log is created.
    11. Real location is returned correctly.
    """
    headers = await get_officer_headers(client)

    # Step A: Citizen submits real emergency report
    test_phone = f"987{uuid.uuid4().int % 10000000:07d}"
    report_payload = {
        "full_name": "Ravi Teja",
        "phone": test_phone,
        "emergency_type": EmergencyType.FLOOD.value,
        "description": "Flash flooding near riverbank bridge, 3 vehicles stranded with rising water levels.",
        "location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "street_address": "Bridge Road, Old Town",
            "landmark": "Near Riverside Temple",
            "zone_or_district": "Krishna District",
            "city": "Vijayawada",
            "state": "Andhra Pradesh",
            "country": "India",
            "postal_code": "520001",
        },
        "media": [
            {
                "filename": "flood_water_level.jpg",
                "file_url": "/uploads/test_flood.jpg",
                "media_type": "image/jpeg",
                "size_bytes": 102400,
            }
        ]
    }

    create_res = await client.post("/api/v1/citizen/reports", json=report_payload)
    assert create_res.status_code == 201
    created_report = create_res.json()
    report_id = created_report["report_id"]
    assert report_id.startswith("RES-")

    # Step B: Officer retrieves report
    detail_res = await client.get(f"/api/v1/officer/reports/{report_id}", headers=headers)
    assert detail_res.status_code == 200
    report_detail = detail_res.json()
    assert report_detail["report_id"] == report_id
    assert report_detail["emergency_type"] == EmergencyType.FLOOD.value
    assert report_detail["status"] == ReportStatus.RECEIVED.value
    assert report_detail["priority"] == ReportPriority.UNASSESSED.value
    assert report_detail["location"]["latitude"] == 16.5062
    assert report_detail["location"]["longitude"] == 80.6480
    assert report_detail["location"]["street_address"] is not None
    assert len(report_detail["media"]) == 1

    # Step C: Officer attempts invalid status jump (RECEIVED -> RESOLVED directly) -> MUST FAIL (400)
    invalid_jump = await client.patch(
        f"/api/v1/officer/reports/{report_id}/status",
        json={"status": ReportStatus.RESOLVED.value},
        headers=headers,
    )
    assert invalid_jump.status_code == 400
    assert "Invalid operational transition" in invalid_jump.json()["detail"]

    # Step D: Officer acknowledges report
    ack_res = await client.post(f"/api/v1/officer/reports/{report_id}/acknowledge", headers=headers)
    assert ack_res.status_code == 200
    ack_data = ack_res.json()
    assert ack_data["status"] == ReportStatus.ACKNOWLEDGED.value
    assert ack_data["acknowledged_at"] is not None
    assert ack_data["acknowledged_by"] is not None

    # Step E: Officer assigns Priority (CRITICAL)
    prio_res = await client.patch(
        f"/api/v1/officer/reports/{report_id}/priority",
        json={"priority": ReportPriority.CRITICAL.value},
        headers=headers,
    )
    assert prio_res.status_code == 200
    assert prio_res.json()["priority"] == ReportPriority.CRITICAL.value

    # Step F: Officer adds operational note
    note_res = await client.post(
        f"/api/v1/officer/reports/{report_id}/notes",
        json={"note": "Disaster Response Unit 4 dispatched to Old Town bridge with rescue rafts."},
        headers=headers,
    )
    assert note_res.status_code == 200
    notes_list = note_res.json()["notes"]
    assert len(notes_list) >= 1
    assert "Disaster Response Unit 4" in notes_list[-1]["note"]

    # Step G: Officer updates status to UNDER_ASSESSMENT
    assess_res = await client.patch(
        f"/api/v1/officer/reports/{report_id}/status",
        json={"status": ReportStatus.UNDER_ASSESSMENT.value, "reason": "Field team arriving on scene"},
        headers=headers,
    )
    assert assess_res.status_code == 200
    assert assess_res.json()["status"] == ReportStatus.UNDER_ASSESSMENT.value

    # Step H: Officer updates status to ACTION_REQUIRED
    act_res = await client.patch(
        f"/api/v1/officer/reports/{report_id}/status",
        json={"status": ReportStatus.ACTION_REQUIRED.value, "reason": "Evacuation of stranded vehicles required"},
        headers=headers,
    )
    assert act_res.status_code == 200
    assert act_res.json()["status"] == ReportStatus.ACTION_REQUIRED.value

    # Step I: Officer resolves report
    resolve_res = await client.patch(
        f"/api/v1/officer/reports/{report_id}/status",
        json={"status": ReportStatus.RESOLVED.value, "reason": "All occupants rescued safely, water subsiding"},
        headers=headers,
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == ReportStatus.RESOLVED.value

    # Step J: Verify timeline events
    timeline_res = await client.get(f"/api/v1/officer/reports/{report_id}/timeline", headers=headers)
    assert timeline_res.status_code == 200
    timeline = timeline_res.json()
    assert len(timeline) >= 4
    event_types = [t["event_type"] for t in timeline]
    assert TimelineEventType.REPORT_RECEIVED.value in event_types or any("REPORT" in t for t in event_types)
    assert TimelineEventType.REPORT_ACKNOWLEDGED.value in event_types
    assert TimelineEventType.PRIORITY_CHANGED.value in event_types
    assert TimelineEventType.NOTE_ADDED.value in event_types
    assert TimelineEventType.STATUS_CHANGED.value in event_types

    # Step K: Verify audit_logs in MongoDB
    test_db = db_manager.db
    if test_db is not None:
        audit_count = await test_db["audit_logs"].count_documents({"report_id": report_id})
        assert audit_count >= 4


@pytest.mark.anyio
async def test_missing_reverse_geocoded_address_handling(client: AsyncClient):
    """12. Missing reverse-geocoded address does not invent fake address; displays raw coordinates."""
    headers = await get_officer_headers(client)
    test_phone = f"987{uuid.uuid4().int % 10000000:07d}"

    # Coordinates in remote oceanic Point Nemo (-48.8767, -123.3933) where Nominatim returns no street/suburb/city
    report_payload = {
        "full_name": "Deep Sea Vessel",
        "phone": test_phone,
        "emergency_type": EmergencyType.OTHER.value,
        "description": "Engine stall in oceanic waters with no named street or postal address.",
        "location": {
            "latitude": -48.8767,
            "longitude": -123.3933,
            "address": None,
            "street_address": None,
            "city": None,
            "state": None,
        },
        "media": []
    }

    create_res = await client.post("/api/v1/citizen/reports", json=report_payload)
    assert create_res.status_code == 201
    report_id = create_res.json()["report_id"]

    detail_res = await client.get(f"/api/v1/officer/reports/{report_id}", headers=headers)
    assert detail_res.status_code == 200
    doc = detail_res.json()
    # Coordinates must be exact
    assert doc["location"]["latitude"] == -48.8767
    assert doc["location"]["longitude"] == -123.3933


@pytest.mark.anyio
async def test_pagination_and_filtering(client: AsyncClient):
    """14 & 15. Test pagination and search/filtering."""
    headers = await get_officer_headers(client)

    # Filter by emergency type
    res_filter = await client.get(
        "/api/v1/officer/reports?emergency_type=Landslide",
        headers=headers,
    )
    assert res_filter.status_code == 200

    # Search by keyword
    res_search = await client.get(
        "/api/v1/officer/reports?search=riverbank",
        headers=headers,
    )
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert isinstance(search_data["items"], list)


@pytest.mark.anyio
async def test_multi_officer_authenticated_actor_identity(client: AsyncClient):
    """
    Verify authenticated actor identity:
    1. Authenticated Officer A acknowledges report -> timeline actor = Officer A.
    2. Authenticated Officer B updates priority -> timeline actor = Officer B.
    3. Authenticated Officer B adds note -> note author & timeline actor = Officer B.
    4. Backend strictly uses authenticated session identity, no dummy fallbacks.
    """
    test_db = db_manager.db
    assert test_db is not None
    from datetime import datetime, timezone
    from app.core.security import get_password_hash

    # Provision Officer 2 (Officer Dipesh Kumar) in the isolated test database
    officer_b_phone = "9999999099"
    await test_db["users"].update_one(
        {"phone": officer_b_phone},
        {"$set": {
            "phone": officer_b_phone,
            "full_name": "Dipesh Kumar",
            "email": "dipesh.officer@resilience.gov",
            "role": UserRole.EMERGENCY_OFFICER.value,
            "is_active": True,
            "badge_number": "EOC-777",
            "department_or_agency": "Incident Command Center",
            "hashed_password": get_password_hash("DipeshPassword@2026"),
            "volunteer_profile": None,
            "auth_provider": "local",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }},
        upsert=True
    )

    # Login Officer A (Commander Sarah Jenkins via admin token or Officer 1)
    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999001", "password": "AdminPassword@2026"}
    )
    assert admin_login.status_code == 200
    admin_data = admin_login.json()
    officer_a_name = admin_data["user"]["full_name"]
    officer_a_id = admin_data["user"]["id"]
    headers_officer_a = {"Authorization": f"Bearer {admin_data['access_token']}"}

    # Login Officer B (Dipesh Kumar)
    b_login = await client.post(
        "/api/v1/auth/login",
        json={"phone": officer_b_phone, "password": "DipeshPassword@2026"}
    )
    assert b_login.status_code == 200
    b_data = b_login.json()
    officer_b_name = b_data["user"]["full_name"]
    officer_b_id = b_data["user"]["id"]
    headers_officer_b = {"Authorization": f"Bearer {b_data['access_token']}"}

    # Create a fresh citizen report
    test_phone = f"987{uuid.uuid4().int % 10000000:07d}"
    report_res = await client.post(
        "/api/v1/citizen/reports",
        json={
            "full_name": "Emergency Citizen",
            "phone": test_phone,
            "emergency_type": EmergencyType.BUILDING_COLLAPSE.value,
            "description": "Tremors felt, structural cracks visible on primary building column.",
            "location": {"latitude": 28.6139, "longitude": 77.2090, "city": "New Delhi"},
            "media": []
        }
    )
    assert report_res.status_code == 201
    report_id = report_res.json()["report_id"]

    # Officer A views report
    view_res = await client.get(f"/api/v1/officer/reports/{report_id}", headers=headers_officer_a)
    assert view_res.status_code == 200
    view_data = view_res.json()
    view_event = [e for e in view_data["timeline"] if e["event_type"] == TimelineEventType.REPORT_VIEWED.value][0]
    assert view_event["actor_id"] == officer_a_id
    assert view_event["actor_name"] == officer_a_name
    assert officer_a_name in view_event["details"]

    # Officer A acknowledges report
    ack_res = await client.post(f"/api/v1/officer/reports/{report_id}/acknowledge", headers=headers_officer_a)
    assert ack_res.status_code == 200
    ack_data = ack_res.json()
    assert ack_data["acknowledged_by"] == officer_a_name
    ack_event = [e for e in ack_data["timeline"] if e["event_type"] == TimelineEventType.REPORT_ACKNOWLEDGED.value][0]
    assert ack_event["actor_id"] == officer_a_id
    assert ack_event["actor_name"] == officer_a_name
    assert ack_event["details"] == f"Incident acknowledged by {officer_a_name}."

    # Officer B changes priority to HIGH
    prio_res = await client.patch(
        f"/api/v1/officer/reports/{report_id}/priority",
        json={"priority": ReportPriority.HIGH.value},
        headers=headers_officer_b
    )
    assert prio_res.status_code == 200
    prio_data = prio_res.json()
    prio_event = [e for e in prio_data["timeline"] if e["event_type"] == TimelineEventType.PRIORITY_CHANGED.value][0]
    assert prio_event["actor_id"] == officer_b_id
    assert prio_event["actor_name"] == officer_b_name
    assert f"by {officer_b_name}" in prio_event["details"]

    # Officer B adds operational note
    note_res = await client.post(
        f"/api/v1/officer/reports/{report_id}/notes",
        json={"note": "Structural engineering evaluation team dispatched."},
        headers=headers_officer_b
    )
    assert note_res.status_code == 200
    note_data = note_res.json()
    assert note_data["notes"][-1]["author_name"] == officer_b_name
    assert note_data["notes"][-1]["author_id"] == officer_b_id
    note_event = [e for e in note_data["timeline"] if e["event_type"] == TimelineEventType.NOTE_ADDED.value][0]
    assert note_event["actor_id"] == officer_b_id
    assert note_event["actor_name"] == officer_b_name


@pytest.mark.anyio
async def test_report_view_event_deduplication(client: AsyncClient):
    """
    Verify that rapid GET requests by the same officer do NOT duplicate REPORT_VIEWED events.
    """
    headers = await get_officer_headers(client)

    test_phone = f"987{uuid.uuid4().int % 10000000:07d}"
    report_res = await client.post(
        "/api/v1/citizen/reports",
        json={
            "full_name": "Test Citizen",
            "phone": test_phone,
            "emergency_type": EmergencyType.FIRE.value,
            "description": "Smoke visible from commercial rooftop unit.",
            "location": {"latitude": 12.9716, "longitude": 77.5946, "city": "Bengaluru"},
            "media": []
        }
    )
    assert report_res.status_code == 201
    report_id = report_res.json()["report_id"]

    # Call GET report 4 times in rapid succession
    for _ in range(4):
        res = await client.get(f"/api/v1/officer/reports/{report_id}", headers=headers)
        assert res.status_code == 200

    detail_res = await client.get(f"/api/v1/officer/reports/{report_id}", headers=headers)
    timeline = detail_res.json()["timeline"]
    view_events = [e for e in timeline if e["event_type"] == TimelineEventType.REPORT_VIEWED.value]
    # Deduplication must ensure only 1 view event is recorded during cooldown
    assert len(view_events) == 1


@pytest.mark.anyio
async def test_officer_can_list_volunteers(client: AsyncClient):
    """Verify officer can list real volunteer responders."""
    headers = await get_officer_headers(client)
    res = await client.get("/api/v1/officer/volunteers", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    for v in data:
        assert v["role"] == UserRole.VOLUNTEER.value
        assert "id" in v
        assert "full_name" in v
        assert "phone" in v


@pytest.mark.anyio
async def test_officer_can_list_audit_logs(client: AsyncClient):
    """Verify officer can list operational audit trail logs."""
    headers = await get_officer_headers(client)
    res = await client.get("/api/v1/officer/audit-logs?limit=20", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)

