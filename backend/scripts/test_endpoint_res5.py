import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath("."))
from motor.motor_asyncio import AsyncIOMotorClient
from app.api.v1.endpoints.safety_guidance import send_test_web_push

MONGODB_URL = "mongodb+srv://dipeshkumarvu98_db_user:dipesh%404280@cluster0.fx2dtbx.mongodb.net/?appName=Cluster0"
DB_NAME = "resilience_db"

async def test():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    
    res = await send_test_web_push(report_id="RES-5CRSLFPX", db=db)
    print("Endpoint response for RES-5CRSLFPX:")
    print(res)

if __name__ == "__main__":
    asyncio.run(test())
