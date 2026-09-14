import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URL = "mongodb+srv://dipeshkumarvu98_db_user:dipesh%404280@cluster0.fx2dtbx.mongodb.net/?appName=Cluster0"
DB_NAME = "resilience_db"

async def inspect():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    
    subs = await db["push_subscriptions"].find({}).to_list(100)
    for s in subs:
        print(f"=== SUB: {s.get('subscription_id')} ===")
        for k, v in s.items():
            if k not in ['endpoint', 'p256dh', 'auth']:
                print(f"  {k}: {v}")
        print()

if __name__ == "__main__":
    asyncio.run(inspect())
