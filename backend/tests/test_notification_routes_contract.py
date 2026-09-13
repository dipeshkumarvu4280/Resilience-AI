import uuid
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient

from app.db.mongodb import get_database
from app.models.enums import (
    NotificationCategory,
    NotificationDeliveryStatus,
    NotificationSeverity,
    UserRole,
)
from app.models.notification import NotificationPreferenceUpdate
from app.services.notification import NotificationService, set_whatsapp_provider_override
from app.services.notification.whatsapp_provider import MockableWhatsAppProvider


@pytest.fixture(autouse=True)
def setup_mock_wa():
    mock_provider = MockableWhatsAppProvider(configured=True, should_succeed=True)
    set_whatsapp_provider_override(mock_provider)
    yield mock_provider
    set_whatsapp_provider_override(None)


async def get_token(client: AsyncClient, phone: str = "9999999002", password: str = "OfficerPassword@2026") -> str:
    res = await client.post("/api/v1/auth/login", json={"phone": phone, "password": password})
    assert res.status_code == 200, f"Login failed: {res.text}"
    return res.json()["access_token"]


# -------------------------------------------------------------
# 1. GET /api/v1/notifications authenticated user -> 200
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_get_notifications_authenticated_200(client: AsyncClient):
    token = await get_token(client)
    res = await client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)


# -------------------------------------------------------------
# 2. GET /api/v1/notifications empty collection -> valid empty list []
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_get_notifications_empty_real_collection(client: AsyncClient):
    db = get_database()
    token = await get_token(client)
    # Clear test db notifications
    await db["notifications"].delete_many({})

    res = await client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data == []


# -------------------------------------------------------------
# 3. GET /api/v1/notifications with severity filter
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_get_notifications_with_severity_filter(client: AsyncClient):
    db = get_database()
    officer = await db["users"].find_one({"phone": "9999999002"})
    officer_id = str(officer.get("user_id") or officer.get("_id") or officer.get("phone"))

    service = NotificationService()
    # Create 1 CRITICAL, 1 LOW
    await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type="CRITICAL_FLOOD_ALERT",
        severity=NotificationSeverity.CRITICAL,
        title="Critical Flood Escalation",
        message="Flash flood near main bridge",
        target_user_ids=[officer_id],
        material_state={"ts": uuid.uuid4().hex},
    )
    await service.dispatch_event(
        category=NotificationCategory.RESOURCE_LOGISTICS,
        event_type="LOW_STOCK_INFO",
        severity=NotificationSeverity.LOW,
        title="Routine Stock Info",
        message="Inventory routine update",
        target_user_ids=[officer_id],
        material_state={"ts": uuid.uuid4().hex},
    )

    token = await get_token(client)
    res = await client.get(
        "/api/v1/notifications?severity=CRITICAL",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 1
    assert all(item["severity"] == "CRITICAL" for item in items)


# -------------------------------------------------------------
# 4. GET /api/v1/notifications with unread_only=true
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_get_notifications_unread_only(client: AsyncClient):
    db = get_database()
    officer = await db["users"].find_one({"phone": "9999999002"})
    officer_id = str(officer.get("user_id") or officer.get("_id") or officer.get("phone"))

    service = NotificationService()
    notif1 = await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type="UNREAD_TEST_1",
        severity=NotificationSeverity.HIGH,
        title="Unread Incident Alert",
        message="Attention required immediately",
        target_user_ids=[officer_id],
        material_state={"ts": uuid.uuid4().hex},
    )
    notif2 = await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type="READ_TEST_2",
        severity=NotificationSeverity.HIGH,
        title="Read Incident Alert",
        message="Already acknowledged",
        target_user_ids=[officer_id],
        material_state={"ts": uuid.uuid4().hex},
    )

    # Mark notif2 as read
    await service.mark_as_read(user_id=officer_id, notification_id=notif2.notification_id)

    token = await get_token(client)
    res = await client.get(
        "/api/v1/notifications?unread_only=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    items = res.json()
    ids = [n["notification_id"] for n in items]
    assert notif1.notification_id in ids
    assert notif2.notification_id not in ids


# -------------------------------------------------------------
# 5. GET /api/v1/notifications/unread-count -> real count
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_get_unread_count_endpoint(client: AsyncClient):
    db = get_database()
    token = await get_token(client)
    officer = await db["users"].find_one({"phone": "9999999002"})
    officer_id = str(officer.get("user_id") or officer.get("_id") or officer.get("phone"))

    service = NotificationService()
    # Mark all read first to establish baseline
    await service.mark_all_as_read(user_id=officer_id)

    # Dispatch 2 new notifications
    await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type="COUNT_TEST_1",
        severity=NotificationSeverity.MEDIUM,
        title="Count Test 1",
        message="Msg 1",
        target_user_ids=[officer_id],
        material_state={"ts": uuid.uuid4().hex},
    )
    await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type="COUNT_TEST_2",
        severity=NotificationSeverity.MEDIUM,
        title="Count Test 2",
        message="Msg 2",
        target_user_ids=[officer_id],
        material_state={"ts": uuid.uuid4().hex},
    )

    res = await client.get("/api/v1/notifications/unread-count", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert "count" in data
    assert "unread_count" in data
    assert data["count"] == 2
    assert data["unread_count"] == 2


# -------------------------------------------------------------
# 6. Read notifications excluded from unread count
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_read_notifications_excluded_from_unread_count(client: AsyncClient):
    db = get_database()
    token = await get_token(client)
    officer = await db["users"].find_one({"phone": "9999999002"})
    officer_id = str(officer.get("user_id") or officer.get("_id") or officer.get("phone"))

    service = NotificationService()
    await service.mark_all_as_read(user_id=officer_id)

    notif = await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type="COUNT_EXCLUSION_TEST",
        severity=NotificationSeverity.HIGH,
        title="Exclusion Test",
        message="Msg",
        target_user_ids=[officer_id],
        material_state={"ts": uuid.uuid4().hex},
    )

    # Check unread count is 1
    res1 = await client.get("/api/v1/notifications/unread-count", headers={"Authorization": f"Bearer {token}"})
    assert res1.json()["count"] == 1

    # Mark as read
    await service.mark_as_read(user_id=officer_id, notification_id=notif.notification_id)

    # Check unread count is now 0
    res2 = await client.get("/api/v1/notifications/unread-count", headers={"Authorization": f"Bearer {token}"})
    assert res2.json()["count"] == 0


# -------------------------------------------------------------
# 7. Another user's notifications cannot be returned
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_user_notification_isolation(client: AsyncClient):
    db = get_database()
    admin = await db["users"].find_one({"phone": "9999999001"})
    admin_id = str(admin.get("user_id") or admin.get("_id") or admin.get("phone"))

    service = NotificationService()
    admin_notif = await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type="ADMIN_ISOLATION_TEST",
        severity=NotificationSeverity.HIGH,
        title="Admin Exclusive Secret",
        message="Sensitive admin details",
        target_user_ids=[admin_id],
        material_state={"ts": uuid.uuid4().hex},
    )

    officer_token = await get_token(client, phone="9999999002", password="OfficerPassword@2026")
    res = await client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {officer_token}"})
    assert res.status_code == 200
    officer_items = res.json()
    officer_ids = [n["notification_id"] for n in officer_items]
    assert admin_notif.notification_id not in officer_ids


# -------------------------------------------------------------
# 8. Unauthenticated request rejected (401)
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_unauthenticated_requests_rejected(client: AsyncClient):
    res1 = await client.get("/api/v1/notifications")
    assert res1.status_code == 401

    res2 = await client.get("/api/v1/notifications/unread-count")
    assert res2.status_code == 401

    res3 = await client.get("/api/v1/notifications/channels/status")
    assert res3.status_code == 401


# -------------------------------------------------------------
# 9. Invalid severity handled correctly (422)
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_invalid_severity_query_param(client: AsyncClient):
    token = await get_token(client)
    res = await client.get(
        "/api/v1/notifications?severity=INVALID_SEVERITY_XYZ",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


# -------------------------------------------------------------
# 10. Limit and Skip handling
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_limit_and_skip_pagination(client: AsyncClient):
    db = get_database()
    token = await get_token(client)
    officer = await db["users"].find_one({"phone": "9999999002"})
    officer_id = str(officer.get("user_id") or officer.get("_id") or officer.get("phone"))

    service = NotificationService()
    for i in range(5):
        await service.dispatch_event(
            category=NotificationCategory.SITUATION,
            event_type=f"PAGINATION_PAGE_TEST_{i}",
            severity=NotificationSeverity.LOW,
            title=f"Pagination Item {i}",
            message=f"Pagination body {i}",
            target_user_ids=[officer_id],
            material_state={"idx": i, "ts": uuid.uuid4().hex},
        )

    res = await client.get(
        "/api/v1/notifications?limit=2&skip=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2


# -------------------------------------------------------------
# 11. Channels/status remains 200
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_channels_status_200(client: AsyncClient):
    token = await get_token(client)
    res = await client.get("/api/v1/notifications/channels/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert "in_app" in data
    assert "whatsapp" in data
    assert "sms" in data
    assert data["in_app"]["status"] == "OPERATIONAL"
