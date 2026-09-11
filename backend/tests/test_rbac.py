import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_rbac_officer_cannot_access_admin_users(client: AsyncClient):
    # Log in as Officer
    officer_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999002", "password": "OfficerPassword@2026"}
    )
    token = officer_res.json()["access_token"]
    
    # Try to access Admin Users endpoint
    headers = {"Authorization": f"Bearer {token}"}
    users_res = await client.get("/api/v1/users", headers=headers)
    assert users_res.status_code == 403
    assert "Access denied" in users_res.json()["detail"]


@pytest.mark.anyio
async def test_rbac_admin_can_access_admin_users(client: AsyncClient):
    # Log in as Admin
    admin_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999001", "password": "AdminPassword@2026"}
    )
    token = admin_res.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    users_res = await client.get("/api/v1/users", headers=headers)
    assert users_res.status_code == 200
    assert isinstance(users_res.json(), list)
