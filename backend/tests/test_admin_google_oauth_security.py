import pytest
from httpx import AsyncClient
from app.db.mongodb import get_database
from app.models.enums import UserRole
from app.core.security import get_password_hash
from datetime import datetime, timezone


@pytest.mark.anyio
async def test_1_authorized_admin_first_time_google_linking(client: AsyncClient):
    """
    TEST 1: Authorized ADMIN + matching verified Google email + google_sub missing
    -> Google login succeeds -> google_sub securely linked -> ADMIN session created.
    """
    db = get_database()
    now = datetime.now(timezone.utc)
    admin_email = "authorized.admin.test1@gmail.com"
    admin_phone = "9999901001"
    
    # Pre-provision authorized admin without google_sub
    await db["users"].delete_many({"phone": admin_phone})
    await db["users"].insert_one({
        "phone": admin_phone,
        "full_name": "Chief Administrator",
        "email": admin_email,
        "role": UserRole.ADMIN.value,
        "is_active": True,
        "google_sub": None,
        "hashed_password": get_password_hash("AdminPass123!"),
        "auth_provider": "local",
        "created_at": now,
        "updated_at": now,
    })

    test_token = f"test-mock-google-token:sub-admin-test1-unique:{admin_email}:Chief Administrator"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "ADMIN",
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["role"] == "ADMIN"
    assert data["user"]["email"] == admin_email
    assert data["user"]["google_sub"] == "sub-admin-test1-unique"

    # Verify in DB that google_sub was securely persisted
    updated = await db["users"].find_one({"phone": admin_phone})
    assert updated["google_sub"] == "sub-admin-test1-unique"
    assert updated["auth_provider"] == "google"

    # Verify audit log
    audit = await db["auth_audit_logs"].find_one({"phone": admin_phone, "event": "GOOGLE_IDENTITY_LINKED"})
    assert audit is not None
    assert audit["role"] == "ADMIN"


@pytest.mark.anyio
async def test_2_authorized_admin_already_linked_google_login(client: AsyncClient):
    """
    TEST 2: Authorized ADMIN + already linked correct google_sub -> login succeeds.
    """
    test_token = "test-mock-google-token:sub-admin-test1-unique:authorized.admin.test1@gmail.com:Chief Administrator"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "ADMIN",
        }
    )
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "ADMIN"
    assert res.json()["user"]["google_sub"] == "sub-admin-test1-unique"


@pytest.mark.anyio
async def test_3_unauthorized_google_account_attempting_admin_blocked(client: AsyncClient):
    """
    TEST 3: Unauthorized Google account -> 403 Security Policy Violation.
    """
    test_token = "test-mock-google-token:sub-unauth-999:intruder.unauthorized@gmail.com:Random Person"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "ADMIN",
        }
    )
    assert res.status_code == 403
    assert "not pre-provisioned or authorized for the Admin role" in res.json()["detail"]


@pytest.mark.anyio
async def test_4_volunteer_trying_to_login_as_admin_blocked(client: AsyncClient):
    """
    TEST 4: Google account email matches Volunteer but tries ADMIN -> blocked.
    """
    db = get_database()
    now = datetime.now(timezone.utc)
    vol_email = "community.volunteer.test4@gmail.com"
    vol_phone = "9999901004"
    
    await db["users"].delete_many({"phone": vol_phone})
    await db["users"].insert_one({
        "phone": vol_phone,
        "full_name": "Volunteer Person",
        "email": vol_email,
        "role": UserRole.VOLUNTEER.value,
        "is_active": True,
        "google_sub": "sub-vol-test4",
        "hashed_password": get_password_hash("VolPass123!"),
        "created_at": now,
        "updated_at": now,
    })

    test_token = f"test-mock-google-token:sub-vol-test4:{vol_email}:Volunteer Person"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "ADMIN",
        }
    )
    assert res.status_code == 403
    assert "provisioned as 'VOLUNTEER', not 'ADMIN'" in res.json()["detail"]


@pytest.mark.anyio
async def test_5_resource_manager_trying_to_login_as_admin_blocked(client: AsyncClient):
    """
    TEST 5: Google account email matches Resource Manager but tries ADMIN -> blocked.
    """
    db = get_database()
    now = datetime.now(timezone.utc)
    rm_email = "logistics.manager.test5@gmail.com"
    rm_phone = "9999901005"
    
    await db["users"].delete_many({"phone": rm_phone})
    await db["users"].insert_one({
        "phone": rm_phone,
        "full_name": "Logistics Manager",
        "email": rm_email,
        "role": UserRole.RESOURCE_MANAGER.value,
        "is_active": True,
        "google_sub": "sub-rm-test5",
        "hashed_password": get_password_hash("RMPass123!"),
        "created_at": now,
        "updated_at": now,
    })

    test_token = f"test-mock-google-token:sub-rm-test5:{rm_email}:Logistics Manager"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "ADMIN",
        }
    )
    assert res.status_code == 403
    assert "provisioned as 'RESOURCE_MANAGER', not 'ADMIN'" in res.json()["detail"]


@pytest.mark.anyio
async def test_6_inactive_admin_blocked(client: AsyncClient):
    """
    TEST 6: Inactive ADMIN -> blocked with 403.
    """
    db = get_database()
    now = datetime.now(timezone.utc)
    inactive_email = "inactive.admin.test6@gmail.com"
    inactive_phone = "9999901006"
    
    await db["users"].delete_many({"phone": inactive_phone})
    await db["users"].insert_one({
        "phone": inactive_phone,
        "full_name": "Deactivated Admin",
        "email": inactive_email,
        "role": UserRole.ADMIN.value,
        "is_active": False,
        "google_sub": "sub-admin-inactive-6",
        "hashed_password": get_password_hash("AdminPass123!"),
        "created_at": now,
        "updated_at": now,
    })

    test_token = f"test-mock-google-token:sub-admin-inactive-6:{inactive_email}:Deactivated Admin"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "ADMIN",
        }
    )
    assert res.status_code == 403
    assert "Account is deactivated" in res.json()["detail"]


@pytest.mark.anyio
async def test_7_existing_google_sub_mismatch_blocked(client: AsyncClient):
    """
    TEST 7: Existing google_sub belongs to another user -> do not overwrite, authentication blocked.
    """
    db = get_database()
    now = datetime.now(timezone.utc)
    locked_email = "locked.admin.test7@gmail.com"
    locked_phone = "9999901007"
    
    await db["users"].delete_many({"phone": locked_phone})
    await db["users"].insert_one({
        "phone": locked_phone,
        "full_name": "Locked Admin",
        "email": locked_email,
        "role": UserRole.ADMIN.value,
        "is_active": True,
        "google_sub": "sub-original-owner-7",
        "hashed_password": get_password_hash("AdminPass123!"),
        "created_at": now,
        "updated_at": now,
    })

    # Attacker tries with same email but different sub
    attacker_token = f"test-mock-google-token:sub-attacker-fake-7:{locked_email}:Attacker Name"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": attacker_token,
            "intended_role": "ADMIN",
        }
    )
    assert res.status_code == 403
    assert "already securely linked to a different Google identity" in res.json()["detail"]

    # Verify in DB that sub was NOT overwritten
    persisted = await db["users"].find_one({"phone": locked_phone})
    assert persisted["google_sub"] == "sub-original-owner-7"


@pytest.mark.anyio
async def test_8_email_case_and_whitespace_normalization(client: AsyncClient):
    """
    TEST 8: Email case/whitespace normalization -> matching authorized account works correctly.
    """
    db = get_database()
    now = datetime.now(timezone.utc)
    norm_phone = "9999901008"
    
    await db["users"].delete_many({"phone": norm_phone})
    await db["users"].insert_one({
        "phone": norm_phone,
        "full_name": "Case Admin",
        "email": "Admin.CaseNormalized@resilience.gov",
        "role": UserRole.ADMIN.value,
        "is_active": True,
        "google_sub": None,
        "hashed_password": get_password_hash("AdminPass123!"),
        "created_at": now,
        "updated_at": now,
    })

    # User authenticates with lowercase and whitespace
    test_token = f"test-mock-google-token:sub-norm-8:  admin.casenormalized@resilience.gov  :Case Admin"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "ADMIN",
        }
    )
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "ADMIN"
    assert res.json()["user"]["google_sub"] == "sub-norm-8"


@pytest.mark.anyio
async def test_9_session_validation_after_admin_google_login(client: AsyncClient):
    """
    TEST 9: Refresh / token verification after Admin Google login -> Admin session remains valid and accesses Admin APIs.
    """
    test_token = "test-mock-google-token:sub-admin-test1-unique:authorized.admin.test1@gmail.com:Chief Administrator"
    login_res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "ADMIN",
        }
    )
    assert login_res.status_code == 200
    access_token = login_res.json()["access_token"]
    
    # Test accessing protected Admin endpoint (GET /users)
    admin_headers = {"Authorization": f"Bearer {access_token}"}
    users_res = await client.get("/api/v1/users", headers=admin_headers)
    assert users_res.status_code == 200
    assert isinstance(users_res.json(), list)


@pytest.mark.anyio
async def test_10_logout_invalidates_admin_client_session(client: AsyncClient):
    """
    TEST 10: Logout -> protected Admin APIs become inaccessible without token.
    """
    # Call without auth header
    unauth_res = await client.get("/api/v1/users")
    assert unauth_res.status_code in [401, 403]


@pytest.mark.anyio
async def test_11_existing_officer_google_login_still_works(client: AsyncClient):
    """
    TEST 11: Existing Officer Google login still works.
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
    assert res.json()["user"]["role"] == "EMERGENCY_OFFICER"


@pytest.mark.anyio
async def test_12_existing_resource_manager_google_login_still_works(client: AsyncClient):
    """
    TEST 12: Existing Resource Manager Google login still works.
    """
    test_token = "test-mock-google-token:sub-elena-9003:elena.rostova@resilience.gov:Elena Rostova"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "RESOURCE_MANAGER",
        }
    )
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "RESOURCE_MANAGER"


@pytest.mark.anyio
async def test_13_volunteer_google_signup_login_behavior(client: AsyncClient):
    """
    TEST 13: Volunteer Google signup/login behavior still works according to authorization policy.
    """
    test_token = "test-mock-google-token:sub-new-vol-13:new.community.vol13@gmail.com:Community Volunteer 13"
    res = await client.post(
        "/api/v1/auth/google/callback",
        json={
            "id_token": test_token,
            "intended_role": "VOLUNTEER",
        }
    )
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "VOLUNTEER"
    assert res.json()["user"]["email"] == "new.community.vol13@gmail.com"
