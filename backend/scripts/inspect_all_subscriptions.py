import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URL = "mongodb+srv://dipeshkumarvu98_db_user:dipesh%404280@cluster0.fx2dtbx.mongodb.net/?appName=Cluster0"
DB_NAME = "resilience_db"

async def inspect():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    
    print("ALL PUSH SUBSCRIPTIONS (SORTED BY CREATED_AT DESC):")
    subs = await db["push_subscriptions"].find({}).sort("created_at", -1).to_list(100)
    for s in subs:
        print(f"ID: {s.get('subscription_id')}")
        print(f"  status: {s.get('status')}")
        print(f"  report_ids: {s.get('report_ids')}")
        print(f"  session_id: {s.get('session_id')}")
        print(f"  created_at: {s.get('created_at')}")
        print(f"  updated_at: {s.get('updated_at')}")
        print(f"  endpoint_hash: {s.get('endpoint_hash')}")
        print()
        
    print("\nRECENT CITIZEN REPORTS:")
    reps = await db["citizen_reports"].find({}).sort("created_at", -1).limit(5).to_list(5)
    for r in reps:
        print(f"  Report ID: {r.get('report_id')}, created: {r.get('created_at')}, type: {r.get('emergency_type')}")

if __name__ == "__main__":
    asyncio.run(inspect())
