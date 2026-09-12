import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.db.mongodb import get_database
from app.models.enums import (
    NotificationCategory,
    NotificationDeliveryStatus,
    NotificationSeverity,
    UserRole,
)
from app.services.notification import (
    NotificationService,
    get_notification_service,
    set_whatsapp_provider_override,
)
from app.services.notification.whatsapp_provider import (
    MockableWhatsAppProvider,
    MetaCloudWhatsAppProvider,
)


@pytest.fixture(autouse=True)
def setup_test_provider():
    mock_provider = MockableWhatsAppProvider(configured=True, should_succeed=True)
    set_whatsapp_provider_override(mock_provider)
    yield mock_provider
    set_whatsapp_provider_override(None)


@pytest.mark.anyio
async def test_meta_webhook_verification_success(client: AsyncClient, monkeypatch):
    """A. Valid Meta verification: hub.mode=subscribe and valid token returns exact challenge with 200"""
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "test_meta_webhook_secret_2026")
    
    challenge_val = "1158201444_test_challenge_xyz"
    response = await client.get(
        "/api/v1/notifications/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test_meta_webhook_secret_2026",
            "hub.challenge": challenge_val,
        },
    )
    assert response.status_code == 200
    assert response.text == challenge_val


@pytest.mark.anyio
async def test_meta_webhook_verification_invalid_token(client: AsyncClient, monkeypatch):
    """B. Invalid verify token returns 403 Forbidden"""
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "real_configured_secret")
    
    response = await client.get(
        "/api/v1/notifications/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_attacker_token",
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 403
    assert "Verification failed" in response.text


@pytest.mark.anyio
async def test_meta_webhook_verification_invalid_mode(client: AsyncClient, monkeypatch):
    """C. Invalid verification mode (not 'subscribe') returns 403 Forbidden"""
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "real_configured_secret")
    
    response = await client.get(
        "/api/v1/notifications/whatsapp/webhook",
        params={
            "hub.mode": "unsubscribe",
            "hub.verify_token": "real_configured_secret",
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_meta_webhook_verification_unconfigured_token(client: AsyncClient, monkeypatch):
    """G. When WHATSAPP_VERIFY_TOKEN is unconfigured, verification returns 403 safely"""
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "")
    monkeypatch.setattr(settings, "WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
    
    response = await client.get(
        "/api/v1/notifications/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "any_token",
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_meta_webhook_verification_no_db_mutation(client: AsyncClient, monkeypatch):
    """I. Webhook verification GET causes no operational database mutations"""
    db = get_database()
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "verify_secret_123")
    
    count_before = await db.notifications.count_documents({})
    
    response = await client.get(
        "/api/v1/notifications/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify_secret_123",
            "hub.challenge": "challenge_abc",
        },
    )
    assert response.status_code == 200
    
    count_after = await db.notifications.count_documents({})
    assert count_before == count_after


@pytest.mark.anyio
async def test_meta_webhook_post_delivery_status_updates(client: AsyncClient):
    """D & E. Valid webhook POST updates delivery status and handles duplicate events idempotently"""
    db = get_database()
    service = NotificationService()

    # Create a test notification record with WhatsApp recipient and known provider_message_id
    notif = await service.dispatch_event(
        category=NotificationCategory.CITIZEN_REPORT,
        event_type="REPORT_DISPATCHED",
        severity=NotificationSeverity.HIGH,
        title="Emergency Dispatch: Unit 1",
        message="Responders dispatched to incident.",
        target_roles=[UserRole.EMERGENCY_OFFICER],
        material_state={"dispatch": "unit_1"},
    )
    assert notif is not None
    assert len(notif.recipients) > 0
    
    # Set a known provider_message_id
    test_msg_id = f"wamid.TEST_WEBHOOK_STATUS_{notif.notification_id}"
    await db.notifications.update_one(
        {"notification_id": notif.notification_id},
        {"$set": {"recipients.0.whatsapp.provider_message_id": test_msg_id}},
    )

    # 1. Post 'delivered' status update
    delivered_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "100000000000001",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "100000000000002",
                            },
                            "statuses": [
                                {
                                    "id": test_msg_id,
                                    "status": "delivered",
                                    "timestamp": "1710000000",
                                    "recipient_id": "9999999002",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    res = await client.post("/api/v1/notifications/whatsapp/webhook", json=delivered_payload)
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # Verify document in DB updated to DELIVERED
    doc_delivered = await db.notifications.find_one({"notification_id": notif.notification_id})
    assert doc_delivered["recipients"][0]["whatsapp"]["status"] == NotificationDeliveryStatus.DELIVERED.value
    assert doc_delivered["recipients"][0]["whatsapp"]["delivered_at"] is not None

    # 2. Duplicate 'delivered' webhook - idempotent execution
    res_dup = await client.post("/api/v1/notifications/whatsapp/webhook", json=delivered_payload)
    assert res_dup.status_code == 200
    assert res_dup.json()["status"] == "ok"

    # 3. Post 'read' status update
    read_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "100000000000001",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "100000000000002",
                            },
                            "statuses": [
                                {
                                    "id": test_msg_id,
                                    "status": "read",
                                    "timestamp": "1710000010",
                                    "recipient_id": "9999999002",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    res_read = await client.post("/api/v1/notifications/whatsapp/webhook", json=read_payload)
    assert res_read.status_code == 200

    doc_read = await db.notifications.find_one({"notification_id": notif.notification_id})
    assert doc_read["recipients"][0]["whatsapp"]["status"] == NotificationDeliveryStatus.READ.value
    assert doc_read["recipients"][0]["whatsapp"]["read_at"] is not None


@pytest.mark.anyio
async def test_meta_webhook_post_malformed_payload_safe_rejection(client: AsyncClient):
    """F. Malformed or non-JSON payloads are safely rejected/handled without crashing"""
    # Empty dict
    res1 = await client.post("/api/v1/notifications/whatsapp/webhook", json={})
    assert res1.status_code == 200
    assert res1.json()["details"]["status"] == "ignored"

    # Random non-WhatsApp JSON
    res2 = await client.post("/api/v1/notifications/whatsapp/webhook", json={"random": "data"})
    assert res2.status_code == 200
    assert res2.json()["details"]["status"] == "ignored"

    # Non-JSON content-type / string
    res3 = await client.post(
        "/api/v1/notifications/whatsapp/webhook",
        content="not-json-payload-data",
        headers={"Content-Type": "application/json"},
    )
    assert res3.status_code == 200
    assert res3.json()["status"] == "ignored"
    assert res3.json()["reason"] == "malformed_json"


@pytest.mark.anyio
async def test_meta_webhook_post_inbound_message_receipt(client: AsyncClient):
    """Webhook handles inbound message notifications safely without crashing"""
    inbound_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "100000000000001",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "100000000000002",
                            },
                            "messages": [
                                {
                                    "from": "919801338643",
                                    "id": "wamid.INBOUND_MSG_123",
                                    "timestamp": "1710000050",
                                    "text": {"body": "STATUS REPORT"},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    res = await client.post("/api/v1/notifications/whatsapp/webhook", json=inbound_payload)
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["details"]["messages_received"] == 1


@pytest.mark.anyio
async def test_channel_status_reports_truthful_state():
    """G & H. Channel status truthfully reports WhatsApp and In-App operational state"""
    # 1. With configured provider
    mock_p = MockableWhatsAppProvider(configured=True)
    svc = NotificationService(whatsapp_provider=mock_p)
    status_info = svc.get_channel_status()
    assert status_info["in_app"]["status"] == "OPERATIONAL"
    assert status_info["in_app"]["configured"] is True
    assert status_info["whatsapp"]["status"] == "OPERATIONAL"
    assert status_info["whatsapp"]["configured"] is True

    # 2. With unconfigured provider
    unconf_p = MockableWhatsAppProvider(configured=False)
    svc_unconf = NotificationService(whatsapp_provider=unconf_p)
    status_unconf = svc_unconf.get_channel_status()
    assert status_unconf["whatsapp"]["status"] == "NOT_CONFIGURED"
    assert status_unconf["whatsapp"]["configured"] is False
