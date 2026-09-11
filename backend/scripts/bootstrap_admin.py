"""
RESILIENCE Operator Provisioning Utility.
Authorizes official role accounts in MongoDB with hashed credentials.
NO dummy operational data (incidents, resources, shelters) is created.
"""
import asyncio
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.enums import UserRole


async def provision_authorized_operators():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    print(f"Connecting to MongoDB at {settings.MONGODB_URL} [{settings.MONGODB_DB_NAME}]...")
    
    operators = [
        {
            "phone": "9999999001",
            "full_name": "Commander Sarah Jenkins",
            "email": "commander.jenkins@resilience.gov",
            "role": UserRole.ADMIN.value,
            "is_active": True,
            "badge_number": "ADM-001",
            "department_or_agency": "National Emergency Management Agency",
            "password": "AdminPassword@2026",
        },
        {
            "phone": "9999999002",
            "full_name": "Emergency Duty Officer",
            "email": "officer@resilience.gov",
            "role": UserRole.EMERGENCY_OFFICER.value,
            "is_active": True,
            "badge_number": "EOC-408",
            "department_or_agency": "Incident Command Center",
            "password": "OfficerPassword@2026",
        },
        {
            "phone": "9999999003",
            "full_name": "Elena Rostova",
            "email": "elena.rostova@resilience.gov",
            "role": UserRole.RESOURCE_MANAGER.value,
            "is_active": True,
            "badge_number": "LOG-204",
            "department_or_agency": "Emergency Logistics & Disaster Supply",
            "password": "ResourcePassword@2026",
        },
    ]
    
    now = datetime.now(timezone.utc)
    
    for op in operators:
        existing = await db["users"].find_one({"phone": op["phone"]})
        if existing:
            # Preserve existing operator's customized name, email, badge and google_sub
            update_data = {
                "role": op["role"],
                "is_active": True,
                "hashed_password": get_password_hash(op["password"]),
                "updated_at": now,
            }
            # Only set default metadata if account is entirely unconfigured
            if not existing.get("full_name"):
                update_data["full_name"] = op["full_name"]
            if not existing.get("email"):
                update_data["email"] = op["email"]
            if not existing.get("department_or_agency"):
                update_data["department_or_agency"] = op["department_or_agency"]

            await db["users"].update_one(
                {"phone": op["phone"]},
                {"$set": update_data}
            )
            print(f"  [UPDATED] Authorized {op['role']}: {existing.get('full_name', op['full_name'])} (Phone: {op['phone']})")
        else:
            new_doc = {
                "phone": op["phone"],
                "full_name": op["full_name"],
                "email": op["email"],
                "role": op["role"],
                "is_active": True,
                "badge_number": op["badge_number"],
                "department_or_agency": op["department_or_agency"],
                "hashed_password": get_password_hash(op["password"]),
                "volunteer_profile": None,
                "auth_provider": "local",
                "created_at": now,
                "updated_at": now,
                "last_login": None,
            }
            await db["users"].insert_one(new_doc)
            print(f"  [CREATED] Authorized {op['role']}: {op['full_name']} (Phone: {op['phone']})")
            
    client.close()
    print("\nAuthorization provisioning completed successfully.")


if __name__ == "__main__":
    asyncio.run(provision_authorized_operators())
