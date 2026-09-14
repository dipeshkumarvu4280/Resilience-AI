import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath("."))
from motor.motor_asyncio import AsyncIOMotorClient
from app.services.notification.web_push_service import WebPushService
from app.models.safety_guidance import PushNotificationPayload

MONGODB_URL = "mongodb+srv://dipeshkumarvu98_db_user:dipesh%404280@cluster0.fx2dtbx.mongodb.net/?appName=Cluster0"
DB_NAME = "resilience_db"

async def test():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    
    # Query subscriptions for RES-5CRSLFPX
    cursor = db["push_subscriptions"].find({"status": "ACTIVE", "report_ids": "RES-5CRSLFPX"})
    subs = await cursor.to_list(10)
    print(f"Subscriptions found for RES-5CRSLFPX: {len(subs)}")
    
    payload = PushNotificationPayload(
        title="🚨 RESILIENCE Emergency Alert",
        body="Emergency alert channel verified for report RES-5CRSLFPX.",
        url="/safety-guidance/RES-5CRSLFPX",
    )
    
    for doc in subs:
        record = WebPushService._doc_to_record(doc)
        print(f"Testing push to subscription: {record.subscription_id}")
        ok = await WebPushService.send_web_push(record, payload, db=db)
        print(f"Push send result: {ok}")
        
        updated = await db["push_subscriptions"].find_one({"subscription_id": record.subscription_id})
        print(f"Last Provider Status: {updated.get('last_provider_status')}")
        print(f"Last Delivery Status: {updated.get('last_delivery_status')}")
        print(f"Failure Reason: {updated.get('failure_reason')}")

if __name__ == "__main__":
    asyncio.run(test())
