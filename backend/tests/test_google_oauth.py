import pytest
from httpx import AsyncClient
from app.core.config import settings
from app.models.enums import UserRole
from app.db.mongodb import get_database


@pytest.mark.anyio
async def test_google_oauth_url_endpoint(client: AsyncClient):
    """
    Test GET /api/v1/auth/google/url endpoint.
    """
    old_id = settings.GOOGLE_CLIENT_ID
    try:
        settings.GOOGLE_CLIENT_ID = "test-google-client-id-123.apps.googleusercontent.com"
        res = await client.get("/api/v1/auth/google/url?intended_role=EMERGENCY_OFFICER")
        assert res.status_code == 200
        data = res.json()
        assert "auth_url" in data
        assert "accounts.google.com" in data["auth_url"]
        assert "client_id=test-google-client-id-123.apps.googleusercontent.com" in data["auth_url"]
        assert data["client_id"] == "test-google-client-id-123.apps.googleusercontent.com"
    finally:
        settings.GOOGLE_CLIENT_ID = old_id


@pytest.mark.anyio
async def test_google_oauth_unconfigured_error(client: AsyncClient):
    """
    When Google OAuth client ID is empty, endpoint must truthfully return 503.
    """
    old_id = settings.GOOGLE_CLIENT_ID
    try:
        settings.GOOGLE_CLIENT_ID = ""
        res = await client.get("/api/v1/auth/google/url")
        assert res.status_code == 503
        assert "Google sign-in is not configured for this environment" in res.json()["detail"]
    finally:
        settings.GOOGLE_CLIENT_ID = old_id


@pytest.mark.anyio
async def test_invalid_google_token_rejected(client: AsyncClient):
    """
    Test that invalid or unverified Google tokens are rejected with 401 Unauthorized.
    """
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={"id_token": "completely-invalid-malformed-token"}
    )
    assert res.status_code == 401
    assert "Google authentication could not be verified" in res.json()["detail"]


@pytest.mark.anyio
async def test_unauthorized_google_identity_attempting_admin_rejected(client: AsyncClient):
    """
    Unauthorized Google user attempting to access ADMIN must be rejected with 403 Forbidden.
    """
    test_token = "test-mock-google-token:sub-intruder-1001:intruder.random@gmail.com:Random Intruder"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "ADMIN",
        }
    )
    assert res.status_code == 403
    assert "not pre-provisioned or authorized" in res.json()["detail"]


@pytest.mark.anyio
async def test_unauthorized_google_identity_attempting_officer_rejected(client: AsyncClient):
    """
    Unauthorized Google user attempting to access EMERGENCY_OFFICER must be rejected with 403.
    """
    test_token = "test-mock-google-token:sub-intruder-1002:fake.officer@gmail.com:Fake Officer"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "EMERGENCY_OFFICER",
        }
    )
    assert res.status_code == 403
    assert "not pre-provisioned or authorized" in res.json()["detail"]


@pytest.mark.anyio
async def test_unauthorized_google_identity_attempting_resource_manager_rejected(client: AsyncClient):
    """
    Unauthorized Google user attempting to access RESOURCE_MANAGER must be rejected with 403.
    """
    test_token = "test-mock-google-token:sub-intruder-1003:fake.manager@gmail.com:Fake Manager"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "RESOURCE_MANAGER",
        }
    )
    assert res.status_code == 403
    assert "not pre-provisioned or authorized for the Resource Manager role" in res.json()["detail"]


@pytest.mark.anyio
async def test_authorized_official_operator_google_login(client: AsyncClient):
    """
    Authorized officer (pre-provisioned in DB with officer.vance@resilience.gov)
    authenticating with verified Google account succeeds and links immutable google_sub.
    """
    test_token = "test-mock-google-token:sub-officer-vance-408:officer.vance@resilience.gov:Officer Marcus Vance"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "EMERGENCY_OFFICER",
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["role"] == "EMERGENCY_OFFICER"
    assert data["user"]["full_name"] == "Officer Marcus Vance"
    assert data["user"]["google_sub"] == "sub-officer-vance-408"


@pytest.mark.anyio
async def test_volunteer_google_registration_creates_volunteer_only(client: AsyncClient):
    """
    Public Google authentication for new user creates a genuine VOLUNTEER account.
    """
    test_token = "test-mock-google-token:sub-volunteer-9901:sarah.volunteer@gmail.com:Sarah Volunteer"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "VOLUNTEER",
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["role"] == "VOLUNTEER"
    assert data["user"]["email"] == "sarah.volunteer@gmail.com"
    assert data["user"]["google_sub"] == "sub-volunteer-9901"


@pytest.mark.anyio
async def test_existing_volunteer_google_login(client: AsyncClient):
    """
    Existing volunteer Google user logs in successfully using their immutable Google sub.
    """
    test_token = "test-mock-google-token:sub-volunteer-9901:sarah.volunteer@gmail.com:Sarah Volunteer"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["role"] == "VOLUNTEER"
    assert data["user"]["email"] == "sarah.volunteer@gmail.com"


@pytest.mark.anyio
async def test_admin_can_provision_operator_google_identity(client: AsyncClient):
    """
    Admin can securely link an official Google email to an existing operator.
    """
    # 1. Login as Admin
    admin_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999001", "password": "AdminPassword@2026"}
    )
    assert admin_res.status_code == 200
    admin_token = admin_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Provision Google email for resource manager Elena Rostova
    patch_res = await client.patch(
        "/api/v1/users/9999999003/provision-google?google_email=elena.official.google@resilience.gov",
        headers=headers
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["email"] == "elena.official.google@resilience.gov"

    # 3. Elena logs in with her newly provisioned Google account (testing case-insensitive email normalization)
    elena_token = "test-mock-google-token:sub-elena-9003:ELENA.OFFICIAL.GOOGLE@RESILIENCE.GOV:Elena Rostova"
    login_res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": elena_token,
            "intended_role": "RESOURCE_MANAGER"
        }
    )
    assert login_res.status_code == 200
    assert login_res.json()["user"]["role"] == "RESOURCE_MANAGER"
    assert login_res.json()["user"]["google_sub"] == "sub-elena-9003"


@pytest.mark.anyio
async def test_google_sub_mismatch_rejection(client: AsyncClient):
    """
    If an official account is already linked to google_sub A,
    a different Google identity with google_sub B attempting to log into the same email is rejected.
    """
    # Officer Vance is linked to "sub-officer-vance-408"
    intruder_token = "test-mock-google-token:sub-attacker-9999:officer.vance@resilience.gov:Attacker Officer"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": intruder_token,
            "intended_role": "EMERGENCY_OFFICER",
        }
    )
    assert res.status_code == 403
    assert "already securely linked to a different Google identity" in res.json()["detail"]
