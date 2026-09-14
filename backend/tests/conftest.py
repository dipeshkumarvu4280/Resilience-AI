import pytest
from httpx import AsyncClient, ASGITransport
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.enums import UserRole
from app.main import app
from app.db.mongodb import (
    get_database,
    connect_to_mongo,
    close_mongo_connection,
    db_manager,
    init_db_indexes,
)

# Override database name to strictly isolate all tests from runtime resilience_db
settings.MONGODB_DB_NAME = "resilience_test_db"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def setup_db():
    settings.MONGODB_DB_NAME = "resilience_test_db"
    await close_mongo_connection()
    await connect_to_mongo()
    
    # Initialize indexes in test database
    await init_db_indexes()
    
    test_db = db_manager.db
    if test_db is not None:
        # Clean transient test collections for strict test isolation
        for col in ["citizen_reports", "dispatches", "timeline_events", "audit_logs", "situations", "monitoring_events", "push_subscriptions", "push_deliveries"]:
            await test_db[col].delete_many({})

    # Set FastAPI dependency override to guarantee tests use resilience_test_db
    app.dependency_overrides[get_database] = lambda: db_manager.db
    
    # Provision base authorized operators into the isolated test database
    if test_db is not None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        operators = [
            {
                "phone": "9999999001",
                "full_name": "Commander Sarah Jenkins",
                "email": "commander.jenkins@resilience.gov",
                "role": UserRole.ADMIN.value,
                "is_active": True,
                "badge_number": "ADM-001",
                "department_or_agency": "National Emergency Management Agency",
                "hashed_password": get_password_hash("AdminPassword@2026"),
                "volunteer_profile": None,
                "auth_provider": "local",
                "created_at": now,
                "updated_at": now,
            },
            {
                "phone": "9999999002",
                "full_name": "Officer Marcus Vance",
                "email": "officer.vance@resilience.gov",
                "role": UserRole.EMERGENCY_OFFICER.value,
                "is_active": True,
                "badge_number": "EOC-408",
                "department_or_agency": "Incident Command Center",
                "hashed_password": get_password_hash("OfficerPassword@2026"),
                "volunteer_profile": None,
                "auth_provider": "local",
                "created_at": now,
                "updated_at": now,
            },
            {
                "phone": "9999999003",
                "full_name": "Elena Rostova",
                "email": "elena.rostova@resilience.gov",
                "role": UserRole.RESOURCE_MANAGER.value,
                "is_active": True,
                "badge_number": "LOG-204",
                "department_or_agency": "Emergency Logistics & Disaster Supply",
                "hashed_password": get_password_hash("ResourcePassword@2026"),
                "volunteer_profile": None,
                "auth_provider": "local",
                "created_at": now,
                "updated_at": now,
            },
            {
                "phone": "9999999004",
                "full_name": "Test Volunteer",
                "email": "volunteer@resilience.gov",
                "role": UserRole.VOLUNTEER.value,
                "is_active": True,
                "badge_number": "VOL-101",
                "department_or_agency": "Community Volunteer Corps",
                "hashed_password": get_password_hash("VolunteerPassword@2026"),
                "volunteer_profile": None,
                "auth_provider": "local",
                "created_at": now,
                "updated_at": now,
            },
            {
                "phone": "9999999005",
                "full_name": "Test Citizen",
                "email": "citizen@resilience.gov",
                "role": UserRole.CITIZEN.value,
                "is_active": True,
                "badge_number": None,
                "department_or_agency": None,
                "hashed_password": get_password_hash("CitizenPassword@2026"),
                "volunteer_profile": None,
                "auth_provider": "local",
                "created_at": now,
                "updated_at": now,
            },
        ]
        for op in operators:
            await test_db["users"].update_one(
                {"phone": op["phone"]},
                {"$set": op},
                upsert=True
            )
            
    yield
    
    app.dependency_overrides.clear()
    await close_mongo_connection()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def db():
    return get_database()

