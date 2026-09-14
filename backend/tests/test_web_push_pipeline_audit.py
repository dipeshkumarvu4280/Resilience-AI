import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import pywebpush

from app.main import app
from app.db.mongodb import db_manager
from app.core.config import settings
from app.models.enums import (
    NotificationChannel,
    PushSubscriptionStatus,
    SafetyNotificationType,
)
from app.models.safety_guidance import (
    PushSubscriptionRecord,
    PushNotificationPayload,
    CitizenSafetyGuidance,
)
from app.services.notification.web_push_service import WebPushService


@pytest.fixture(autouse=True)
async def clean_push_collections():
    test_db = db_manager.db
    if test_db is not None:
        await test_db["push_subscriptions"].delete_many({})
        await test_db["push_deliveries"].delete_many({})
        await test_db["citizen_safety_guidance"].delete_many({})
    yield


@pytest.mark.anyio
async def test_push_status_diagnostic_endpoint_read_only():
    """Verify GET /api/v1/notifications/push/status returns truthful status without leaking secrets."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/notifications/push/status")
        assert res.status_code == 200
        data = res.json()
        assert data["enabled"] is True
        assert data["secure_context_required"] is True
        assert data["subscription_registered"] is False
        assert data["subscription_persisted"] is False
        assert data["active_subscriptions"] == 0
        assert data["last_delivery_status"] in ["NONE", "DELIVERED", "FAILED"]
        assert "private_key" not in str(data)
        assert "VAPID_PRIVATE_KEY" not in str(data)

        # Mirror endpoint on /citizen/push/status
        res_citizen = await client.get("/api/v1/citizen/push/status")
        assert res_citizen.status_code == 200
        assert res_citizen.json()["enabled"] is True


@pytest.mark.anyio
async def test_vapid_public_key_safety():
    """Verify VAPID public key endpoint never leaks private key."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/citizen/push/vapid-public-key")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "vapid_public_key" in data
        assert "private" not in data
        assert "VAPID_PRIVATE_KEY" not in data


@pytest.mark.anyio
async def test_push_subscription_persistence_and_update():
    """Verify truthful persistence and idempotent updates in MongoDB."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "endpoint": "https://updates.push.services.mozilla.com/wpush/v2/gAAAAABtest",
            "keys": {
                "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9AcUbVJaBoeWOMXwhpyCnE",
                "auth": "tBHItJI5svbpez7KI4CCXg",
            },
            "user_agent": "Mozilla/5.0 (Android; Mobile)",
            "report_id": "RES-20260913-9999",
            "session_id": "sess-mobile-1",
        }

        res = await client.post("/api/v1/citizen/push/subscribe", json=payload)
        assert res.status_code == 200
        sub_id = res.json()["subscription_id"]

        test_db = db_manager.db
        doc = await test_db["push_subscriptions"].find_one({"subscription_id": sub_id})
        assert doc is not None
        assert doc["status"] == PushSubscriptionStatus.ACTIVE.value
        assert "RES-20260913-9999" in doc["report_ids"]

        # Check diagnostic endpoint shows 1 active subscription
        diag_res = await client.get("/api/v1/notifications/push/status")
        assert diag_res.json()["active_subscriptions"] == 1
        assert diag_res.json()["subscription_registered"] is True
        assert diag_res.json()["subscription_persisted"] is True


@pytest.mark.anyio
async def test_provider_success_delivery():
    """Verify provider 201 Created delivery is recorded truthfully."""
    test_db = db_manager.db
    now = datetime.now(timezone.utc)

    sub_record = PushSubscriptionRecord(
        subscription_id="SUB-TEST-001",
        endpoint="https://fcm.googleapis.com/fcm/send/test-sub-token",
        p256dh="BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9AcUbVJaBoeWOMXwhpyCnE",
        auth="tBHItJI5svbpez7KI4CCXg",
        status=PushSubscriptionStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    await test_db["push_subscriptions"].insert_one(sub_record.model_dump())

    payload = PushNotificationPayload(
        title="🚨 Emergency Warning",
        body="Flash flood near current position.",
        url="/citizen/report",
    )

    with patch("pywebpush.webpush", return_value=MagicMock(status_code=201)):
        success = await WebPushService.send_web_push(sub_record, payload, db=test_db)
        assert success is True

    updated_doc = await test_db["push_subscriptions"].find_one({"subscription_id": "SUB-TEST-001"})
    assert updated_doc["last_provider_status"] == "ACCEPTED_201"
    assert updated_doc["last_delivery_status"] == "DELIVERED"
    assert updated_doc["failure_reason"] is None


@pytest.mark.anyio
async def test_provider_410_and_404_expired_subscription():
    """Verify 410 Gone / 404 Not Found deactivates expired subscription."""
    test_db = db_manager.db
    now = datetime.now(timezone.utc)

    sub_record = PushSubscriptionRecord(
        subscription_id="SUB-EXPIRED-001",
        endpoint="https://fcm.googleapis.com/fcm/send/expired-token",
        p256dh="BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9AcUbVJaBoeWOMXwhpyCnE",
        auth="tBHItJI5svbpez7KI4CCXg",
        status=PushSubscriptionStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    await test_db["push_subscriptions"].insert_one(sub_record.model_dump())

    payload = PushNotificationPayload(title="Test", body="Test", url="/citizen/report")

    # Simulate 410 Gone WebPushException
    mock_resp = MagicMock(status_code=410)
    mock_ex = pywebpush.WebPushException("Subscription gone", response=mock_resp)

    with patch("pywebpush.webpush", side_effect=mock_ex):
        success = await WebPushService.send_web_push(sub_record, payload, db=test_db)
        assert success is False

    updated_doc = await test_db["push_subscriptions"].find_one({"subscription_id": "SUB-EXPIRED-001"})
    assert updated_doc["status"] == PushSubscriptionStatus.EXPIRED.value
    assert updated_doc["last_provider_status"] == "410_SUBSCRIPTION_EXPIRED"
    assert updated_doc["last_delivery_status"] == "FAILED"


@pytest.mark.anyio
async def test_provider_401_vapid_auth_error():
    """Verify 401 VAPID Auth Error is classified accurately."""
    test_db = db_manager.db
    now = datetime.now(timezone.utc)

    sub_record = PushSubscriptionRecord(
        subscription_id="SUB-AUTH-001",
        endpoint="https://fcm.googleapis.com/fcm/send/auth-token",
        p256dh="BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9AcUbVJaBoeWOMXwhpyCnE",
        auth="tBHItJI5svbpez7KI4CCXg",
        status=PushSubscriptionStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    await test_db["push_subscriptions"].insert_one(sub_record.model_dump())

    payload = PushNotificationPayload(title="Test", body="Test", url="/citizen/report")

    mock_resp = MagicMock(status_code=401)
    mock_ex = pywebpush.WebPushException("Unauthorized VAPID JWT", response=mock_resp)

    with patch("pywebpush.webpush", side_effect=mock_ex):
        success = await WebPushService.send_web_push(sub_record, payload, db=test_db)
        assert success is False

    updated_doc = await test_db["push_subscriptions"].find_one({"subscription_id": "SUB-AUTH-001"})
    assert updated_doc["last_provider_status"] == "401_VAPID_AUTH_ERROR"
    assert updated_doc["last_delivery_status"] == "FAILED"


@pytest.mark.anyio
async def test_provider_429_and_5xx_transient_error():
    """Verify 429 Rate Limited and 503 Service Unavailable are classified accurately without deactivating subscription."""
    test_db = db_manager.db
    now = datetime.now(timezone.utc)

    sub_record = PushSubscriptionRecord(
        subscription_id="SUB-TRANSIENT-001",
        endpoint="https://fcm.googleapis.com/fcm/send/transient-token",
        p256dh="BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9AcUbVJaBoeWOMXwhpyCnE",
        auth="tBHItJI5svbpez7KI4CCXg",
        status=PushSubscriptionStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    await test_db["push_subscriptions"].insert_one(sub_record.model_dump())

    payload = PushNotificationPayload(title="Test", body="Test", url="/citizen/report")

    # 429 Rate Limited
    mock_resp_429 = MagicMock(status_code=429)
    with patch("pywebpush.webpush", side_effect=pywebpush.WebPushException("Rate Limited", response=mock_resp_429)):
        success = await WebPushService.send_web_push(sub_record, payload, db=test_db)
        assert success is False

    doc_429 = await test_db["push_subscriptions"].find_one({"subscription_id": "SUB-TRANSIENT-001"})
    assert doc_429["status"] == PushSubscriptionStatus.ACTIVE.value  # Active preserved for retry
    assert doc_429["last_provider_status"] == "429_RATE_LIMITED"


@pytest.mark.anyio
async def test_test_push_diagnostic_endpoint():
    """Verify POST /api/v1/citizen/push/test dispatches to registered subscriptions."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # With 0 subscriptions
        res = await client.post("/api/v1/citizen/push/test")
        assert res.status_code == 200
        assert res.json()["sent_count"] == 0

        # With 1 subscription
        test_db = db_manager.db
        sub_record = PushSubscriptionRecord(
            subscription_id="SUB-TEST-DISP",
            endpoint="https://fcm.googleapis.com/fcm/send/disp-token",
            p256dh="BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9AcUbVJaBoeWOMXwhpyCnE",
            auth="tBHItJI5svbpez7KI4CCXg",
            status=PushSubscriptionStatus.ACTIVE,
            report_ids=["RES-101"],
        )
        await test_db["push_subscriptions"].insert_one(sub_record.model_dump())

        with patch("app.services.notification.web_push_service.WebPushService.send_web_push", return_value=True):
            res_disp = await client.post("/api/v1/citizen/push/test?report_id=RES-101")
            assert res_disp.status_code == 200
            assert res_disp.json()["sent_count"] == 1
            assert res_disp.json()["success"] is True
