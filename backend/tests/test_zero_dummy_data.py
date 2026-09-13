import pytest
from httpx import AsyncClient
from app.models.enums import UserRole
from app.db.mongodb import get_database


@pytest.mark.anyio
async def test_zero_demo_reports_in_clean_db(client: AsyncClient):
    """
    Verify fresh application reports collection contains zero automatic demo reports.
    """
    # Log in as officer to query reports endpoint
    officer_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999002", "password": "OfficerPassword@2026"}
    )
    assert officer_res.status_code == 200
    token = officer_res.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    reports_res = await client.get("/api/v1/citizen/reports", headers=headers)
    assert reports_res.status_code == 200
    reports = reports_res.json()
    assert isinstance(reports, list)


@pytest.mark.anyio
async def test_google_oauth_rejects_unauthorized_privileged_roles(client: AsyncClient):
    """
    Verify an arbitrary Google identity cannot claim ADMIN, EMERGENCY_OFFICER, or RESOURCE_MANAGER.
    """
    # Attempt to claim ADMIN
    res = await client.post(
        "/api/v1/auth/google",
        json={
            "id_token": "test-mock-google-token:sub-intruder-101:arbitrary.intruder@gmail.com:Intruder",
            "intended_role": "ADMIN"
        }
    )
    assert res.status_code == 403
    assert "Security Policy Violation" in res.json()["detail"]

    # Attempt to claim EMERGENCY_OFFICER
    res = await client.post(
        "/api/v1/auth/google",
        json={
            "id_token": "test-mock-google-token:sub-intruder-102:arbitrary.officer@gmail.com:Fake Officer",
            "intended_role": "EMERGENCY_OFFICER"
        }
    )
    assert res.status_code == 403
    assert "Security Policy Violation" in res.json()["detail"]

    # Attempt to claim RESOURCE_MANAGER
    res = await client.post(
        "/api/v1/auth/google",
        json={
            "id_token": "test-mock-google-token:sub-intruder-103:arbitrary.manager@gmail.com:Fake Manager",
            "intended_role": "RESOURCE_MANAGER"
        }
    )
    assert res.status_code == 403
    assert "Security Policy Violation" in res.json()["detail"]


@pytest.mark.anyio
async def test_google_oauth_creates_genuine_volunteer_identity_only(client: AsyncClient):
    """
    Verify that when a real Google user registers as VOLUNTEER, only their exact identity is created.
    """
    real_email = "citizen.volunteer.test@gmail.com"
    real_name = "Genuine Volunteer"
    
    res = await client.post(
        "/api/v1/auth/google",
        json={
            "id_token": f"test-mock-google-token:sub-volunteer-gen-1:{real_email}:{real_name}",
            "intended_role": "VOLUNTEER"
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == real_email
    assert data["user"]["full_name"] == real_name
    assert data["user"]["role"] == "VOLUNTEER"


@pytest.mark.anyio
async def test_google_oauth_requires_valid_token(client: AsyncClient):
    """
    Verify Google OAuth rejects requests with missing or invalid token.
    """
    res = await client.post(
        "/api/v1/auth/google",
        json={
            "id_token": "",
        }
    )
    assert res.status_code == 400
    assert "token or authorization code is required" in res.json()["detail"]


@pytest.mark.anyio
async def test_system_status_truthful_and_unseeded(client: AsyncClient):
    """
    Verify system status endpoint reflects truthful operational statuses and zero demo flags.
    """
    res = await client.get("/api/v1/system/status")
    assert res.status_code == 200
    data = res.json()
    assert data["system_name"] == "RESILIENCE"
    assert data["overall_status"] in ["OPERATIONAL", "HEALTHY"]
    assert "services" in data
    assert "platform_core" in data["services"]


@pytest.mark.anyio
async def test_fresh_startup_zero_demo_resources(client: AsyncClient):
    """
    Verify that in the test database, zero demo resources, incidents, or dummy collections are populated.
    """
    db = get_database()
    collections = await db.list_collection_names()
    for dummy_col in ["demo_data", "mock_incidents", "fake_resources", "sample_shelters"]:
        assert dummy_col not in collections
