import asyncio
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.services.notification.sms_provider import TwilioSmsProvider

async def test_trial_template_dispatch():
    trial_provider = TwilioSmsProvider(mode="trial_template", trial_template="sms_internal_alerts")
    test_number = "+919801338643"
    print(f"Sending trial_template SMS to {test_number}...")
    res = await trial_provider.send_sms(
        recipient_phone=test_number,
        message="Critical Emergency Alert"
    )
    print("\n--- TRIAL TEMPLATE DELIVERY RESULT ---")
    print(f"Status      : {res.status}")
    print(f"Message SID : {res.provider_message_id}")
    print(f"Error Code  : {res.error_code}")
    print(f"Error Msg   : {res.error_message}")

if __name__ == "__main__":
    asyncio.run(test_trial_template_dispatch())
