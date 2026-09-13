import asyncio
import os
import sys
from datetime import datetime, timezone
import uuid

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.models.enums import NotificationCategory, NotificationSeverity, NotificationDeliveryStatus
from app.services.notification.sms_provider import (
    TwilioSmsProvider,
    get_sms_provider,
    set_sms_provider_override,
)
from app.services.notification.notification_service import NotificationService
from app.db.mongodb import connect_to_mongo, close_mongo_connection, db_manager


async def run_trial_template_e2e_verification():
    print("=" * 60)
    print("VERIFICATION: TWILIO TRIAL TEMPLATE MODE DISPATCH")
    print("=" * 60)

    # Reset provider override so singleton initializes from updated settings
    set_sms_provider_override(None)

    # 1. Check runtime settings
    print("\n1. RUNTIME CONFIGURATION:")
    print(f"SMS_PROVIDER              : {settings.SMS_PROVIDER}")
    print(f"TWILIO_SMS_ENABLED        : {settings.TWILIO_SMS_ENABLED}")
    print(f"TWILIO_SMS_FROM           : {settings.TWILIO_SMS_FROM}")
    print(f"TWILIO_SMS_MODE           : {settings.TWILIO_SMS_MODE}")
    print(f"TWILIO_SMS_TRIAL_TEMPLATE : {settings.TWILIO_SMS_TRIAL_TEMPLATE}")
    print(f"TWILIO_ACCOUNT_SID (masked): ...{settings.TWILIO_ACCOUNT_SID[-4:] if settings.TWILIO_ACCOUNT_SID else 'None'}")
    print(f"TWILIO_AUTH_TOKEN Configured: {bool(settings.TWILIO_AUTH_TOKEN)}")

    assert settings.TWILIO_SMS_MODE == "trial_template", f"Expected trial_template, got {settings.TWILIO_SMS_MODE}"
    assert settings.TWILIO_SMS_TRIAL_TEMPLATE == "sms_internal_alerts"

    # 2. Provider Check
    print("\n2. PROVIDER INITIALIZATION:")
    provider = get_sms_provider()
    print(f"Provider Class            : {type(provider).__name__}")
    print(f"Provider Configured?      : {provider.is_configured()}")
    print(f"Provider Mode             : {getattr(provider, 'mode', 'N/A')}")
    print(f"Provider Trial Template   : {getattr(provider, 'trial_template', 'N/A')}")

    assert isinstance(provider, TwilioSmsProvider)
    assert provider.mode == "trial_template"
    assert provider.trial_template == "sms_internal_alerts"
    assert provider.is_configured() is True

    # 3. Connect to MongoDB for end-to-end delivery record check
    await connect_to_mongo()
    db = db_manager.db
    assert db is not None, "MongoDB connection failed"

    # 4. Dispatch Genuine Event via NotificationService
    verified_phone = "+919801338643"
    report_id = f"RES-VERIFY-{uuid.uuid4().hex[:6]}"
    guidance_token = f"tok_{uuid.uuid4().hex[:12]}"
    guidelines_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/safety-guidance/{guidance_token}"

    print(f"\n3. DISPATCHING LIVE NOTIFICATION EVENT TO {verified_phone}...")
    notif_service = NotificationService()

    notif = await notif_service.dispatch_event(
        category=NotificationCategory.CITIZEN_REPORT,
        event_type="REPORTER_SAFETY_GUIDANCE",
        severity=NotificationSeverity.HIGH,
        title="Emergency Report Received — Safety Guidance",
        message=(
            f"Your emergency report has been received.\n"
            f"Please follow safety guidance: {guidelines_url}"
        ),
        entity_type="CITIZEN_REPORT",
        entity_id=report_id,
        target_user_ids=[verified_phone],
        material_state={"report_id": report_id, "action": "TRIAL_TEMPLATE_VERIFICATION"},
        metadata={
            "report_id": report_id,
            "safety_guidelines_url": guidelines_url,
            "safety_guidance_token": guidance_token,
        },
        db=db,
    )

    assert notif is not None, "Notification dispatch returned None"
    print(f"Generated Notification ID: {notif.notification_id}")

    # Inspect recipient delivery state
    rec = notif.recipients[0]
    print("\n--- DELIVERY STATE IN MEMORY ---")
    print(f"In-App Status : {rec.in_app.status}")
    print(f"SMS Status    : {rec.sms.status}")
    print(f"SMS Provider ID: {rec.sms.provider_message_id}")
    print(f"SMS Error Code: {rec.sms.error_code}")
    print(f"SMS Error Msg : {rec.sms.error_message}")

    # 5. Check MongoDB record
    db_notif = await db["notifications"].find_one({"notification_id": notif.notification_id})
    assert db_notif is not None, "Notification not found in MongoDB"
    db_rec = db_notif["recipients"][0]

    print("\n--- DELIVERY STATE IN MONGODB ---")
    print(f"MongoDB Notification ID : {db_notif['notification_id']}")
    print(f"MongoDB Recipient Phone  : {db_rec['phone_number']}")
    print(f"MongoDB In-App Status    : {db_rec['in_app']['status']}")
    print(f"MongoDB SMS Status       : {db_rec['sms']['status']}")
    print(f"MongoDB Provider Msg SID : {db_rec['sms']['provider_message_id']}")

    assert db_rec["sms"]["status"] in [
        NotificationDeliveryStatus.QUEUED.value,
        NotificationDeliveryStatus.SENT.value,
        NotificationDeliveryStatus.DELIVERED.value,
    ], f"Unexpected SMS status in MongoDB: {db_rec['sms']['status']}"

    assert db_rec["sms"]["provider_message_id"] is not None
    assert str(db_rec["sms"]["provider_message_id"]).startswith("SM"), "Invalid Twilio Message SID"

    # Clean up test notification record from db
    await db["notifications"].delete_one({"notification_id": notif.notification_id})
    await close_mongo_connection()

    print("\n" + "=" * 60)
    print("ALL TRIAL TEMPLATE VERIFICATIONS PASSED")
    print(f"Twilio Message SID: {db_rec['sms']['provider_message_id']}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_trial_template_e2e_verification())
