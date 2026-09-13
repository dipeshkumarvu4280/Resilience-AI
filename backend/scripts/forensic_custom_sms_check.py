import asyncio
import os
import sys
from datetime import datetime, timezone

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.models.enums import NotificationCategory, NotificationSeverity, NotificationDeliveryStatus
from app.services.notification.sms_provider import (
    TwilioSmsProvider,
    get_sms_provider,
    normalize_phone_e164,
)
from app.services.notification.notification_service import NotificationService
from app.db.mongodb import connect_to_mongo, close_mongo_connection, db_manager


async def run_forensic_sms_check():
    print("=" * 60)
    print("FORENSIC TWILIO CUSTOM SMS INSPECTION")
    print("=" * 60)

    # 1. Inspect Settings & Runtime Mode
    print("\n1. RUNTIME CONFIGURATION CHECK:")
    print(f"SMS_PROVIDER                : {settings.SMS_PROVIDER}")
    print(f"TWILIO_SMS_ENABLED          : {settings.TWILIO_SMS_ENABLED}")
    print(f"TWILIO_SMS_FROM             : {settings.TWILIO_SMS_FROM}")
    print(f"TWILIO_SMS_MODE             : {settings.TWILIO_SMS_MODE}")
    print(f"TWILIO_SMS_TRIAL_TEMPLATE   : {settings.TWILIO_SMS_TRIAL_TEMPLATE}")
    print(f"TWILIO_ACCOUNT_SID (masked) : ...{settings.TWILIO_ACCOUNT_SID[-4:] if settings.TWILIO_ACCOUNT_SID else 'None'}")
    print(f"TWILIO_AUTH_TOKEN Configured: {bool(settings.TWILIO_AUTH_TOKEN)}")

    # 2. Inspect SMS Provider instance
    print("\n2. SMS PROVIDER INSTANTIATION CHECK:")
    provider = get_sms_provider()
    print(f"Provider Class              : {type(provider).__name__}")
    print(f"Provider Configured?        : {provider.is_configured()}")
    print(f"Provider Resolved Mode      : {getattr(provider, 'mode', 'N/A')}")
    print(f"Provider Trial Template     : {getattr(provider, 'trial_template', 'N/A')}")

    assert getattr(provider, "mode", "").lower() == "custom", f"Expected mode 'custom', got '{getattr(provider, 'mode', '')}'"
    print("-> Mode check: CONFIRMED 'custom'")

    # 3. Simulate Reporter Safety Guidance message construction
    print("\n3. SAFETY GUIDANCE MESSAGE PATH TRACE:")
    report_id = "RES-2026-TEST-E2E"
    safety_guidance_token = "tok_test_guidance_2026_forensic"
    safety_guidelines_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/safety-guidance/{safety_guidance_token}"
    
    reporter_title = "Emergency Report Received — Safety Guidance"
    reporter_message = (
        f"Your emergency report has been received.\n"
        f"Please follow the safety guidance while responders review your report.\n\n"
        f"View Safety Guidelines: {safety_guidelines_url}"
    )

    notif_service = NotificationService()
    sms_text = notif_service._format_sms_message(
        severity=NotificationSeverity.HIGH,
        title=reporter_title,
        message=reporter_message,
    )

    print("Constructed SMS Body:")
    print("-" * 40)
    print(sms_text)
    print("-" * 40)

    assert safety_guidelines_url in sms_text, "Safety Guidelines URL missing from SMS text"
    assert "https://resilience-ai-pied.vercel.app/safety-guidance/" in sms_text, "Canonical frontend URL missing"
    print("-> Body trace: CONFIRMED application safety guidance + URL intact.")

    # 4. Perform live SMS test to verified phone number
    target_phone = "+919801338643"
    print(f"\n4. DISPATCHING TEST CUSTOM SMS TO {target_phone}...")
    
    delivery_result = await provider.send_sms(
        recipient_phone=target_phone,
        message=sms_text,
    )

    print("\n--- TWILIO DELIVERY RESULT ---")
    print(f"Status             : {delivery_result.status}")
    print(f"Provider Message SID: {delivery_result.provider_message_id}")
    print(f"Error Code         : {delivery_result.error_code}")
    print(f"Error Message      : {delivery_result.error_message}")
    print(f"Timestamp          : {delivery_result.timestamp}")

    print("\n" + "=" * 60)
    if delivery_result.status in (NotificationDeliveryStatus.SENT, NotificationDeliveryStatus.QUEUED, NotificationDeliveryStatus.SENDING, NotificationDeliveryStatus.DELIVERED):
        print("RESULT: PASS — Twilio accepted custom SMS message with valid Message SID.")
    else:
        print(f"RESULT: FAILED — Twilio delivery status {delivery_result.status}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_forensic_sms_check())
