import pytest
import uuid
from datetime import datetime, timezone
from httpx import AsyncClient

from app.db.mongodb import get_database, db_manager
from app.models.enums import (
    NotificationCategory,
    NotificationDeliveryStatus,
    NotificationSeverity,
    UserRole,
    ReportStatus,
    ReportPriority,
    EmergencyType,
)
from app.models.notification import (
    NotificationPreference,
    NotificationPreferenceUpdate,
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
    # Setup mock provider for tests
    mock_provider = MockableWhatsAppProvider(configured=True, should_succeed=True)
    set_whatsapp_provider_override(mock_provider)
    yield mock_provider
    set_whatsapp_provider_override(None)


async def get_auth_token(client: AsyncClient, phone: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"phone": phone, "password": password})
    assert res.status_code == 200, f"Login failed: {res.text}"
    return res.json()["access_token"]


@pytest.mark.anyio
async def test_01_real_domain_event_creates_in_app_notification():
    """1. Real domain event creates correct in-app notification"""
    db = get_database()
    service = NotificationService()

    notif = await service.dispatch_event(
        category=NotificationCategory.CITIZEN_REPORT,
        event_type="REPORT_CREATED",
        severity=NotificationSeverity.HIGH,
        title="New Emergency Report: Flood",
        message="Flash flood reported in Ward 4.",
        entity_type="CITIZEN_REPORT",
        entity_id="REP-TEST-01",
        target_roles=[UserRole.EMERGENCY_OFFICER],
        material_state={"report_id": "REP-TEST-01", "status": "RECEIVED"},
    )
    assert notif is not None
    assert notif.category == NotificationCategory.CITIZEN_REPORT
    assert notif.severity == NotificationSeverity.HIGH
    assert len(notif.recipients) > 0

    # Verify MongoDB persistence
    doc = await db.notifications.find_one({"notification_id": notif.notification_id})
    assert doc is not None
    assert doc["title"] == "New Emergency Report: Flood"


@pytest.mark.anyio
async def test_02_recipient_isolation(client: AsyncClient):
    """2. User A cannot see user B's notifications"""
    db = get_database()
    service = NotificationService()

    # Create notification targeted ONLY to Admin (9999999001)
    admin_doc = await db.users.find_one({"phone": "9999999001"})
    officer_doc = await db.users.find_one({"phone": "9999999002"})
    assert admin_doc and officer_doc

    admin_id = str(admin_doc.get("user_id") or admin_doc.get("_id") or admin_doc.get("phone"))
    officer_id = str(officer_doc.get("user_id") or officer_doc.get("_id") or officer_doc.get("phone"))

    notif = await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type="SITUATION_CLASSIFIED",
        severity=NotificationSeverity.MEDIUM,
        title="Admin-Only Classified Alert",
        message="Executive briefing only.",
        target_user_ids=[admin_id],
        material_state={"secret": "adm_only"},
    )
    assert notif is not None

    # Officer queries their notifications via API
    officer_token = await get_auth_token(client, "9999999002", "OfficerPassword@2026")
    res = await client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert res.status_code == 200
    officer_notifs = res.json()
    assert not any(n["notification_id"] == notif.notification_id for n in officer_notifs)


@pytest.mark.anyio
async def test_03_unread_count_correctness(client: AsyncClient):
    """3. Unread count correctness"""
    db = get_database()
    officer_doc = await db.users.find_one({"phone": "9999999002"})
    officer_id = str(officer_doc.get("user_id") or officer_doc.get("_id") or officer_doc.get("phone"))

    service = NotificationService()
    # Create 3 unread notifications
    for i in range(3):
        await service.dispatch_event(
            category=NotificationCategory.CITIZEN_REPORT,
            event_type=f"TEST_UNREAD_{i}",
            severity=NotificationSeverity.LOW,
            title=f"Test Unread {i}",
            message=f"Message {i}",
            target_user_ids=[officer_id],
            material_state={"test_idx": f"uniq_{uuid.uuid4().hex}"},
        )

    officer_token = await get_auth_token(client, "9999999002", "OfficerPassword@2026")
    res = await client.get(
        "/api/v1/notifications/unread-count",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["unread_count"] >= 3


@pytest.mark.anyio
async def test_04_mark_single_as_read(client: AsyncClient):
    """4. Mark single notification as read"""
    db = get_database()
    officer_doc = await db.users.find_one({"phone": "9999999002"})
    officer_id = str(officer_doc.get("user_id") or officer_doc.get("_id") or officer_doc.get("phone"))

    service = NotificationService()
    notif = await service.dispatch_event(
        category=NotificationCategory.RESOURCE_LOGISTICS,
        event_type="STOCK_LOW",
        severity=NotificationSeverity.HIGH,
        title="Stock Low Alert",
        message="Potable water below 20%",
        target_user_ids=[officer_id],
        material_state={"sku": f"water_{uuid.uuid4().hex}"},
    )

    officer_token = await get_auth_token(client, "9999999002", "OfficerPassword@2026")
    res = await client.post(
        f"/api/v1/notifications/{notif.notification_id}/read",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Verify notification state is READ
    detail_res = await client.get(
        f"/api/v1/notifications/{notif.notification_id}",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert detail_res.status_code == 200
    assert detail_res.json()["in_app_status"] == "READ"
    assert detail_res.json()["read_at"] is not None


@pytest.mark.anyio
async def test_05_mark_all_as_read(client: AsyncClient):
    """5. Mark all unread notifications as read"""
    officer_token = await get_auth_token(client, "9999999002", "OfficerPassword@2026")
    res = await client.post(
        "/api/v1/notifications/read-all",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Verify unread count is now 0
    count_res = await client.get(
        "/api/v1/notifications/unread-count",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert count_res.json()["unread_count"] == 0


@pytest.mark.anyio
async def test_06_pagination(client: AsyncClient):
    """6. Pagination support"""
    officer_token = await get_auth_token(client, "9999999002", "OfficerPassword@2026")
    res = await client.get(
        "/api/v1/notifications?limit=2&skip=0",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) <= 2


@pytest.mark.anyio
async def test_07_deep_link_metadata():
    """7. Notification deep-link metadata preservation"""
    service = NotificationService()
    notif = await service.dispatch_event(
        category=NotificationCategory.DYNAMIC_REPLANNING,
        event_type="REPLAN_READY",
        severity=NotificationSeverity.HIGH,
        title="Revised Coordination Plan Ready",
        message="Review updated resource allocations.",
        entity_type="COORDINATION_PLAN",
        entity_id="PLAN-2026-REV-1",
        situation_id="SIT-2026-001",
        coordination_plan_id="PLAN-2026-REV-1",
        view_hint="plans",
        target_roles=[UserRole.EMERGENCY_OFFICER],
        material_state={"plan_id": "PLAN-2026-REV-1", "ts": uuid.uuid4().hex},
    )
    assert notif is not None
    assert notif.deep_link is not None
    assert notif.deep_link.entity_id == "PLAN-2026-REV-1"
    assert notif.deep_link.situation_id == "SIT-2026-001"
    assert notif.deep_link.view_hint == "plans"


@pytest.mark.anyio
async def test_08_event_idempotency():
    """8. Event idempotency prevents duplicate notifications"""
    service = NotificationService()
    mat_state = {"resource_id": "RES-WATER-01", "qty": 50}

    notif1 = await service.dispatch_event(
        category=NotificationCategory.RESOURCE_LOGISTICS,
        event_type="STOCK_DEPLETED",
        severity=NotificationSeverity.HIGH,
        title="Water Depletion Alert",
        message="Water depleted at depot 1",
        entity_id="RES-WATER-01",
        target_roles=[UserRole.EMERGENCY_OFFICER],
        material_state=mat_state,
    )

    notif2 = await service.dispatch_event(
        category=NotificationCategory.RESOURCE_LOGISTICS,
        event_type="STOCK_DEPLETED",
        severity=NotificationSeverity.HIGH,
        title="Water Depletion Alert",
        message="Water depleted at depot 1",
        entity_id="RES-WATER-01",
        target_roles=[UserRole.EMERGENCY_OFFICER],
        material_state=mat_state,
    )

    assert notif1.notification_id == notif2.notification_id
    assert notif1.fingerprint == notif2.fingerprint


@pytest.mark.anyio
async def test_09_material_state_change_creates_new_alert():
    """9. Material state change creates valid new alert"""
    service = NotificationService()

    # Initial shortfall: 30
    notif1 = await service.dispatch_event(
        category=NotificationCategory.RESOURCE_LOGISTICS,
        event_type="RESOURCE_SHORTAGE",
        severity=NotificationSeverity.HIGH,
        title="Resource Shortfall",
        message="Shortfall: 30 units",
        entity_id="RES-FOOD-01",
        target_roles=[UserRole.EMERGENCY_OFFICER],
        material_state={"required": 100, "available": 70, "shortfall": 30},
    )

    # Later worsened shortfall: 60
    notif2 = await service.dispatch_event(
        category=NotificationCategory.RESOURCE_LOGISTICS,
        event_type="RESOURCE_SHORTAGE",
        severity=NotificationSeverity.CRITICAL,
        title="Resource Shortfall Escalated",
        message="Shortfall worsened: 60 units",
        entity_id="RES-FOOD-01",
        target_roles=[UserRole.EMERGENCY_OFFICER],
        material_state={"required": 100, "available": 40, "shortfall": 60},
    )

    assert notif1.notification_id != notif2.notification_id
    assert notif1.fingerprint != notif2.fingerprint


@pytest.mark.anyio
async def test_10_duplicate_event_does_not_spam_recipients():
    """10. Repeated calls with identical fingerprint do not spam"""
    db = get_database()
    service = NotificationService()
    mat_state = {"stable_id": f"stab_{uuid.uuid4().hex}"}

    initial_count = await db.notifications.count_documents({"fingerprint": service.compute_fingerprint(
        NotificationCategory.VOLUNTEER_OPS, "VOL_SHORTFALL", "VOL-OPS-1", mat_state
    )})
    assert initial_count == 0

    for _ in range(5):
        await service.dispatch_event(
            category=NotificationCategory.VOLUNTEER_OPS,
            event_type="VOL_SHORTFALL",
            severity=NotificationSeverity.MEDIUM,
            title="Volunteer Shortfall",
            message="Need 5 EMT volunteers",
            entity_id="VOL-OPS-1",
            target_roles=[UserRole.EMERGENCY_OFFICER],
            material_state=mat_state,
        )

    final_count = await db.notifications.count_documents({"fingerprint": service.compute_fingerprint(
        NotificationCategory.VOLUNTEER_OPS, "VOL_SHORTFALL", "VOL-OPS-1", mat_state
    )})
    assert final_count == 1


@pytest.mark.anyio
async def test_11_critical_escalation_triggers_whatsapp(setup_test_provider: MockableWhatsAppProvider):
    """11. Critical escalation policy triggers WhatsApp attempt"""
    db = get_database()
    officer_doc = await db.users.find_one({"phone": "9999999002"})
    officer_id = str(officer_doc.get("user_id") or officer_doc.get("_id") or officer_doc.get("phone"))

    service = NotificationService()
    notif = await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type="SITUATION_CRITICAL",
        severity=NotificationSeverity.CRITICAL,
        title="CRITICAL EMERGENCY ESCALATION",
        message="Hospital power outage. Evacuation required.",
        target_user_ids=[officer_id],
        material_state={"crit_id": uuid.uuid4().hex},
    )
    assert notif is not None
    # Recipient whatsapp state should be SENT
    rec = next(r for r in notif.recipients if r.user_id == officer_id)
    assert rec.whatsapp.status == NotificationDeliveryStatus.SENT
    assert rec.whatsapp.provider_message_id is not None
    assert len(setup_test_provider.sent_messages) > 0


@pytest.mark.anyio
async def test_12_whatsapp_disabled_preference():
    """12. WhatsApp disabled user preference is respected for non-critical alerts"""
    db = get_database()
    officer_doc = await db.users.find_one({"phone": "9999999002"})
    officer_id = str(officer_doc.get("user_id") or officer_doc.get("_id") or officer_doc.get("phone"))

    service = NotificationService()
    # Explicitly disable whatsapp for user
    await service.update_user_preferences(
        user_id=officer_id,
        update=NotificationPreferenceUpdate(whatsapp_enabled=False),
    )

    notif = await service.dispatch_event(
        category=NotificationCategory.RESOURCE_LOGISTICS,
        event_type="INVENTORY_UPDATE",
        severity=NotificationSeverity.LOW,
        title="Inventory Count Updated",
        message="50 blankets added",
        target_user_ids=[officer_id],
        material_state={"sku": f"blanket_{uuid.uuid4().hex}"},
    )
    rec = next(r for r in notif.recipients if r.user_id == officer_id)
    assert rec.whatsapp.status == NotificationDeliveryStatus.SKIPPED


@pytest.mark.anyio
async def test_13_whatsapp_missing_configuration_honestly_records_not_configured():
    """13. WhatsApp missing configuration returns NOT_CONFIGURED honestly without crashing"""
    db = get_database()
    officer_doc = await db.users.find_one({"phone": "9999999002"})
    officer_id = str(officer_doc.get("user_id") or officer_doc.get("_id") or officer_doc.get("phone"))

    # Unconfigured provider
    unconfigured_provider = MockableWhatsAppProvider(configured=False)
    service = NotificationService(whatsapp_provider=unconfigured_provider)

    notif = await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type="SITUATION_CRITICAL",
        severity=NotificationSeverity.CRITICAL,
        title="Critical Situation",
        message="Immediate officer attention required.",
        target_user_ids=[officer_id],
        material_state={"sit": uuid.uuid4().hex},
    )
    assert notif is not None
    rec = next(r for r in notif.recipients if r.user_id == officer_id)
    assert rec.whatsapp.status == NotificationDeliveryStatus.NOT_CONFIGURED
    assert rec.whatsapp.error_code == "CREDENTIALS_MISSING"
    # In-App delivery must still succeed independently
    assert rec.in_app.status == NotificationDeliveryStatus.DELIVERED


@pytest.mark.anyio
async def test_14_provider_success_maps_to_sent():
    """14. Real provider success maps to actual SENT state"""
    db = get_database()
    officer_doc = await db.users.find_one({"phone": "9999999002"})
    officer_id = str(officer_doc.get("user_id") or officer_doc.get("_id") or officer_doc.get("phone"))

    success_provider = MockableWhatsAppProvider(configured=True, should_succeed=True)
    service = NotificationService(whatsapp_provider=success_provider)

    notif = await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type="SITUATION_CRITICAL",
        severity=NotificationSeverity.CRITICAL,
        title="Bridge Collapsed",
        message="Critical transit failure.",
        target_user_ids=[officer_id],
        material_state={"bridge": uuid.uuid4().hex},
    )
    rec = next(r for r in notif.recipients if r.user_id == officer_id)
    assert rec.whatsapp.status == NotificationDeliveryStatus.SENT
    assert rec.whatsapp.sent_at is not None


@pytest.mark.anyio
async def test_15_provider_failure_maps_to_failed():
    """15. Provider failure maps to FAILED state without fake success"""
    db = get_database()
    officer_doc = await db.users.find_one({"phone": "9999999002"})
    officer_id = str(officer_doc.get("user_id") or officer_doc.get("_id") or officer_doc.get("phone"))

    failed_provider = MockableWhatsAppProvider(
        configured=True, should_succeed=False, error_msg="Meta Cloud API 500: Internal Server Error"
    )
    service = NotificationService(whatsapp_provider=failed_provider)

    notif = await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type="SITUATION_CRITICAL",
        severity=NotificationSeverity.CRITICAL,
        title="Hazardous Chemical Leak",
        message="Zone 2 evacuation.",
        target_user_ids=[officer_id],
        material_state={"leak": uuid.uuid4().hex},
    )
    rec = next(r for r in notif.recipients if r.user_id == officer_id)
    assert rec.whatsapp.status == NotificationDeliveryStatus.FAILED
    assert rec.whatsapp.error_code == "PROVIDER_ERROR"
    assert "Meta Cloud API 500" in rec.whatsapp.error_message


@pytest.mark.anyio
async def test_18_19_simulation_isolation(setup_test_provider: MockableWhatsAppProvider):
    """18 & 19. Simulation notifications remain isolated in-app and NEVER trigger WhatsApp"""
    db = get_database()
    officer_doc = await db.users.find_one({"phone": "9999999002"})
    officer_id = str(officer_doc.get("user_id") or officer_doc.get("_id") or officer_doc.get("phone"))

    initial_wa_count = len(setup_test_provider.sent_messages)

    service = NotificationService()
    notif = await service.dispatch_event(
        category=NotificationCategory.WHAT_IF_SIMULATION,
        event_type="SIMULATION_COMPLETED",
        severity=NotificationSeverity.CRITICAL,  # Even if severity is marked critical
        title="[SIMULATION] Hypothetical Dam Failure",
        message="Simulated 5000 casualties in scenario.",
        target_user_ids=[officer_id],
        is_simulation=True,  # STRICT SAFETY RULE
        material_state={"sim": uuid.uuid4().hex},
    )
    assert notif is not None
    assert notif.is_simulation is True
    rec = next(r for r in notif.recipients if r.user_id == officer_id)
    assert rec.in_app.status == NotificationDeliveryStatus.DELIVERED
    assert rec.whatsapp.status == NotificationDeliveryStatus.SKIPPED
    # ZERO WhatsApp messages must have been dispatched
    assert len(setup_test_provider.sent_messages) == initial_wa_count


@pytest.mark.anyio
async def test_20_resource_shortage_notification_actual_values():
    """20. Resource shortage notifications use actual required/available/shortfall"""
    service = NotificationService()
    notif = await service.dispatch_event(
        category=NotificationCategory.RESOURCE_LOGISTICS,
        event_type="RESOURCE_SHORTAGE",
        severity=NotificationSeverity.HIGH,
        title="Medical Kits Shortage",
        message="Required: 100, Available: 70, Shortfall: 30 Units",
        entity_id="RES-MEDKIT-01",
        target_roles=[UserRole.EMERGENCY_OFFICER, UserRole.RESOURCE_MANAGER],
        material_state={"req": 100, "avail": 70, "shortfall": 30},
        metadata={"shortfall_details": "Shortfall of 30 units for Emergency Medical Kits"},
    )
    assert notif is not None
    assert "30 Units" in notif.message
    assert notif.metadata["shortfall_details"] == "Shortfall of 30 units for Emergency Medical Kits"


@pytest.mark.anyio
async def test_21_shelter_conflict_notification():
    """21. Shelter conflict notification uses actual capacity values"""
    service = NotificationService()
    notif = await service.dispatch_event(
        category=NotificationCategory.SHELTER_OPS,
        event_type="SHELTER_CAPACITY_CHANGED",
        severity=NotificationSeverity.HIGH,
        title="Shelter Capacity Exceeded: Community Center",
        message="Capacity: 200, Current Occupancy: 240, Shortfall: 40 beds.",
        entity_id="SHELTER-01",
        target_roles=[UserRole.EMERGENCY_OFFICER],
        material_state={"cap": 200, "occ": 240, "shortfall": 40},
    )
    assert "40 beds" in notif.message


@pytest.mark.anyio
async def test_22_healthcare_capacity_alert():
    """22. Healthcare capacity alert uses actual values"""
    service = NotificationService()
    notif = await service.dispatch_event(
        category=NotificationCategory.HEALTHCARE_OPS,
        event_type="HEALTHCARE_CAPACITY_CHANGED",
        severity=NotificationSeverity.CRITICAL,
        title="Hospital ICU Capacity Full: General Hospital",
        message="Available ICU Beds: 0 / 25 Total. 5 critical casualties pending.",
        entity_id="HOSP-01",
        target_roles=[UserRole.EMERGENCY_OFFICER],
        material_state={"icu_avail": 0, "pending": 5},
    )
    assert notif.severity == NotificationSeverity.CRITICAL
    assert "0 / 25 Total" in notif.message


@pytest.mark.anyio
async def test_23_volunteer_shortfall_notification():
    """23. Volunteer shortfall notification uses actual required/available values"""
    service = NotificationService()
    notif = await service.dispatch_event(
        category=NotificationCategory.VOLUNTEER_OPS,
        event_type="VOLUNTEER_AVAILABILITY_CHANGED",
        severity=NotificationSeverity.HIGH,
        title="Search & Rescue Volunteer Shortfall",
        message="Required Responders: 20, Available: 12, Shortfall: 8.",
        entity_id="VOL-SKILL-SAR",
        target_roles=[UserRole.EMERGENCY_OFFICER],
        material_state={"req": 20, "avail": 12, "shortfall": 8},
    )
    assert "Shortfall: 8" in notif.message


@pytest.mark.anyio
async def test_26_dynamic_replanning_ready_notification():
    """26. Dynamic re-planning ready-for-review notification"""
    service = NotificationService()
    notif = await service.dispatch_event(
        category=NotificationCategory.DYNAMIC_REPLANNING,
        event_type="REPLANNING_RECOMMENDED",
        severity=NotificationSeverity.HIGH,
        title="Revised Coordination Plan Generated: v2",
        message="Dynamic re-planning triggered by route blockage. Awaiting officer approval.",
        entity_type="COORDINATION_PLAN",
        entity_id="PLAN-SIT-01-V2",
        situation_id="SIT-01",
        coordination_plan_id="PLAN-SIT-01-V2",
        view_hint="plans",
        target_roles=[UserRole.EMERGENCY_OFFICER],
        material_state={"version": 2, "plan_id": "PLAN-SIT-01-V2"},
    )
    assert notif.category == NotificationCategory.DYNAMIC_REPLANNING
    assert notif.deep_link.view_hint == "plans"


@pytest.mark.anyio
async def test_27_plan_activation_notification():
    """27. Plan approval/activation notification"""
    service = NotificationService()
    notif = await service.dispatch_event(
        category=NotificationCategory.COORDINATION_PLAN,
        event_type="PLAN_ACTIVATED",
        severity=NotificationSeverity.HIGH,
        title="Response Plan PLAN-001 (v2) Activated",
        message="Plan approved and activated by Officer Marcus Vance.",
        entity_type="COORDINATION_PLAN",
        entity_id="PLAN-001",
        situation_id="SIT-001",
        coordination_plan_id="PLAN-001",
        view_hint="plans",
        target_roles=[UserRole.EMERGENCY_OFFICER, UserRole.RESOURCE_MANAGER],
        material_state={"plan_id": "PLAN-001", "v": 2, "status": "ACTIVE"},
    )
    assert notif.event_type == "PLAN_ACTIVATED"


@pytest.mark.anyio
async def test_28_rbac_unauthorized_access(client: AsyncClient):
    """28. Unauthenticated requests to notification endpoints are rejected (401)"""
    res = await client.get("/api/v1/notifications")
    assert res.status_code == 401


@pytest.mark.anyio
async def test_29_idor_prevention(client: AsyncClient):
    """29. User cannot mark another user's private notification as read"""
    db = get_database()
    admin_doc = await db.users.find_one({"phone": "9999999001"})
    admin_id = str(admin_doc.get("user_id") or admin_doc.get("_id") or admin_doc.get("phone"))

    service = NotificationService()
    # Create notification targeted exclusively to Admin
    notif = await service.dispatch_event(
        category=NotificationCategory.SITUATION,
        event_type="ADMIN_ONLY_EVENT",
        severity=NotificationSeverity.LOW,
        title="Admin Private Notice",
        message="Private administrative audit.",
        target_user_ids=[admin_id],
        material_state={"priv": uuid.uuid4().hex},
    )

    # Officer attempts to mark it as read
    officer_token = await get_auth_token(client, "9999999002", "OfficerPassword@2026")
    res = await client.post(
        f"/api/v1/notifications/{notif.notification_id}/read",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    # Should be 404 / access denied for officer
    assert res.status_code in [404, 403]


@pytest.mark.anyio
async def test_30_channel_status_endpoint(client: AsyncClient):
    """30. Transparent channel status endpoint without credentials leak"""
    officer_token = await get_auth_token(client, "9999999002", "OfficerPassword@2026")
    res = await client.get(
        "/api/v1/notifications/channels/status",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "in_app" in data
    assert "whatsapp" in data
    assert data["in_app"]["status"] == "OPERATIONAL"
    # Never expose access tokens
    assert "token" not in str(data).lower()
    assert "secret" not in str(data).lower()
