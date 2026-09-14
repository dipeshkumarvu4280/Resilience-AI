import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URL = "mongodb+srv://dipeshkumarvu98_db_user:dipesh%404280@cluster0.fx2dtbx.mongodb.net/?appName=Cluster0"
DB_NAME = "resilience_db"

async def inspect():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    
    subs = await db["push_subscriptions"].find({}).to_list(100)
    print(f"Total push subscriptions in MongoDB Atlas: {len(subs)}")
    for s in subs:
        print(f" - Subscription ID: {s.get('subscription_id')}")
        print(f"   Status: {s.get('status')}")
        print(f"   Endpoint prefix: {s.get('endpoint', '')[:45]}...")
        print(f"   Report IDs: {s.get('report_ids')}")
        print(f"   User Agent: {s.get('user_agent')}")
        print(f"   Last Success: {s.get('last_success_at')}")
        print(f"   Last Failure: {s.get('last_failure_at')}")
        print(f"   Failure Reason: {s.get('failure_reason')}")
        print(f"   Last Provider Status: {s.get('last_provider_status')}")
        print()
        
    deliveries = await db["push_deliveries"].find({}).to_list(100)
    print(f"Total push deliveries in MongoDB Atlas: {len(deliveries)}")
    for d in deliveries:
        print(f" - Delivery ID: {d.get('delivery_id')}")
        print(f"   Event ID: {d.get('event_id')}")
        print(f"   Notification Type: {d.get('notification_type')}")
        print(f"   Status: {d.get('status')}")
        print(f"   Delivered At: {d.get('delivered_at')}")
        print()

if __name__ == "__main__":
    asyncio.run(inspect())
