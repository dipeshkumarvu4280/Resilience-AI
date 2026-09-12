import random
import uuid
from datetime import datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.db.mongodb import get_database
from app.main import app
from app.models.enums import (
    NotificationCategory,
    NotificationDeliveryStatus,
    NotificationSeverity,
    UserRole,
)
from app.services.notification.notification_service import (
    NotificationService,
)
from app.services.notification.sms_provider import (
    MockableSmsProvider,
    normalize_phone_e164,
    set_sms_provider_override,
)
from app.services.notification.whatsapp_provider import (
    set_whatsapp_provider_override,
)


def gen_digits(n=5) -> str:
    return "".join(str(random.randint(0, 9)) for _ in range(n))


@pytest.fixture(autouse=True)
def cleanup_overrides():
    set_sms_provider_override(None)
    set_whatsapp_provider_override(None)
    yield
    set_sms_provider_override(None)
    set_whatsapp_provider_override(None)


@pytest.mark.anyio
async def test_admin_can_update_emergency_officer_phone():
    """1. Admin can successfully update an Emergency Officer's phone number with E.164 normalization."""
    db = get_database()

    admin_user = await db["users"].find_one({"phone": "9999999001"})
    assert admin_user is not None
    admin_token = create_access_token(
        data={
            "sub": admin_user["phone"],
            "user_id": str(admin_user["_id"]),
            "role": UserRole.ADMIN.value,
        }
    )

    officer_user = await db["users"].find_one({"phone": "9999999002"})
    assert officer_user is not None
    target_oid = str(officer_user["_id"])
    initial_phone = officer_user["phone"]

    # Pre-existing notification preference
    await db["notification_preferences"].update_one(
        {"user_id": target_oid},
        {
            "$set": {
                "preference_id": f"pref_{target_oid[-6:]}",
                "user_id": target_oid,
                "phone_number": initial_phone,
                "sms_enabled": True,
                "whatsapp_enabled": True,
                "notify_critical": True,
                "notify_high": True,
                "notify_operational": True,
                "notify_plan_updates": True,
                "notify_monitoring": True,
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )

    new_digits = gen_digits(5)
    new_raw_phone = f"98013{new_digits}"  # 10 digits without + -> normalizes to +9198013...
    expected_norm = f"+9198013{new_digits}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/users/{target_oid}",
            json={"phone": new_raw_phone},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["phone"] == expected_norm
        assert data["role"] == UserRole.EMERGENCY_OFFICER.value

    # Verify MongoDB users collection
    updated_user = await db["users"].find_one({"_id": officer_user["_id"]})
    assert updated_user["phone"] == expected_norm
    assert updated_user["role"] == UserRole.EMERGENCY_OFFICER.value

    # Verify notification_preferences synchronization
    updated_pref = await db["notification_preferences"].find_one({"user_id": target_oid})
    assert updated_pref["phone_number"] == expected_norm

    # Verify immutable audit log record
    audit_entry = await db["audit_logs"].find_one({"action": "ADMIN_OFFICER_PHONE_UPDATED", "target_user_id": target_oid})
    assert audit_entry is not None
    assert audit_entry["actor_id"] == str(admin_user["_id"])
    assert audit_entry["new_phone"] == expected_norm
    assert audit_entry["status"] == "SUCCESS"


@pytest.mark.anyio
async def test_non_admin_cannot_update_another_user_phone():
    """2. Non-admin users (Emergency Officer, Volunteer) are rejected with 403 Forbidden."""
    db = get_database()

    officer_user = await db["users"].find_one({"phone": "9999999002"})
    assert officer_user is not None
    officer_token = create_access_token(
        data={
            "sub": officer_user["phone"],
            "user_id": str(officer_user["_id"]),
            "role": UserRole.EMERGENCY_OFFICER.value,
        }
    )

    admin_user = await db["users"].find_one({"phone": "9999999001"})
    assert admin_user is not None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/users/{str(admin_user['_id'])}",
            json={"phone": f"+9198013{gen_digits(5)}"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert response.status_code == 403


@pytest.mark.anyio
async def test_unauthorized_request_rejected():
    """3. Unauthenticated requests are rejected with 401 Unauthorized."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/v1/users/some_user_id",
            json={"phone": "+919801338643"},
        )
        assert response.status_code == 401


@pytest.mark.anyio
async def test_invalid_phone_rejected():
    """4. Malformed, empty, or unparseable phone numbers are rejected with 400 Bad Request."""
    db = get_database()

    admin_user = await db["users"].find_one({"phone": "9999999001"})
    assert admin_user is not None
    admin_token = create_access_token(
        data={
            "sub": admin_user["phone"],
            "user_id": str(admin_user["_id"]),
            "role": UserRole.ADMIN.value,
        }
    )

    officer_user = await db["users"].find_one({"phone": "9999999002"})
    assert officer_user is not None

    invalid_numbers = ["123", "abc", "not_a_phone", "+", ""]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for num in invalid_numbers:
            response = await client.patch(
                f"/api/v1/users/{str(officer_user['_id'])}",
                json={"phone": num},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert response.status_code in (400, 422)


@pytest.mark.anyio
async def test_cannot_mutate_role_or_password_via_phone_endpoint():
    """5. Admin phone endpoint cannot mutate user role, password, or administrative flags."""
    db = get_database()

    admin_user = await db["users"].find_one({"phone": "9999999001"})
    assert admin_user is not None
    admin_token = create_access_token(
        data={
            "sub": admin_user["phone"],
            "user_id": str(admin_user["_id"]),
            "role": UserRole.ADMIN.value,
        }
    )

    officer_user = await db["users"].find_one({"phone": "9999999002"})
    assert officer_user is not None
    orig_password_hash = officer_user["hashed_password"]
    new_phone = f"+9199552{gen_digits(5)}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/users/{str(officer_user['_id'])}",
            json={
                "phone": new_phone,
                "role": "ADMIN",
                "password": "HackedPassword123!",
                "is_active": False,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == UserRole.EMERGENCY_OFFICER.value

    # Verify database unchanged for sensitive fields
    updated_doc = await db["users"].find_one({"_id": officer_user["_id"]})
    assert updated_doc["role"] == UserRole.EMERGENCY_OFFICER.value
    assert updated_doc["hashed_password"] == orig_password_hash
    assert updated_doc["is_active"] is True
    assert updated_doc["phone"] == new_phone


@pytest.mark.anyio
async def test_critical_notification_resolves_updated_officer_phone():
    """6. When an Emergency Officer's phone is updated, CRITICAL notifications resolve the new phone."""
    db = get_database()

    admin_user = await db["users"].find_one({"phone": "9999999001"})
    assert admin_user is not None
    admin_token = create_access_token(
        data={
            "sub": admin_user["phone"],
            "user_id": str(admin_user["_id"]),
            "role": UserRole.ADMIN.value,
        }
    )

    officer_user = await db["users"].find_one({"phone": "9999999002"})
    assert officer_user is not None
    target_oid = str(officer_user["_id"])

    updated_phone = f"+9198013{gen_digits(5)}"

    # 1. Update phone via Admin endpoint
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/users/{target_oid}",
            json={"phone": updated_phone},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

    # 2. Dispatch a CRITICAL event targeting EMERGENCY_OFFICER role
    mock_sms_provider = MockableSmsProvider(configured=True, should_succeed=True)
    service = NotificationService(sms_provider=mock_sms_provider)

    notif = await service.dispatch_event(
        category=NotificationCategory.CITIZEN_REPORT,
        event_type="REPORT_PRIORITY_CHANGED",
        severity=NotificationSeverity.CRITICAL,
        title="Cyclone Evacuation Order",
        message="Immediate shelter evacuation initiated.",
        target_roles=[UserRole.EMERGENCY_OFFICER],
        db=db,
    )

    assert notif is not None
    # Verify the recipient record resolved the updated phone
    officer_rec = next((r for r in notif.recipients if r.user_id == target_oid), None)
    assert officer_rec is not None
    assert officer_rec.phone_number == updated_phone
    assert officer_rec.sms.status == NotificationDeliveryStatus.SENT


@pytest.mark.anyio
async def test_citizen_phone_not_incorrectly_selected():
    """7. When targeting Emergency Officers, citizen phone numbers from unrelated reports are NOT selected."""
    db = get_database()
    suffix = uuid.uuid4().hex[:6]
    digits = gen_digits(5)

    # Create citizen report with a citizen phone number
    citizen_phone = f"+9196081{digits}"
    await db["citizen_reports"].insert_one({
        "report_id": f"REP-{suffix}",
        "citizen_name": "Citizen Reporter",
        "citizen_phone": citizen_phone,
        "emergency_type": "Flood",
        "impact_level": "CRITICAL",
        "created_at": datetime.now(timezone.utc),
    })

    # Dispatch notification targeting EMERGENCY_OFFICER role
    service = NotificationService()
    recipients = await service.resolve_recipients(
        target_roles=[UserRole.EMERGENCY_OFFICER],
        db=db,
    )

    # Ensure citizen phone is not in resolved officer recipients
    resolved_phones = [r.get("phone_number") for r in recipients]
    assert citizen_phone not in resolved_phones
