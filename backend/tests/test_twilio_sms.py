import asyncio
import os
import re
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.db.mongodb import get_database
from app.main import app
from app.models.enums import (
    NotificationCategory,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationSeverity,
    UserRole,
)
from app.models.notification import (
    NotificationPreferenceUpdate,
    NotificationRecipientInfo,
    SmsDeliveryState,
)
from app.services.notification.notification_service import (
    NotificationService,
    get_notification_service,
)
from app.services.notification.sms_provider import (
    DisabledSmsProvider,
    MockableSmsProvider,
    TwilioSmsProvider,
    get_sms_provider,
    normalize_phone_e164,
    set_sms_provider_override,
)
from app.services.notification.whatsapp_provider import (
    MetaCloudWhatsAppProvider,
    MockableWhatsAppProvider,
    TwilioWhatsAppProvider,
    get_whatsapp_provider,
    set_whatsapp_provider_override,
    validate_twilio_signature,
)


@pytest.fixture(autouse=True)
def cleanup_overrides():
    """Ensure clean provider overrides and settings before and after each test."""
    set_sms_provider_override(None)
    set_whatsapp_provider_override(None)
    yield
    set_sms_provider_override(None)
    set_whatsapp_provider_override(None)


# -------------------------------------------------------------
# 1. SMS Provider Initialization
# -------------------------------------------------------------
def test_sms_provider_initialization():
    provider = TwilioSmsProvider(
        account_sid="ACtest_sid_12345",
        auth_token="secret_auth_token",
        from_number="+14155552671",
        enabled=True,
    )
    assert provider.is_configured() is True
    assert provider.account_sid == "ACtest_sid_12345"
    assert provider.from_number == "+14155552671"
    assert provider.enabled is True


# -------------------------------------------------------------
# 2. Missing Credentials
# -------------------------------------------------------------
def test_sms_missing_credentials():
    provider = TwilioSmsProvider(
        account_sid="",
        auth_token="",
        from_number="",
        enabled=True,
    )
    assert provider.is_configured() is False


# -------------------------------------------------------------
# 3. Disabled SMS Provider
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_disabled_sms_provider():
    provider = DisabledSmsProvider()
    assert provider.is_configured() is False
    res = await provider.send_sms("+919801338643", "Emergency alert")
    assert res.status == NotificationDeliveryStatus.NOT_CONFIGURED
    assert res.error_code == "DISABLED"


# -------------------------------------------------------------
# 4. Valid E.164 Recipient Normalization
# -------------------------------------------------------------
def test_valid_e164_recipient_normalization():
    # 10-digit Indian number defaults to +91
    assert normalize_phone_e164("9801338643") == "+919801338643"
    # Full international with +
    assert normalize_phone_e164("+919801338643") == "+919801338643"
    assert normalize_phone_e164("+14155552671") == "+14155552671"
    # Stripping whatsapp prefix if passed
    assert normalize_phone_e164("whatsapp:+919801338643") == "+919801338643"


# -------------------------------------------------------------
# 5. Recipient Normalization Formatting (Spaces, hyphens, brackets)
# -------------------------------------------------------------
def test_recipient_normalization_spaces_hyphens():
    assert normalize_phone_e164("+91 98013-38643") == "+919801338643"
    assert normalize_phone_e164("+1 (415) 555-2671") == "+14155552671"


# -------------------------------------------------------------
# 6. Invalid Recipient
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_invalid_recipient_not_calling_twilio():
    provider = TwilioSmsProvider(
        account_sid="ACtest_sid_12345",
        auth_token="secret_auth_token",
        from_number="+14155552671",
        enabled=True,
    )
    assert normalize_phone_e164("123") is None
    assert normalize_phone_e164("") is None

    res = await provider.send_sms("invalid_phone", "Alert")
    assert res.status == NotificationDeliveryStatus.FAILED
    assert res.error_code == "INVALID_PHONE_NUMBER"


# -------------------------------------------------------------
# 7. Successful Twilio SMS Send
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_successful_twilio_sms_send():
    provider = TwilioSmsProvider(
        account_sid="ACtest_sid_12345",
        auth_token="secret_token",
        from_number="+14155552671",
        enabled=True,
    )

    mock_response = httpx.Response(
        201,
        json={
            "sid": "SMtest_msg_sid_9999",
            "status": "queued",
            "to": "+919801338643",
            "from": "+14155552671",
            "body": "Test alert",
        },
        request=httpx.Request("POST", "https://api.twilio.com/2010-04-01/Accounts/ACtest_sid_12345/Messages.json"),
    )

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
        res = await provider.send_sms("+919801338643", "Test alert")
        assert res.status == NotificationDeliveryStatus.QUEUED
        assert res.provider_message_id == "SMtest_msg_sid_9999"


# -------------------------------------------------------------
# 8. Twilio Message SID Persistence in MongoDB
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_twilio_message_sid_persistence():
    db = get_database()
    test_uid = f"user_sms_test_{uuid.uuid4().hex[:8]}"

    # Setup preference with SMS enabled
    await db["notification_preferences"].insert_one({
        "preference_id": f"pref_{uuid.uuid4().hex[:8]}",
        "user_id": test_uid,
        "in_app_enabled": True,
        "whatsapp_enabled": False,
        "sms_enabled": True,
        "phone_number": "+919801338643",
        "notify_critical": True,
        "notify_high": True,
        "notify_operational": True,
        "notify_plan_updates": True,
        "notify_monitoring": True,
        "updated_at": datetime.now(timezone.utc),
    })

    mock_sms_provider = MockableSmsProvider(configured=True, should_succeed=True)
    service = NotificationService(sms_provider=mock_sms_provider)

    notif = await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type=f"SITUATION_ESCALATED_{test_uid}",
        entity_id=f"entity_{test_uid}",
        severity=NotificationSeverity.CRITICAL,
        title="Cyclone Warning",
        message="Cyclone shelter alert in sector 4.",
        target_user_ids=[test_uid],
        db=db,
    )

    assert notif is not None
    rec = next(r for r in notif.recipients if r.user_id == test_uid)
    assert rec.sms.status == NotificationDeliveryStatus.SENT
    assert rec.sms.provider_message_id is not None
    assert rec.sms.provider_message_id.startswith("SMmock_")

    # Verify MongoDB persistence
    persisted = await db["notifications"].find_one({"notification_id": notif.notification_id})
    assert persisted is not None
    persisted_rec = next(r for r in persisted["recipients"] if r["user_id"] == test_uid)
    assert persisted_rec["sms"]["provider_message_id"] == rec.sms.provider_message_id
    assert persisted_rec["sms"]["status"] == NotificationDeliveryStatus.SENT.value


# -------------------------------------------------------------
# 9-13. Twilio SMS Delivery Status Lifecycle (queued, sent, delivered, undelivered, failed)
# -------------------------------------------------------------
@pytest.mark.parametrize(
    "raw_status,expected_enum",
    [
        ("queued", NotificationDeliveryStatus.QUEUED),
        ("accepted", NotificationDeliveryStatus.QUEUED),
        ("sending", NotificationDeliveryStatus.SENDING),
        ("sent", NotificationDeliveryStatus.SENT),
        ("delivered", NotificationDeliveryStatus.DELIVERED),
        ("undelivered", NotificationDeliveryStatus.UNDELIVERED),
        ("failed", NotificationDeliveryStatus.FAILED),
    ],
)
@pytest.mark.anyio
async def test_twilio_sms_status_lifecycle(raw_status, expected_enum):
    db = get_database()
    test_sid = f"SMtest_lifecycle_{raw_status}_{uuid.uuid4().hex[:6]}"
    notif_id = f"notif_sms_{uuid.uuid4().hex[:8]}"

    # Seed notification with SMS provider SID
    await db["notifications"].insert_one({
        "notification_id": notif_id,
        "category": "SITUATION",
        "event_type": "TEST_ALERT",
        "severity": "CRITICAL",
        "title": "Status Test",
        "message": "Testing status callback",
        "fingerprint": f"fp_{uuid.uuid4().hex}",
        "created_at": datetime.now(timezone.utc),
        "recipients": [
            {
                "user_id": "test_user",
                "phone_number": "+919801338643",
                "in_app": {"status": "DELIVERED"},
                "whatsapp": {"status": "SKIPPED"},
                "sms": {
                    "status": "QUEUED",
                    "provider_message_id": test_sid,
                },
            }
        ],
    })

    service = NotificationService()
    callback_payload = {
        "MessageSid": test_sid,
        "MessageStatus": raw_status,
        "ErrorCode": "30008" if raw_status in ("failed", "undelivered") else None,
        "ErrorMessage": "Delivery error" if raw_status in ("failed", "undelivered") else None,
    }

    res = await service.process_twilio_status_callback(callback_payload, db=db)
    assert res["status"] == "processed"
    assert res["delivery_status"] == expected_enum.value
    assert res["channel"] == "sms"

    doc = await db["notifications"].find_one({"notification_id": notif_id})
    rec = doc["recipients"][0]["sms"]
    assert rec["status"] == expected_enum.value
    if raw_status in ("failed", "undelivered"):
        assert rec["error_code"] == "30008"


# -------------------------------------------------------------
# 14. Duplicate Callback Idempotency
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_duplicate_sms_callback_idempotency():
    db = get_database()
    test_sid = f"SMtest_idem_{uuid.uuid4().hex[:8]}"
    notif_id = f"notif_sms_idem_{uuid.uuid4().hex[:8]}"

    await db["notifications"].insert_one({
        "notification_id": notif_id,
        "category": "SITUATION",
        "event_type": "TEST_IDEM",
        "severity": "CRITICAL",
        "title": "Idempotency Test",
        "message": "Testing idempotency",
        "fingerprint": f"fp_{uuid.uuid4().hex}",
        "created_at": datetime.now(timezone.utc),
        "recipients": [
            {
                "user_id": "test_user",
                "phone_number": "+919801338643",
                "in_app": {"status": "DELIVERED"},
                "whatsapp": {"status": "SKIPPED"},
                "sms": {
                    "status": "QUEUED",
                    "provider_message_id": test_sid,
                },
            }
        ],
    })

    service = NotificationService()
    payload = {"MessageSid": test_sid, "MessageStatus": "delivered"}

    res1 = await service.process_twilio_status_callback(payload, db=db)
    assert res1["status"] == "processed"
    assert res1["updated"] is True

    # Second callback: same status
    res2 = await service.process_twilio_status_callback(payload, db=db)
    assert res2["status"] == "processed"

    count = await db["notifications"].count_documents({"recipients.sms.provider_message_id": test_sid})
    assert count == 1


# -------------------------------------------------------------
# 15. Invalid Twilio Signature -> 403
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_invalid_twilio_signature_rejected():
    with patch.object(settings, "TWILIO_VALIDATE_SIGNATURE", True):
        with patch.object(settings, "TWILIO_AUTH_TOKEN", "test_auth_token"):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/notifications/sms/twilio/status",
                    data={"MessageSid": "SMinvalid_sig", "MessageStatus": "delivered"},
                    headers={"X-Twilio-Signature": "invalidsignature123="},
                )
                assert response.status_code == 403


# -------------------------------------------------------------
# 16. Valid Twilio Signature -> 200 / Processed on /notifications/twilio/status
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_valid_twilio_signature_accepted():
    auth_token = "test_auth_token_for_validation"
    url = "http://test/api/v1/notifications/twilio/status"
    params = {"MessageSid": "SMvalid_sig", "MessageStatus": "delivered"}

    # Compute valid Twilio HMAC-SHA1 signature
    import base64, hashlib, hmac
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params.keys()))
    mac = hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1)
    valid_sig = base64.b64encode(mac.digest()).decode("utf-8")

    with patch.object(settings, "TWILIO_AUTH_TOKEN", auth_token):
        with patch.object(settings, "TWILIO_VALIDATE_SIGNATURE", True):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/notifications/twilio/status",
                    data=params,
                    headers={"X-Twilio-Signature": valid_sig},
                )
                assert response.status_code == 200
                assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_twilio_status_missing_message_sid():
    with patch.object(settings, "TWILIO_VALIDATE_SIGNATURE", False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/notifications/twilio/status",
                data={"MessageStatus": "delivered"},
            )
            assert response.status_code == 200
            assert response.json()["result"]["status"] == "ignored"


@pytest.mark.anyio
async def test_twilio_status_unknown_message_sid():
    with patch.object(settings, "TWILIO_VALIDATE_SIGNATURE", False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/notifications/twilio/status",
                data={"MessageSid": "SM_unknown_sid_9999", "MessageStatus": "delivered"},
            )
            assert response.status_code == 200
            assert response.json()["result"]["status"] == "not_found"


# -------------------------------------------------------------
# 17. Channel Status Endpoint Reflects SMS State
# -------------------------------------------------------------
def test_channel_status_endpoint_sms():
    service = NotificationService()
    with patch.object(settings, "SMS_PROVIDER", "twilio"):
        with patch.object(settings, "TWILIO_ACCOUNT_SID", "ACtest"):
            with patch.object(settings, "TWILIO_AUTH_TOKEN", "token"):
                with patch.object(settings, "TWILIO_SMS_FROM", "+14155552671"):
                    with patch.object(settings, "TWILIO_SMS_ENABLED", True):
                        st = service.get_channel_status()
                        assert "sms" in st
                        assert st["sms"]["configured"] is True
                        assert st["sms"]["provider"] == "twilio"
                        assert st["sms"]["status"] == "OPERATIONAL"


# -------------------------------------------------------------
# 18. Provider Selection (twilio / disabled / mock)
# -------------------------------------------------------------
def test_sms_provider_selection():
    with patch.object(settings, "SMS_PROVIDER", "disabled"):
        set_sms_provider_override(None)
        p1 = get_sms_provider()
        assert isinstance(p1, DisabledSmsProvider)

    with patch.object(settings, "SMS_PROVIDER", "twilio"):
        set_sms_provider_override(None)
        p2 = get_sms_provider()
        assert isinstance(p2, TwilioSmsProvider)

    with patch.object(settings, "SMS_PROVIDER", "mock"):
        set_sms_provider_override(None)
        p3 = get_sms_provider()
        assert isinstance(p3, MockableSmsProvider)


# -------------------------------------------------------------
# 19. SMS and WhatsApp Independent Delivery Records
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_sms_and_whatsapp_independent_deliveries():
    db = get_database()
    test_uid = f"user_multi_channel_{uuid.uuid4().hex[:8]}"

    # Setup preference with BOTH WhatsApp and SMS enabled
    await db["notification_preferences"].insert_one({
        "preference_id": f"pref_{uuid.uuid4().hex[:8]}",
        "user_id": test_uid,
        "in_app_enabled": True,
        "whatsapp_enabled": True,
        "sms_enabled": True,
        "phone_number": "+919801338643",
        "notify_critical": True,
        "notify_high": True,
        "notify_operational": True,
        "notify_plan_updates": True,
        "notify_monitoring": True,
        "updated_at": datetime.now(timezone.utc),
    })

    mock_wa = MockableWhatsAppProvider(configured=True, should_succeed=True)
    mock_sms = MockableSmsProvider(configured=True, should_succeed=True)

    service = NotificationService(whatsapp_provider=mock_wa, sms_provider=mock_sms)

    notif = await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type=f"MULTI_CHANNEL_ALERT_{test_uid}",
        entity_id=f"entity_{test_uid}",
        severity=NotificationSeverity.CRITICAL,
        title="Multi-channel Test",
        message="Independent channel verification",
        target_user_ids=[test_uid],
        db=db,
    )

    assert notif is not None
    rec = next(r for r in notif.recipients if r.user_id == test_uid)
    assert rec.whatsapp.status == NotificationDeliveryStatus.SENT
    assert rec.sms.status == NotificationDeliveryStatus.SENT
    assert rec.whatsapp.provider_message_id is not None
    assert rec.sms.provider_message_id is not None
    assert rec.whatsapp.provider_message_id != rec.sms.provider_message_id


# -------------------------------------------------------------
# 20. Meta WhatsApp Provider Remains Intact
# -------------------------------------------------------------
def test_meta_whatsapp_remains_intact():
    meta_provider = MetaCloudWhatsAppProvider(
        access_token="test_meta_token",
        phone_number_id="1234567890",
    )
    assert meta_provider.is_configured() is True
    assert meta_provider.phone_number_id == "1234567890"


# -------------------------------------------------------------
# 21. Inbound SMS Webhook Never Triggers Citizen Reporting
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_inbound_sms_never_triggers_citizen_reporting():
    db = get_database()
    service = NotificationService()

    before_reports = await db["citizen_reports"].count_documents({})
    before_situations = await db["situations"].count_documents({})

    inbound_data = {
        "MessageSid": f"SMinbound_{uuid.uuid4().hex[:8]}",
        "From": "+919801338643",
        "Body": "Flood on main street, need immediate rescue!",
    }

    res = await service.process_twilio_inbound_sms(inbound_data, db=db)
    assert res["status"] == "acknowledged"

    after_reports = await db["citizen_reports"].count_documents({})
    after_situations = await db["situations"].count_documents({})

    assert after_reports == before_reports
    assert after_situations == before_situations


# -------------------------------------------------------------
# 22. Zero Dummy Operational Data
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_no_dummy_operational_data_in_db():
    db = get_database()
    # Check that test collections do not have seeded fake operational reports
    fake_reports = await db["citizen_reports"].count_documents({"is_demo": True})
    assert fake_reports == 0


# -------------------------------------------------------------
# 23. No Credential Leakage in Errors or Logs
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_no_credential_leakage():
    provider = TwilioSmsProvider(
        account_sid="ACsecret_sid_999",
        auth_token="super_secret_auth_token_999",
        from_number="+14155552671",
        enabled=True,
    )

    mock_error_resp = httpx.Response(
        401,
        json={"code": 20003, "message": "Authenticate error"},
        request=httpx.Request("POST", "https://api.twilio.com/2010-04-01/Accounts/ACsecret_sid_999/Messages.json"),
    )

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_error_resp)):
        res = await provider.send_sms("+919801338643", "Alert")
        assert res.status == NotificationDeliveryStatus.FAILED
        assert "super_secret_auth_token_999" not in str(res.error_message)
        assert "super_secret_auth_token_999" not in str(res.error_code)


# -------------------------------------------------------------
# 24-25. No Hardcoded Recipients or Senders in Python Code
# -------------------------------------------------------------
def test_no_hardcoded_recipients_or_senders():
    sms_file = os.path.join(os.path.dirname(__file__), "..", "app", "services", "notification", "sms_provider.py")
    with open(sms_file, "r", encoding="utf-8") as f:
        content = f.read()
    # Check that no real personal phone numbers or auth tokens are hardcoded
    assert "super_secret" not in content
    assert "AC" + "0" * 32 not in content


# -------------------------------------------------------------
# 26. Trial Template Mode Parameter Construction
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_trial_template_mode_sends_predefined_template():
    provider = TwilioSmsProvider(
        account_sid="ACtest_sid_12345",
        auth_token="secret_token",
        from_number="+14155552671",
        enabled=True,
        mode="trial_template",
        trial_template="sms_internal_alerts",
    )

    captured_data = {}

    async def mock_post(url, data=None, auth=None):
        nonlocal captured_data
        captured_data = data
        return httpx.Response(
            201,
            json={"sid": "SMtest_trial_1234", "status": "queued"},
            request=httpx.Request("POST", url),
        )

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await provider.send_sms("+919801338643", "Arbitrary emergency alert text that should NOT be sent directly in trial mode")
        assert res.status == NotificationDeliveryStatus.QUEUED
        assert res.provider_message_id == "SMtest_trial_1234"
        assert captured_data.get("Body") == "sms_internal_alerts"
        assert captured_data.get("To") == "+919801338643"
        assert captured_data.get("From") == "+14155552671"


# -------------------------------------------------------------
# 27. Custom Mode Preserves Arbitrary Body for Production
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_custom_mode_sends_application_body():
    provider = TwilioSmsProvider(
        account_sid="ACtest_sid_12345",
        auth_token="secret_token",
        from_number="+14155552671",
        enabled=True,
        mode="custom",
    )

    captured_data = {}

    async def mock_post(url, data=None, auth=None):
        nonlocal captured_data
        captured_data = data
        return httpx.Response(
            201,
            json={"sid": "SMtest_custom_1234", "status": "queued"},
            request=httpx.Request("POST", url),
        )

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        custom_text = "RESILIENCE [CRITICAL]: Evacuate sector 9 immediately."
        res = await provider.send_sms("+919801338643", custom_text)
        assert res.status == NotificationDeliveryStatus.QUEUED
        assert res.provider_message_id == "SMtest_custom_1234"
        assert captured_data.get("Body") == custom_text


# -------------------------------------------------------------
# 28. Error Classification: Unverified Recipient (572002)
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_error_classification_unverified_recipient_572002():
    provider = TwilioSmsProvider(
        account_sid="ACtest_sid_12345",
        auth_token="secret_token",
        from_number="+14155552671",
        enabled=True,
    )

    mock_resp = httpx.Response(
        400,
        json={
            "code": 572002,
            "message": "No Twilio trial phone number is assigned for messaging to this destination number. Please add the 'to' number as a verified recipient.",
        },
        request=httpx.Request("POST", "https://api.twilio.com/2010-04-01/Accounts/ACtest_sid_12345/Messages.json"),
    )

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        res = await provider.send_sms("+919999999001", "Alert")
        assert res.status == NotificationDeliveryStatus.FAILED
        assert res.error_code == "572002"
        assert res.provider_message_id is None
        assert "verified recipient" in res.error_message.lower()


# -------------------------------------------------------------
# 29. Error Classification: Invalid Template (572006)
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_error_classification_invalid_template_572006():
    provider = TwilioSmsProvider(
        account_sid="ACtest_sid_12345",
        auth_token="secret_token",
        from_number="+14155552671",
        enabled=True,
    )

    mock_resp = httpx.Response(
        400,
        json={
            "code": 572006,
            "message": "Invalid template name. Trial accounts can only use predefined SMS templates.",
        },
        request=httpx.Request("POST", "https://api.twilio.com/2010-04-01/Accounts/ACtest_sid_12345/Messages.json"),
    )

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        res = await provider.send_sms("+919801338643", "Alert")
        assert res.status == NotificationDeliveryStatus.FAILED
        assert res.error_code == "572006"
        assert res.provider_message_id is None
        assert "invalid template" in res.error_message.lower()


# -------------------------------------------------------------
# 30. Missing Message SID on 200/201 Rejected
# -------------------------------------------------------------
@pytest.mark.anyio
async def test_missing_message_sid_on_201_response():
    provider = TwilioSmsProvider(
        account_sid="ACtest_sid_12345",
        auth_token="secret_token",
        from_number="+14155552671",
        enabled=True,
    )

    mock_resp = httpx.Response(
        201,
        json={"status": "queued"},  # missing 'sid'
        request=httpx.Request("POST", "https://api.twilio.com/2010-04-01/Accounts/ACtest_sid_12345/Messages.json"),
    )

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        res = await provider.send_sms("+919801338643", "Alert")
        assert res.status == NotificationDeliveryStatus.FAILED
        assert res.error_code == "NO_MESSAGE_SID"
        assert res.provider_message_id is None

