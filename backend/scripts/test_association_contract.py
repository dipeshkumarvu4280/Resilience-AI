import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath("."))
from motor.motor_asyncio import AsyncIOMotorClient
from app.models.safety_guidance import PushSubscriptionCreate, PushKeys
from app.services.notification.web_push_service import WebPushService

MONGODB_URL = "mongodb+srv://dipeshkumarvu98_db_user:dipesh%404280@cluster0.fx2dtbx.mongodb.net/?appName=Cluster0"
DB_NAME = "resilience_db"

async def test():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    
    # 1. Find the latest active push subscription from the user's browser
    latest_sub = await db["push_subscriptions"].find_one({"subscription_id": "SUB-E46E002BA874"})
    print(f"Initial subscription SUB-E46E002BA874 report_ids: {latest_sub.get('report_ids')}")
    
    # 2. Test association of genuine report RES-5CRSLFPX
    sub_in = PushSubscriptionCreate(
        endpoint=latest_sub["endpoint"],
        keys=PushKeys(
            p256dh=latest_sub["p256dh"],
            auth=latest_sub["auth"],
        ),
        user_agent=latest_sub.get("user_agent"),
        report_id="RES-5CRSLFPX",
    )
    
    record = await WebPushService.save_subscription(sub_in, db=db)
    print(f"Updated subscription ID: {record.subscription_id}")
    print(f"Updated subscription report_ids: {record.report_ids}")
    
    # 3. Verify directly from MongoDB Atlas
    check_doc = await db["push_subscriptions"].find_one({"subscription_id": "SUB-E46E002BA874"})
    print(f"Atlas verified report_ids: {check_doc.get('report_ids')}")
    print(f"Contains RES-5CRSLFPX: {'RES-5CRSLFPX' in check_doc.get('report_ids', [])}")
    
    # 4. Verify query by report_id
    query_sub = await db["push_subscriptions"].find_one({"status": "ACTIVE", "report_ids": "RES-5CRSLFPX"})
    print(f"Query by report_ids='RES-5CRSLFPX' found: {query_sub is not None}")

if __name__ == "__main__":
    asyncio.run(test())
