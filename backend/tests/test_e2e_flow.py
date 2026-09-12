import pytest
import uuid
from httpx import AsyncClient


@pytest.mark.anyio
async def test_full_e2e_acceptance_suite(client: AsyncClient):
    print("\n--- 1. Testing System Health & Telemetry ---")
    health_res = await client.get("/api/v1/system/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "healthy"
    assert health_res.json()["database"] == "connected"

    status_res = await client.get("/api/v1/system/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["overall_status"] == "OPERATIONAL"
    assert status_data["services"]["platform_core"]["status"] == "Operational"
    assert status_data["services"]["database_storage"]["status"] == "Operational"
    assert status_data["services"]["auth_security"]["status"] == "Operational"
    # Verify genuine active services reported truthfully as Operational
    assert status_data["services"]["citizen_reporting"]["status"] == "Operational"
    assert status_data["services"]["incident_triage"]["status"] == "Operational"
    assert status_data["services"]["gis_mapping"]["status"] == "Operational"
    assert status_data["services"]["ai_intelligence"]["status"] == "Operational"

    print("\n--- 2. Testing Emergency Officer Login ---")
    officer_login = await client.post(
        "/api/v1/auth/login",
        json={
            "phone": "9999999002",
            "password": "OfficerPassword@2026",
            "intended_role": "EMERGENCY_OFFICER",
        },
    )
    assert officer_login.status_code == 200
    officer_data = officer_login.json()
    assert officer_data["user"]["role"] == "EMERGENCY_OFFICER"
    assert officer_data["user"]["badge_number"] == "EOC-408"
    officer_token = officer_data["access_token"]

    print("\n--- 3. Testing Resource Manager Login ---")
    rm_login = await client.post(
        "/api/v1/auth/login",
        json={
            "phone": "9999999003",
            "password": "ResourcePassword@2026",
            "intended_role": "RESOURCE_MANAGER",
        },
    )
    assert rm_login.status_code == 200
    rm_data = rm_login.json()
    assert rm_data["user"]["role"] == "RESOURCE_MANAGER"
    assert rm_data["user"]["badge_number"] == "LOG-204"

    print("\n--- 4. Testing Admin Login & User Listing ---")
    admin_login = await client.post(
        "/api/v1/auth/login",
        json={
            "phone": "9999999001",
            "password": "AdminPassword@2026",
            "intended_role": "ADMIN",
        },
    )
    assert admin_login.status_code == 200
    admin_data = admin_login.json()
    assert admin_data["user"]["role"] == "ADMIN"
    admin_token = admin_data["access_token"]

    # Admin lists genuine users from MongoDB
    admin_users_res = await client.get(
        "/api/v1/users",
        params={"limit": 200},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert admin_users_res.status_code == 200
    users_list = admin_users_res.json()
    assert len(users_list) >= 3
    # Check that Sarah Jenkins, Marcus Vance, Elena Rostova exist in real DB records
    phones = [u["phone"] for u in users_list]
    assert "9999999001" in phones
    assert "9999999002" in phones
    assert "9999999003" in phones

    print("\n--- 5. Testing RBAC Security Guard ---")
    # Officer attempting to call Admin user list MUST BE 403 FORBIDDEN
    officer_forbidden_res = await client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert officer_forbidden_res.status_code == 403
    assert "Access denied" in officer_forbidden_res.json()["detail"]

    # Wrong intended portal rejection
    officer_wrong_portal = await client.post(
        "/api/v1/auth/login",
        json={
            "phone": "9999999002",
            "password": "OfficerPassword@2026",
            "intended_role": "ADMIN",  # Officer claiming Admin portal
        },
    )
    assert officer_wrong_portal.status_code == 403

    print("\n--- 6. Testing Volunteer Self-Registration & Portal Flow ---")
    unique_phone = f"988{uuid.uuid4().int % 10000000:07d}"
    vol_reg = await client.post(
        "/api/v1/auth/register-volunteer",
        json={
            "full_name": "Jordan Chen",
            "phone": unique_phone,
            "password": "VolunteerPassword@2026",
            "skills": ["First Aid & CPR", "Search & Rescue", "Emergency / Heavy Driving"],
            "availability": "Available Immediately",
            "zone_or_district": "North Community Sector",
        },
    )
    assert vol_reg.status_code == 201
    vol_data = vol_reg.json()
    assert vol_data["user"]["full_name"] == "Jordan Chen"
    assert vol_data["user"]["role"] == "VOLUNTEER"
    assert len(vol_data["user"]["volunteer_profile"]["skills"]) == 3
    vol_token = vol_data["access_token"]

    # Verify /me endpoint with volunteer token
    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {vol_token}"}
    )
    assert me_res.status_code == 200
    assert me_res.json()["full_name"] == "Jordan Chen"

    print("\n--- 7. Testing Google Authentication RBAC Security ---")
    # 7a. Pre-authorized Google account login
    google_officer = await client.post(
        "/api/v1/auth/google",
        json={
            "id_token": "test-mock-google-token:sub-officer-vance-408:officer.vance@resilience.gov:Officer Marcus Vance",
            "intended_role": "EMERGENCY_OFFICER",
        },
    )
    assert google_officer.status_code == 200
    assert google_officer.json()["user"]["role"] == "EMERGENCY_OFFICER"

    # 7b. Unprovisioned Google identity attempting to claim ADMIN role MUST BE 403
    unauth_google = await client.post(
        "/api/v1/auth/google",
        json={
            "id_token": "test-mock-google-token:sub-hacker-456:hacker@external-mail.com:Intruder",
            "intended_role": "ADMIN",
        },
    )
    assert unauth_google.status_code == 403
    assert "Security Policy Violation" in unauth_google.json()["detail"]

    print("\n--- 8. Testing Complete Password Reset Flow ---")
    reset_phone = unique_phone
    # 8a. Request OTP
    otp_req = await client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"phone": reset_phone}
    )
    assert otp_req.status_code == 200
    assert "verification code" in otp_req.json()["message"].lower()

    # 8b. Retrieve and verify OTP from DB
    from app.db.mongodb import get_database
    from app.core.security import hash_otp
    db = get_database()
    known_code = "771122"
    await db["otps"].update_one(
        {"phone": reset_phone, "is_used": False},
        {"$set": {"hashed_otp": hash_otp(known_code)}}
    )

    verify_res = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"phone": reset_phone, "otp": known_code}
    )
    assert verify_res.status_code == 200
    reset_token = verify_res.json()["reset_token"]

    # 8c. Reset Password
    reset_res = await client.post(
        "/api/v1/auth/forgot-password/reset",
        json={
            "phone": reset_phone,
            "reset_token": reset_token,
            "new_password": "JordanBrandNewPassword@2026",
            "confirm_password": "JordanBrandNewPassword@2026",
        }
    )
    assert reset_res.status_code == 200

    # 8d. Login with new credentials
    new_vol_login = await client.post(
        "/api/v1/auth/login",
        json={
            "phone": reset_phone,
            "password": "JordanBrandNewPassword@2026",
            "intended_role": "VOLUNTEER",
        }
    )
    assert new_vol_login.status_code == 200

    print("\n--- 9. Testing Logout ---")
    logout_res = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {vol_token}"}
    )
    assert logout_res.status_code == 200
    print("\n=== ALL ACCEPTANCE CRITERIA PASSED SUCCESSFULLY ===")
