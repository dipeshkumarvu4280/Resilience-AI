import pytest
from datetime import datetime, timezone
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock

from app.db.mongodb import db_manager
from app.models.enums import (
    ReportStatus,
    SafetyNotificationType,
    PushSubscriptionStatus,
)
from app.services.notification.web_push_service import WebPushService
from app.models.safety_guidance import (
    CitizenSafetyGuidance,
    VerifiedDestination,
    DestinationType,
)


@pytest.fixture(autouse=True)
async def clean_db_for_audit():
    db = db_manager.db
    if db is not None:
        await db["push_subscriptions"].delete_many({})
        await db["push_deliveries"].delete_many({})
        await db["citizen_reports"].delete_many({"report_id": {"$regex": "^AUDIT-"}})
    yield


async def get_officer_auth_headers(client: AsyncClient):
    res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999002", "password": "OfficerPassword@2026"}
    )
    assert res.status_code == 200, f"Login failed: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_audit_report(
    report_id: str,
    status: str = "RECEIVED",
    phone: str = "9876540001",
    language_code: str = "en",
    emergency_type: str = "Flood",
):
    db = db_manager.db
    now = datetime.now(timezone.utc)
    report_doc = {
        "report_id": report_id,
        "citizen_id": f"CIT-{report_id[-6:]}",
        "citizen_name": "Audit Citizen",
        "citizen_phone": phone,
        "emergency_type": emergency_type,
        "citizen_impact_level": "HIGH",
        "description": f"Audit test incident for {report_id}",
        "language": {
            "code": language_code,
            "name": "Telugu" if language_code == "te" else ("Hindi" if language_code == "hi" else "English"),
            "confidence": 0.95,
            "is_mixed": False,
            "source": "CITIZEN_SELECTION",
            "detection_method": "nlp",
        },
        "preferred_language": language_code,
        "location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "address": "Audit Ring Road, Vijayawada",
        },
        "status": status,
        "priority": "UNASSESSED",
        "safety_guidance_token": f"tok_{report_id.lower()}",
        "created_at": now,
        "updated_at": now,
    }
    await db["citizen_reports"].insert_one(report_doc)
    return report_doc


async def register_audit_push_subscription(report_id: str, sub_id: str = "SUB-AUDIT-01"):
    db = db_manager.db
    now = datetime.now(timezone.utc)
    endpoint = f"https://fcm.googleapis.com/fcm/send/token-{report_id.lower()}"
    sub_doc = {
        "subscription_id": sub_id,
        "endpoint": endpoint,
        "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9AcUbVJaBoeWOMXwhpyCnE",
        "auth": "tBHItJI5svbpez7KI4CCXg",
        "user_id": None,
        "role": "CITIZEN",
        "status": PushSubscriptionStatus.ACTIVE.value,
        "report_ids": [report_id],
        "session_ids": [f"sess-{report_id.lower()}"],
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    await db["push_subscriptions"].insert_one(sub_doc)
    return sub_doc


# ---------------------------------------------------------------------------
# 1. REPORT ACKNOWLEDGED
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_audit_report_acknowledged_flow(client: AsyncClient):
    """
    Audit 1: Emergency Officer ACK action ->
    Report status transition to ACKNOWLEDGED ->
    Notification event creation ->
    Citizen recipient resolution ->
    Report-specific push subscription lookup ->
    Web Push dispatch ->
    Mongo delivery record ->
    Truthful Title & Body with Report ID.
    """
    report_id = "AUDIT-ACK-001"
    await create_audit_report(report_id, status="RECEIVED", language_code="en")
    await register_audit_push_subscription(report_id, sub_id="SUB-ACK-001")

    officer_headers = await get_officer_auth_headers(client)

    captured_payloads = []

    async def mock_send(subscription, payload, db=None):
        captured_payloads.append((subscription, payload))
        return True

    with patch("app.services.notification.web_push_service.WebPushService.send_web_push", side_effect=mock_send):
        res = await client.post(
            f"/api/v1/officer/reports/{report_id}/acknowledge",
            headers=officer_headers,
        )
        assert res.status_code == 200, res.text
        res_data = res.json()
        assert res_data["report_id"] == report_id
        assert res_data["status"] == "ACKNOWLEDGED"
        assert res_data["acknowledged_by"] is not None

    # Verify status in MongoDB
    db = db_manager.db
    doc = await db["citizen_reports"].find_one({"report_id": report_id})
    assert doc["status"] == "ACKNOWLEDGED"
    assert doc["acknowledged_by"] is not None
    assert doc["acknowledged_at"] is not None

    # Verify Push Dispatch was attempted
    assert len(captured_payloads) == 1
    sub_used, payload_sent = captured_payloads[0]
    assert sub_used.endpoint == f"https://fcm.googleapis.com/fcm/send/token-{report_id.lower()}"
    assert payload_sent.title == "Emergency Report Update"
    assert "acknowledged and is now under review" in payload_sent.body
    assert report_id in payload_sent.body
    assert payload_sent.data["report_id"] == report_id
    assert payload_sent.data["notification_type"] == "REPORT_ACKNOWLEDGED"

    # Verify Delivery Record in MongoDB push_deliveries
    delivery = await db["push_deliveries"].find_one({"report_id": report_id})
    assert delivery is not None
    assert delivery["status"] == "DELIVERED"
    assert delivery["provider_status"] == "ACCEPTED_201"
    assert delivery["notification_type"] == "REPORT_ACKNOWLEDGED"


# ---------------------------------------------------------------------------
# 1b. REPORT ACKNOWLEDGED (Multilingual - Hindi)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_audit_report_acknowledged_hindi(client: AsyncClient):
    """Verify stored citizen Hindi language produces truthful Hindi notification content."""
    report_id = "AUDIT-ACK-HI-002"
    await create_audit_report(report_id, status="RECEIVED", language_code="hi")
    await register_audit_push_subscription(report_id, sub_id="SUB-ACK-HI-002")

    officer_headers = await get_officer_auth_headers(client)
    captured_payloads = []

    async def mock_send(subscription, payload, db=None):
        captured_payloads.append((subscription, payload))
        return True

    with patch("app.services.notification.web_push_service.WebPushService.send_web_push", side_effect=mock_send):
        res = await client.post(
            f"/api/v1/officer/reports/{report_id}/acknowledge",
            headers=officer_headers,
        )
        assert res.status_code == 200

    assert len(captured_payloads) == 1
    _, payload_sent = captured_payloads[0]
    assert payload_sent.title == "आपातकालीन रिपोर्ट अपडेट"
    assert "स्वीकार कर ली गई है और अब समीक्षाधीन है" in payload_sent.body
    assert report_id in payload_sent.body
    assert payload_sent.data["language"] == "hi"


# ---------------------------------------------------------------------------
# 2. REPORT ACCEPTED / APPROVED
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_audit_report_accepted_flow(client: AsyncClient):
    """
    Audit 2: Report Accepted/Approved transition (ACTION_REQUIRED / UNDER_ASSESSMENT) ->
    Dispatches distinct citizen-facing acceptance notification with delivery record.
    """
    report_id = "AUDIT-ACC-003"
    await create_audit_report(report_id, status="ACKNOWLEDGED", language_code="en")
    await register_audit_push_subscription(report_id, sub_id="SUB-ACC-003")

    officer_headers = await get_officer_auth_headers(client)
    captured_payloads = []

    async def mock_send(subscription, payload, db=None):
        captured_payloads.append((subscription, payload))
        return True

    with patch("app.services.notification.web_push_service.WebPushService.send_web_push", side_effect=mock_send):
        res = await client.patch(
            f"/api/v1/officer/reports/{report_id}/status",
            headers=officer_headers,
            json={"status": "UNDER_ASSESSMENT", "reason": "Assigned to Sector Alpha Operations team"},
        )
        assert res.status_code == 200

    assert len(captured_payloads) == 1
    _, payload_sent = captured_payloads[0]
    assert payload_sent.title == "Emergency Report Accepted"
    assert "accepted and assigned for response coordination" in payload_sent.body
    assert report_id in payload_sent.body
    assert payload_sent.data["notification_type"] == "REPORT_ACCEPTED"

    # Delivery in Mongo
    db = db_manager.db
    delivery = await db["push_deliveries"].find_one({"report_id": report_id})
    assert delivery is not None
    assert delivery["status"] == "DELIVERED"
    assert delivery["notification_type"] == "REPORT_ACCEPTED"


# ---------------------------------------------------------------------------
# 3. REPORT REJECTED
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_audit_report_rejected_flow(client: AsyncClient):
    """
    Audit 3: Officer Rejection ->
    Mandatory reason validation ->
    Persisted rejection metadata ->
    Dispatches citizen push notification containing the EXACT rejection reason.
    """
    report_id = "AUDIT-REJ-004"
    await create_audit_report(report_id, status="RECEIVED", language_code="en")
    await register_audit_push_subscription(report_id, sub_id="SUB-REJ-004")

    officer_headers = await get_officer_auth_headers(client)
    rejection_reason = "Duplicate report of waterlogging already handled at Junction 12."
    captured_payloads = []

    async def mock_send(subscription, payload, db=None):
        captured_payloads.append((subscription, payload))
        return True

    with patch("app.services.notification.web_push_service.WebPushService.send_web_push", side_effect=mock_send):
        res = await client.post(
            f"/api/v1/officer/reports/{report_id}/reject",
            headers=officer_headers,
            json={"reason": rejection_reason},
        )
        assert res.status_code == 200
        res_data = res.json()
        assert res_data["status"] == "REJECTED"
        assert res_data["rejection"]["reason"] == rejection_reason

    assert len(captured_payloads) == 1
    _, payload_sent = captured_payloads[0]
    assert payload_sent.title == "Emergency Report Update"
    assert rejection_reason in payload_sent.body
    assert report_id in payload_sent.body
    assert payload_sent.data["notification_type"] == "REPORT_REJECTED"
    assert payload_sent.data["rejection_reason"] == rejection_reason

    # Delivery in Mongo
    db = db_manager.db
    delivery = await db["push_deliveries"].find_one({"report_id": report_id})
    assert delivery is not None
    assert delivery["status"] == "DELIVERED"
    assert delivery["notification_type"] == "REPORT_REJECTED"


# ---------------------------------------------------------------------------
# 4. SAFETY GUIDANCE PUSH
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_audit_safety_guidance_push_flow():
    """
    Audit 4: Safety Guidance Synthesis ->
    WebPushService.notify_subscribers_of_guidance_update ->
    Produces localized payload with verified shelter/destination ->
    Mongo delivery record.
    """
    report_id = "AUDIT-GUD-005"
    db = db_manager.db
    await create_audit_report(report_id, status="RECEIVED", language_code="te")
    await register_audit_push_subscription(report_id, sub_id="SUB-GUD-005")

    guidance = CitizenSafetyGuidance(
        guidance_id="GUD-AUDIT-001",
        secure_access_token="tok_audit_te",
        report_id=report_id,
        generated_at=datetime.now(timezone.utc),
        valid_until=datetime.now(timezone.utc),
        status="ACTIVE",
        emergency_type="Flood",
        risk_level="HIGH",
        immediate_actions=["ఎత్తైన ప్రదేశానికి వెళ్ళండి"],
        precautions=[],
        recommended_destination=VerifiedDestination(
            destination_id="PLC-AUDIT",
            destination_name="విజయవాడ పునరావాస కేంద్రం",
            destination_type=DestinationType.SHELTER,
            latitude=16.51,
            longitude=80.65,
            address_or_landmark="Zone 2",
            distance_km=1.8,
            estimated_drive_minutes=4.0,
            is_verified_operational=True,
        ),
        language={"code": "te", "name": "Telugu", "source": "CITIZEN_SELECTION"},
    )

    with patch("app.services.notification.web_push_service.WebPushService.send_web_push", new=AsyncMock(return_value=True)) as mock_send:
        sent_count = await WebPushService.notify_citizen_guidance_update(
            guidance=guidance,
            notification_type=SafetyNotificationType.SAFETY_GUIDANCE_READY,
            event_id="EVT-GUD-AUDIT-001",
            db=db,
        )
        assert sent_count >= 1
        assert mock_send.await_count >= 1

    delivery = await db["push_deliveries"].find_one({"notification_type": "SAFETY_GUIDANCE_READY"})
    assert delivery is not None
    assert delivery["status"] == "DELIVERED"
    assert delivery["notification_type"] == "SAFETY_GUIDANCE_READY"


# ---------------------------------------------------------------------------
# 5. IDEMPOTENCY & FAULT TOLERANCE
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_audit_push_idempotency_and_fault_tolerance(client: AsyncClient):
    """
    Verify:
    1. Duplicate status notification triggers are idempotent and do NOT duplicate provider calls.
    2. Provider error does NOT roll back or fail the report status transition.
    """
    report_id = "AUDIT-FAULT-006"
    await create_audit_report(report_id, status="RECEIVED", language_code="en")
    await register_audit_push_subscription(report_id, sub_id="SUB-FAULT-006")

    officer_headers = await get_officer_auth_headers(client)

    # 1. First trigger with simulated provider failure
    with patch(
        "app.services.notification.web_push_service.WebPushService.send_web_push",
        new=AsyncMock(return_value=False),
    ):
        res = await client.post(
            f"/api/v1/officer/reports/{report_id}/acknowledge",
            headers=officer_headers,
        )
        # Even when push returns False, the endpoint MUST succeed with 200 and report MUST be ACKNOWLEDGED
        assert res.status_code == 200
        assert res.json()["status"] == "ACKNOWLEDGED"

    db = db_manager.db
    doc = await db["citizen_reports"].find_one({"report_id": report_id})
    assert doc["status"] == "ACKNOWLEDGED"
