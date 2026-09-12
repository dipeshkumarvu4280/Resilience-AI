import base64
import hashlib
import hmac
import pytest
from httpx import AsyncClient, Response
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.db.mongodb import get_database
from app.models.enums import (
    NotificationCategory,
    NotificationDeliveryStatus,
    NotificationSeverity,
    UserRole,
)
from app.models.notification import (
    InAppDeliveryState,
    Notification,
    NotificationRecipientInfo,
    WhatsAppDeliveryState,
)
from app.services.notification import (
    NotificationService,
    get_notification_service,
    set_whatsapp_provider_override,
)
from app.services.notification.whatsapp_provider import (
    DisabledWhatsAppProvider,
    MetaCloudWhatsAppProvider,
    MockableWhatsAppProvider,
    TwilioWhatsAppProvider,
    get_whatsapp_provider,
    validate_twilio_signature,
)


def compute_twilio_signature(url: str, params: dict, auth_token: str) -> str:
    """Helper to compute valid X-Twilio-Signature for test fixtures."""
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params.keys()))
    mac = hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode("utf-8")


@pytest.fixture(autouse=True)
def cleanup_provider():
    set_whatsapp_provider_override(None)
    yield
    set_whatsapp_provider_override(None)


# -------------------------------------------------------------
# 1. Twilio Provider Initialization & Configuration
# -------------------------------------------------------------

def test_twilio_provider_initialization():
    """1. Test Twilio provider initializes with explicit or settings parameters."""
    provider = TwilioWhatsAppProvider(
        account_sid="AC_test_account_123",
        auth_token="auth_token_xyz_456",
        from_number="whatsapp:+14155238886",
        enabled=True,
        status_callback_url="https://resilience.test/api/v1/notifications/whatsapp/twilio/status",
    )
    assert provider.account_sid == "AC_test_account_123"
    assert provider.auth_token == "auth_token_xyz_456"
    assert provider.from_number == "whatsapp:+14155238886"
    assert provider.enabled is True
    assert provider.is_configured() is True


def test_twilio_provider_missing_credentials():
    """2. Twilio provider handles missing credentials safely without throwing."""
    provider = TwilioWhatsAppProvider(account_sid="", auth_token="", enabled=True)
    assert provider.is_configured() is False


def test_twilio_provider_disabled():
    """3. Twilio provider reports not configured if enabled is False."""
    provider = TwilioWhatsAppProvider(
        account_sid="AC_test_123",
        auth_token="auth_secret_456",
        enabled=False,
    )
    assert provider.is_configured() is False


# -------------------------------------------------------------
# 2. Recipient Normalization
# -------------------------------------------------------------

def test_recipient_normalization_valid():
    """4. Test valid recipient normalization to 'whatsapp:+<E.164>' format."""
    provider = TwilioWhatsAppProvider(account_sid="AC_123", auth_token="tok_123", enabled=True)
    
    # 10 digits Indian format default to +91
    assert provider.normalize_recipient("9801338643") == "whatsapp:+919801338643"
    # Full +91 with spaces or hyphens
    assert provider.normalize_recipient("+91 98013-38643") == "whatsapp:+919801338643"
    # Already whatsapp:+ formatted
    assert provider.normalize_recipient("whatsapp:+14155552671") == "whatsapp:+14155552671"
    # Standard international E.164
    assert provider.normalize_recipient("+14155552671") == "whatsapp:+14155552671"


def test_recipient_normalization_invalid():
    """5. Test invalid or short recipient numbers are rejected safely."""
    provider = TwilioWhatsAppProvider(account_sid="AC_123", auth_token="tok_123", enabled=True)
    assert provider.normalize_recipient("") is None
    assert provider.normalize_recipient("123") is None
    assert provider.normalize_recipient("abcd") is None


# -------------------------------------------------------------
# 3. Message Sending (REST boundary mocked)
# -------------------------------------------------------------

@pytest.mark.anyio
async def test_twilio_send_message_success():
    """6 & 7. Successful Twilio send returns Message SID and mapped status."""
    provider = TwilioWhatsAppProvider(
        account_sid="AC_mock_acc_123",
        auth_token="mock_token_456",
        from_number="whatsapp:+14155238886",
        enabled=True,
    )

    mock_twilio_response = {
        "sid": "SM_real_twilio_sid_998877",
        "status": "queued",
        "to": "whatsapp:+919801338643",
        "from": "whatsapp:+14155238886",
        "body": "🚨 Emergency alert",
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(
            status_code=201,
            json=mock_twilio_response,
            request=AsyncMock(),
        )

        res = await provider.send_message(
            recipient_phone="9801338643",
            message="🚨 *RESILIENCE AI ALERT [CRITICAL]*\nFlood evacuation update",
        )

        assert res.status == NotificationDeliveryStatus.QUEUED
        assert res.provider_message_id == "SM_real_twilio_sid_998877"
        assert res.error_code is None


@pytest.mark.anyio
async def test_twilio_send_message_error_handling():
    """Safe handling of Twilio 400 Sandbox errors (e.g., number not joined)."""
    provider = TwilioWhatsAppProvider(
        account_sid="AC_mock_acc_123",
        auth_token="mock_token_456",
        from_number="whatsapp:+14155238886",
        enabled=True,
    )

    mock_error_resp = {
        "code": 21608,
        "message": "The number is not a valid WhatsApp Sandbox participant.",
        "more_info": "https://www.twilio.com/docs/errors/21608",
        "status": 400,
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(
            status_code=400,
            json=mock_error_resp,
            request=AsyncMock(),
        )

        res = await provider.send_message(
            recipient_phone="9801338643",
            message="Emergency Alert",
        )

        assert res.status == NotificationDeliveryStatus.FAILED
        assert res.error_code == "21608"
        assert "Sandbox participant" in (res.error_message or "")


# -------------------------------------------------------------
# 4. Status Callback & Idempotent Persistence
# -------------------------------------------------------------

import uuid

@pytest.mark.anyio
@pytest.mark.parametrize(
    "twilio_status,expected_status",
    [
        ("queued", NotificationDeliveryStatus.QUEUED),
        ("sent", NotificationDeliveryStatus.SENT),
        ("delivered", NotificationDeliveryStatus.DELIVERED),
        ("read", NotificationDeliveryStatus.READ),
        ("failed", NotificationDeliveryStatus.FAILED),
        ("undelivered", NotificationDeliveryStatus.UNDELIVERED),
    ],
)
async def test_twilio_status_callback_lifecycle(db, twilio_status, expected_status):
    """8, 9, 10, 11, 12. Map queued, sent, delivered, read, failed to delivery status."""
    service = NotificationService()
    uid_suffix = uuid.uuid4().hex[:8]
    test_sid = f"SM_test_cycle_{twilio_status}_{uid_suffix}"

    # Seed notification with known provider_message_id
    notif = Notification(
        notification_id=f"notif_{twilio_status}_{uid_suffix}",
        category=NotificationCategory.SITUATION,
        event_type="test.twilio.lifecycle",
        severity=NotificationSeverity.CRITICAL,
        title="Test Alert",
        message="Emergency test alert message",
        fingerprint=f"fp_{twilio_status}_{test_sid}",
        recipients=[
            NotificationRecipientInfo(
                user_id="user_test_wa",
                role=UserRole.EMERGENCY_OFFICER,
                phone_number="+919801338643",
                in_app=InAppDeliveryState(status=NotificationDeliveryStatus.DELIVERED),
                whatsapp=WhatsAppDeliveryState(
                    status=NotificationDeliveryStatus.SENDING,
                    provider_message_id=test_sid,
                ),
            )
        ],
    )
    await db["notifications"].insert_one(notif.model_dump())

    form_data = {
        "MessageSid": test_sid,
        "MessageStatus": twilio_status,
        "ErrorCode": "30008" if twilio_status == "failed" else "",
        "ErrorMessage": "Delivery error" if twilio_status == "failed" else "",
    }

    result = await service.process_twilio_status_callback(form_data, db=db)
    assert result["status"] == "processed"
    assert result["delivery_status"] == expected_status.value
    assert result["updated"] is True

    # Verify MongoDB record updated
    doc = await db["notifications"].find_one({"notification_id": notif.notification_id})
    rec_wa = doc["recipients"][0]["whatsapp"]
    assert rec_wa["status"] == expected_status.value


@pytest.mark.anyio
async def test_duplicate_callback_idempotency(db):
    """13. Repeated callbacks must not duplicate records or cause invalid state."""
    service = NotificationService()
    uid_suffix = uuid.uuid4().hex[:8]
    test_sid = f"SM_idempotency_test_sid_{uid_suffix}"

    notif = Notification(
        notification_id=f"notif_idempotency_{uid_suffix}",
        category=NotificationCategory.SITUATION,
        event_type="test.twilio.idempotency",
        severity=NotificationSeverity.CRITICAL,
        title="Test Alert",
        message="Emergency test alert message",
        fingerprint=f"fp_idempotency_{uid_suffix}",
        recipients=[
            NotificationRecipientInfo(
                user_id="user_test_wa_idem",
                phone_number="+919801338643",
                in_app=InAppDeliveryState(status=NotificationDeliveryStatus.DELIVERED),
                whatsapp=WhatsAppDeliveryState(
                    status=NotificationDeliveryStatus.SENT,
                    provider_message_id=test_sid,
                ),
            )
        ],
    )
    await db["notifications"].insert_one(notif.model_dump())

    form_data = {
        "MessageSid": test_sid,
        "MessageStatus": "delivered",
    }

    # First callback
    res1 = await service.process_twilio_status_callback(form_data, db=db)
    assert res1["status"] == "processed"

    # Second identical callback
    res2 = await service.process_twilio_status_callback(form_data, db=db)
    assert res2["status"] == "processed"

    # Verify total documents remains 1
    total_docs = await db["notifications"].count_documents({"notification_id": "notif_idempotency_123"})
    assert total_docs == 1


# -------------------------------------------------------------
# 5. Webhook Signature Validation
# -------------------------------------------------------------

def test_twilio_signature_validation():
    """14 & 15. Test valid and invalid X-Twilio-Signature verification."""
    auth_token = "secret_twilio_auth_token_2026"
    url = "https://resilience.test/api/v1/notifications/whatsapp/twilio/status"
    params = {"MessageSid": "SM123", "MessageStatus": "delivered", "To": "whatsapp:+919801338643"}

    # Compute valid signature
    valid_sig = compute_twilio_signature(url, params, auth_token)

    # Validate signature matches
    assert validate_twilio_signature(url, params, valid_sig, auth_token) is True

    # Validate modified param fails
    params_tampered = dict(params, MessageStatus="failed")
    assert validate_twilio_signature(url, params_tampered, valid_sig, auth_token) is False

    # Validate incorrect auth token fails
    assert validate_twilio_signature(url, params, valid_sig, "wrong_token") is False

    # Validate empty signature fails
    assert validate_twilio_signature(url, params, "", auth_token) is False


@pytest.mark.anyio
async def test_twilio_status_endpoint_signature_enforcement(client: AsyncClient, monkeypatch):
    """Endpoints enforce signature validation when enabled."""
    auth_token = "test_auth_token_for_endpoint"
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", auth_token)
    monkeypatch.setattr(settings, "TWILIO_VALIDATE_SIGNATURE", True)

    payload = {"MessageSid": "SM_test_sig_123", "MessageStatus": "sent"}

    # 1. Missing header -> 403
    resp_no_header = await client.post(
        "/api/v1/notifications/whatsapp/twilio/status",
        data=payload,
    )
    assert resp_no_header.status_code == 403

    # 2. Invalid header -> 403
    resp_bad_header = await client.post(
        "/api/v1/notifications/whatsapp/twilio/status",
        data=payload,
        headers={"X-Twilio-Signature": "invalid_base64_sig=="},
    )
    assert resp_bad_header.status_code == 403

    # 3. Valid header -> 200
    test_url = "http://test/api/v1/notifications/whatsapp/twilio/status"
    valid_sig = compute_twilio_signature(test_url, payload, auth_token)

    resp_valid = await client.post(
        "/api/v1/notifications/whatsapp/twilio/status",
        data=payload,
        headers={"X-Twilio-Signature": valid_sig},
    )
    assert resp_valid.status_code == 200


# -------------------------------------------------------------
# 6. Channel Status Endpoint & Provider Selection
# -------------------------------------------------------------

def test_channel_status_twilio(monkeypatch):
    """16. Test channel status endpoint reflects Twilio provider accurately."""
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "twilio")
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "auth_test")
    monkeypatch.setattr(settings, "TWILIO_WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    provider = TwilioWhatsAppProvider()
    service = NotificationService(whatsapp_provider=provider)
    status = service.get_channel_status()

    assert status["in_app"]["status"] == "OPERATIONAL"
    assert status["whatsapp"]["provider"] == "twilio"
    assert status["whatsapp"]["configured"] is True
    assert status["whatsapp"]["status"] == "OPERATIONAL"
    assert status["whatsapp"]["from_number"] == "whatsapp:+14155238886"


def test_provider_selection_meta_remains_intact(monkeypatch):
    """17 & 18. Meta Cloud API provider remains intact and selectable."""
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "meta")
    monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "meta_token_123")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "phone_id_456")

    provider = get_whatsapp_provider()
    # If WHATSAPP_PROVIDER=meta, factory selects MetaCloudWhatsAppProvider
    assert isinstance(provider, MetaCloudWhatsAppProvider) or isinstance(get_whatsapp_provider(), MetaCloudWhatsAppProvider)


def test_disabled_provider_selection(monkeypatch):
    """Disabled provider truthfully returns NOT_CONFIGURED."""
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "disabled")
    set_whatsapp_provider_override(None)
    provider = get_whatsapp_provider()
    assert isinstance(provider, DisabledWhatsAppProvider)
    assert provider.is_configured() is False


# -------------------------------------------------------------
# 7. Safety & Inbound Integrity
# -------------------------------------------------------------

@pytest.mark.anyio
async def test_inbound_whatsapp_never_triggers_citizen_reporting(client: AsyncClient, monkeypatch, db):
    """19, 20. Inbound WhatsApp messages NEVER trigger citizen emergency reports."""
    monkeypatch.setattr(settings, "TWILIO_VALIDATE_SIGNATURE", False)

    initial_reports_count = await db["citizen_reports"].count_documents({})

    form_data = {
        "MessageSid": "SM_inbound_msg_001",
        "From": "whatsapp:+919801338643",
        "Body": "HELP! Fire on 4th cross road!",
    }

    response = await client.post(
        "/api/v1/notifications/whatsapp/twilio/inbound",
        data=form_data,
    )
    assert response.status_code == 200
    assert "Response" in response.text

    # Verify no citizen report was created
    final_reports_count = await db["citizen_reports"].count_documents({})
    assert final_reports_count == initial_reports_count
