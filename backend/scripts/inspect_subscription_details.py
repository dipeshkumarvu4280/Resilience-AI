import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URL = "mongodb+srv://dipeshkumarvu98_db_user:dipesh%404280@cluster0.fx2dtbx.mongodb.net/?appName=Cluster0"
DB_NAME = "resilience_db"

async def inspect():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    
    # Find citizen report RES-5CRSLFPX
    rep = await db["citizen_reports"].find_one({"report_id": "RES-5CRSLFPX"})
    print("CITIZEN REPORT RES-5CRSLFPX:")
    if rep:
        for k, v in rep.items():
            if k != "_id":
                print(f"  {k}: {v}")
    else:
        print("  NOT FOUND IN citizen_reports")
        
    print("\nALL ACTIVE PUSH SUBSCRIPTIONS:")
    subs = await db["push_subscriptions"].find({"status": "ACTIVE"}).to_list(100)
    for s in subs:
        print(f"ID: {s.get('subscription_id')}")
        print(f"  status: {s.get('status')}")
        print(f"  report_ids: {s.get('report_ids')}")
        print(f"  session_id: {s.get('session_id')}")
        print(f"  created_at: {s.get('created_at')}")
        print(f"  updated_at: {s.get('updated_at')}")
        print(f"  endpoint_fingerprint: {s.get('endpoint_hash')}")
        print(f"  last_provider_status: {s.get('last_provider_status')}")
        print()

if __name__ == "__main__":
    asyncio.run(inspect())
