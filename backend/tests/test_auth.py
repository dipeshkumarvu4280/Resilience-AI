import pytest
import uuid
from httpx import AsyncClient


@pytest.mark.anyio
async def test_officer_login_success(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "phone": "9999999002",
            "password": "OfficerPassword@2026",
            "intended_role": "EMERGENCY_OFFICER",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role"] == "EMERGENCY_OFFICER"
    assert data["user"]["full_name"] == "Officer Marcus Vance"


@pytest.mark.anyio
async def test_wrong_password_rejected(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "phone": "9999999002",
            "password": "WrongPassword123!",
        },
    )
    assert response.status_code == 401
    assert "Invalid phone number or password" in response.json()["detail"]


@pytest.mark.anyio
async def test_volunteer_self_registration(client: AsyncClient):
    unique_phone = f"988{uuid.uuid4().int % 10000000:07d}"
    response = await client.post(
        "/api/v1/auth/register-volunteer",
        json={
            "full_name": "Aiden Patel",
            "phone": unique_phone,
            "password": "VolunteerSecure@2026",
            "skills": ["First Aid & CPR", "Search & Rescue"],
            "availability": "Available Immediately",
            "zone_or_district": "North Community Sector",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role"] == "VOLUNTEER"
    assert data["user"]["volunteer_profile"]["skills"] == ["First Aid & CPR", "Search & Rescue"]


@pytest.mark.anyio
async def test_google_auth_security_policy(client: AsyncClient):
    # Unprovisioned user attempting to claim OFFICER role via Google OAuth should be blocked
    response = await client.post(
        "/api/v1/auth/google",
        json={
            "id_token": "test-mock-google-token:sub-intruder-01:intruder@external.com:Intruder",
            "intended_role": "EMERGENCY_OFFICER",
        },
    )
    assert response.status_code == 403
    assert "Security Policy Violation" in response.json()["detail"]
