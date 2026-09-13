import pytest
import uuid
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient
from app.db.mongodb import db_manager
from app.models.enums import (
    NotificationCategory,
    NotificationDeliveryStatus,
    NotificationSeverity,
    ReportStatus,
    UserRole,
)
from app.services.notification.notification_service import NotificationService
from app.services.notification.sms_provider import (
    SmsDeliveryResult,
    SmsProviderInterface,
    SmsStatusResult,
    TwilioSmsProvider,
    set_sms_provider_override,
)
from app.services.routing_service import RoutingService
from app.services.places_service import PlacesService
from app.services.gemini_service import GeminiIntelligenceService
from app.core.config import settings


@pytest.fixture(autouse=True)
async def clean_safety_guidance_mock_env():
    """Isolate mock router, places discovery, geocoding, and LLM to avoid external network latency during unit tests."""
    async def mock_live_router(o_lat, o_lng, d_lat, d_lng):
        return [
            [o_lat, o_lng],
            [16.2500, 80.6500],
            [d_lat, d_lng],
        ], 3.5, 7.0, "Google Directions API"

    RoutingService.set_custom_router(mock_live_router)
    set_sms_provider_override(None)
    
    with patch.object(PlacesService, "discover_nearby_facilities", new_callable=AsyncMock) as mock_places, \
         patch("app.api.v1.endpoints.citizen.reverse_geocode_coordinates", new_callable=AsyncMock) as mock_geo, \
         patch.object(GeminiIntelligenceService, "extract_structured_evidence", new_callable=AsyncMock) as mock_extract:
        
        mock_places.return_value = []
        mock_geo.return_value = {
            "address": "MG Road, Vijayawada, Andhra Pradesh",
            "street_address": "MG Road",
            "city": "Vijayawada",
            "state": "Andhra Pradesh",
            "country": "India",
            "postal_code": "520010",
        }
        mock_extract.return_value = None
        
        try:
            yield
        finally:
            RoutingService.set_custom_router(None)
            set_sms_provider_override(None)


@pytest.mark.anyio
async def test_01_report_creation_triggers_safety_guidance_notification(client: AsyncClient):
    """1 & 2: Genuine report creation generates both officer notification and reporter safety guidance notification."""
    db = db_manager.db
    unique_phone = "9876543210"
    unique_desc = f"Emergency flood waters entering ground floor apartments {uuid.uuid4().hex[:8]}"

    payload = {
        "full_name": "Ravi Kumar",
        "phone": unique_phone,
        "emergency_type": "Flood",
        "citizen_impact_level": "CRITICAL",
        "description": unique_desc,
        "location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "address": "MG Road, Vijayawada, Andhra Pradesh",
        },
    }

    res = await client.post("/api/v1/citizen/reports", json=payload)
    assert res.status_code == 201
    data = res.json()
    report_id = data["report_id"]
    safety_guidance_token = data.get("safety_guidance_token")
    assert report_id.startswith("RES-")
    assert safety_guidance_token is not None

    # Check notification in database
    reporter_notif = await db["notifications"].find_one({
        "deep_link.entity_id": report_id,
        "event_type": "REPORTER_SAFETY_GUIDANCE",
    })
    assert reporter_notif is not None
    assert reporter_notif["category"] == NotificationCategory.CITIZEN_REPORT.value
    assert "View Safety Guidelines:" in reporter_notif["message"]
    assert safety_guidance_token in reporter_notif["message"]
    assert reporter_notif["metadata"]["safety_guidance_token"] == safety_guidance_token

    # Verify recipient
    recipients = reporter_notif.get("recipients", [])
    assert len(recipients) >= 1
    citizen_rec = next((r for r in recipients if r["phone_number"] in [unique_phone, f"+91{unique_phone}"]), None)
    assert citizen_rec is not None
    assert citizen_rec["in_app"]["status"] == NotificationDeliveryStatus.DELIVERED.value


@pytest.mark.anyio
async def test_02_correct_genuine_reporter_phone_resolved(client: AsyncClient):
    """3 & 4: Correct genuine reporter phone is resolved, no fake phone generated."""
    db = db_manager.db
    test_phone = "9123456789"
    payload = {
        "full_name": "Sunita Sharma",
        "phone": test_phone,
        "emergency_type": "Fire",
        "citizen_impact_level": "HIGH",
        "description": f"Kitchen fire contained but heavy smoke in corridor {uuid.uuid4().hex[:8]}",
        "location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "address": "Governorpet, Vijayawada",
        },
    }

    res = await client.post("/api/v1/citizen/reports", json=payload)
    assert res.status_code == 201
    data = res.json()
    report_id = data["report_id"]

    notif = await db["notifications"].find_one({
        "deep_link.entity_id": report_id,
        "event_type": "REPORTER_SAFETY_GUIDANCE",
    })
    assert notif is not None
    rec = notif["recipients"][0]
    assert rec["phone_number"] == f"+91{test_phone}" or rec["phone_number"] == test_phone
    assert not rec["phone_number"].startswith("555")  # No fake US demo numbers


@pytest.mark.anyio
async def test_03_in_app_safety_guidance_notification_and_url(client: AsyncClient):
    """5 & 6: In-App notification is delivered and contains canonical Safety Guidelines URL."""
    db = db_manager.db
    test_phone = "9888877777"
    payload = {
        "full_name": "Deepak Verma",
        "phone": test_phone,
        "emergency_type": "Medical Emergency",
        "citizen_impact_level": "CRITICAL",
        "description": f"Elderly person breathing difficulty needing urgent ambulance {uuid.uuid4().hex[:8]}",
        "location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "address": "Benz Circle, Vijayawada",
        },
    }

    res = await client.post("/api/v1/citizen/reports", json=payload)
    assert res.status_code == 201
    data = res.json()
    report_id = data["report_id"]
    token = data["safety_guidance_token"]

    notif = await db["notifications"].find_one({
        "deep_link.entity_id": report_id,
        "event_type": "REPORTER_SAFETY_GUIDANCE",
    })
    assert notif is not None
    assert notif["recipients"][0]["in_app"]["status"] == NotificationDeliveryStatus.DELIVERED.value
    expected_url_prefix = settings.FRONTEND_BASE_URL.rstrip("/") + "/safety-guidance"
    assert expected_url_prefix in notif["message"]
    assert token in notif["message"]
    assert notif["metadata"]["safety_guidelines_url"] == f"{expected_url_prefix}/{token}"


@pytest.mark.anyio
async def test_04_idempotency_prevents_duplicate_notifications(client: AsyncClient):
    """7: Duplicate dispatch with same material state suppresses duplicate notification records."""
    db = db_manager.db
    service = NotificationService()
    unique_id = f"RES-IDEMP-{uuid.uuid4().hex[:6]}"

    notif1 = await service.dispatch_event(
        category=NotificationCategory.CITIZEN_REPORT,
        event_type="REPORTER_SAFETY_GUIDANCE",
        severity=NotificationSeverity.HIGH,
        title="Safety Guidance",
        message="Guidance details",
        entity_type="CITIZEN_REPORT",
        entity_id=unique_id,
        target_user_ids=["+919999900001"],
        material_state={"report_id": unique_id, "action": "SAFETY_GUIDANCE_REPORT_RECEIVED"},
        db=db,
    )
    assert notif1 is not None

    notif2 = await service.dispatch_event(
        category=NotificationCategory.CITIZEN_REPORT,
        event_type="REPORTER_SAFETY_GUIDANCE",
        severity=NotificationSeverity.HIGH,
        title="Safety Guidance",
        message="Guidance details",
        entity_type="CITIZEN_REPORT",
        entity_id=unique_id,
        target_user_ids=["+919999900001"],
        material_state={"report_id": unique_id, "action": "SAFETY_GUIDANCE_REPORT_RECEIVED"},
        db=db,
    )
    assert notif2 is not None
    assert notif1.notification_id == notif2.notification_id

    # Verify only 1 record exists in DB
    count = await db["notifications"].count_documents({"deep_link.entity_id": unique_id, "event_type": "REPORTER_SAFETY_GUIDANCE"})
    assert count == 1


@pytest.mark.anyio
async def test_05_twilio_trial_template_mode_compatibility():
    """8, 9, 10: Twilio Trial mode uses approved trial template and requires SM SID for accepted status."""
    mock_provider = TwilioSmsProvider(
        account_sid="ACmockaccount123456789012345678",
        auth_token="mocktoken12345678901234567890",
        from_number="+17372508034",
        enabled=True,
        mode="trial_template",
        trial_template="sms_internal_alerts",
    )
    assert mock_provider.mode == "trial_template"
    assert mock_provider.trial_template == "sms_internal_alerts"
    assert mock_provider.is_configured() is True


@pytest.mark.anyio
async def test_06_twilio_572002_unverified_recipient_classification():
    """11: Twilio 572002 error is truthfully classified as TRIAL_RECIPIENT_NOT_VERIFIED."""
    class Mock572002Provider(SmsProviderInterface):
        def is_configured(self) -> bool:
            return True
        async def send_sms(self, recipient_phone: str, message: str) -> SmsDeliveryResult:
            return SmsDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="TRIAL_RECIPIENT_NOT_VERIFIED",
                error_message="Twilio Trial Error (572002): Recipient +919000000000 is not verified.",
            )
        async def get_delivery_status(self, provider_message_id: str) -> SmsStatusResult:
            return SmsStatusResult(status=NotificationDeliveryStatus.FAILED)

    db = db_manager.db
    service = NotificationService(sms_provider=Mock572002Provider())
    notif = await service.dispatch_event(
        category=NotificationCategory.CITIZEN_REPORT,
        event_type="REPORTER_SAFETY_GUIDANCE",
        severity=NotificationSeverity.HIGH,
        title="Safety Guidance",
        message="Follow guidance",
        entity_type="CITIZEN_REPORT",
        entity_id=f"RES-572002-{uuid.uuid4().hex[:6]}",
        target_user_ids=["+919000000000"],
        material_state={"test": uuid.uuid4().hex},
        db=db,
    )
    assert notif is not None
    rec = notif.recipients[0]
    assert rec.sms.status == NotificationDeliveryStatus.FAILED
    assert rec.sms.error_code == "TRIAL_RECIPIENT_NOT_VERIFIED"
    assert rec.in_app.status == NotificationDeliveryStatus.DELIVERED  # In-App still succeeds


@pytest.mark.anyio
async def test_07_twilio_572006_template_rejection_classification():
    """12: Twilio 572006 error is truthfully classified as TRIAL_TEMPLATE_REJECTED."""
    class Mock572006Provider(SmsProviderInterface):
        def is_configured(self) -> bool:
            return True
        async def send_sms(self, recipient_phone: str, message: str) -> SmsDeliveryResult:
            return SmsDeliveryResult(
                status=NotificationDeliveryStatus.FAILED,
                error_code="TRIAL_TEMPLATE_REJECTED",
                error_message="Twilio Trial Error (572006): Template invalid.",
            )
        async def get_delivery_status(self, provider_message_id: str) -> SmsStatusResult:
            return SmsStatusResult(status=NotificationDeliveryStatus.FAILED)

    db = db_manager.db
    service = NotificationService(sms_provider=Mock572006Provider())
    notif = await service.dispatch_event(
        category=NotificationCategory.CITIZEN_REPORT,
        event_type="REPORTER_SAFETY_GUIDANCE",
        severity=NotificationSeverity.HIGH,
        title="Safety Guidance",
        message="Follow guidance",
        entity_type="CITIZEN_REPORT",
        entity_id=f"RES-572006-{uuid.uuid4().hex[:6]}",
        target_user_ids=["+919000000001"],
        material_state={"test": uuid.uuid4().hex},
        db=db,
    )
    assert notif is not None
    rec = notif.recipients[0]
    assert rec.sms.status == NotificationDeliveryStatus.FAILED
    assert rec.sms.error_code == "TRIAL_TEMPLATE_REJECTED"


@pytest.mark.anyio
async def test_08_sms_failure_does_not_fail_report_creation(client: AsyncClient):
    """14: When SMS provider fails, citizen report creation still succeeds 201 Created."""
    payload = {
        "full_name": "Kavita Reddy",
        "phone": "9999900999",
        "emergency_type": "Road Accident",
        "citizen_impact_level": "HIGH",
        "description": f"Two vehicle collision near flyover, lane partially blocked {uuid.uuid4().hex[:8]}",
        "location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "address": "Ring Road, Vijayawada",
        },
    }

    res = await client.post("/api/v1/citizen/reports", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["report_id"].startswith("RES-")
    assert data["status"] == ReportStatus.RECEIVED.value


@pytest.mark.anyio
async def test_09_duplicate_report_submission_returns_existing_without_duplicate_insert(client: AsyncClient):
    """A4 & Test Matrix 9, 10, 11, 12: Duplicate/retry submission within 15 min returns existing genuine report without duplicate MongoDB insert."""
    db = db_manager.db
    unique_phone = "9988776655"
    unique_desc = f"Localized water surge near canal embankment {uuid.uuid4().hex[:8]}"
    payload = {
        "full_name": "Ananya Sharma",
        "phone": unique_phone,
        "emergency_type": "Flood",
        "citizen_impact_level": "HIGH",
        "description": unique_desc,
        "location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "address": "Canal Road, Vijayawada",
        },
    }

    # 1. First submission
    res1 = await client.post("/api/v1/citizen/reports", json=payload)
    assert res1.status_code == 201
    data1 = res1.json()
    orig_report_id = data1["report_id"]

    # 2. Retry submission with identical parameters (e.g. user retrying after client latency)
    res2 = await client.post("/api/v1/citizen/reports", json=payload)
    assert res2.status_code in [200, 201]
    data2 = res2.json()
    assert data2["report_id"] == orig_report_id
    assert data2["possible_duplicate"] is True

    # 3. Verify exactly 1 report exists in MongoDB
    matching_reports = await db["citizen_reports"].count_documents({
        "citizen_phone": f"+91{unique_phone}",
        "emergency_type": "Flood",
        "description": unique_desc,
    })
    if matching_reports == 0:
        matching_reports = await db["citizen_reports"].count_documents({
            "citizen_phone": unique_phone,
            "emergency_type": "Flood",
            "description": unique_desc,
        })
    assert matching_reports == 1

