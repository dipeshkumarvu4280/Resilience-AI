import pytest
import uuid
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from app.db.mongodb import get_database
from app.core.config import settings
from app.core.security import verify_password, get_password_hash


@pytest.mark.anyio
async def test_emergency_officer_simulated_otp_forgot_password(client: AsyncClient):
    """Verify complete simulated OTP forgot-password recovery for EMERGENCY_OFFICER role."""
    officer_phone = "9999999002"
    
    # A. Request simulated OTP
    req_res = await client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"phone": officer_phone}
    )
    assert req_res.status_code == 200
    data = req_res.json()
    assert data["simulated_mode"] is True
    assert data["demo_otp"] is not None
    assert len(data["demo_otp"]) == 6
    assert data["demo_otp"].isdigit()
    assert "Demo mode" in data["message"]
    demo_otp = data["demo_otp"]

    # B. Wrong OTP rejection
    wrong_res = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"phone": officer_phone, "otp": "999999" if demo_otp != "999999" else "000000"}
    )
    assert wrong_res.status_code == 400
    assert "attempt(s) remaining" in wrong_res.json()["detail"]

    # C. Correct OTP verification
    verify_res = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"phone": officer_phone, "otp": demo_otp}
    )
    assert verify_res.status_code == 200
    reset_token = verify_res.json()["reset_token"]
    assert reset_token is not None

    # D. Password Reset
    new_password = "NewOfficerSecurePassword@2026"
    reset_res = await client.post(
        "/api/v1/auth/forgot-password/reset",
        json={
            "phone": officer_phone,
            "reset_token": reset_token,
            "new_password": new_password,
            "confirm_password": new_password,
        }
    )
    assert reset_res.status_code == 200
    assert "Password reset successfully" in reset_res.json()["message"]

    # E. Old password fails login
    old_login = await client.post(
        "/api/v1/auth/login",
        json={"phone": officer_phone, "password": "OfficerPassword@2026", "intended_role": "EMERGENCY_OFFICER"}
    )
    assert old_login.status_code == 401

    # F. New password succeeds login
    new_login = await client.post(
        "/api/v1/auth/login",
        json={"phone": officer_phone, "password": new_password, "intended_role": "EMERGENCY_OFFICER"}
    )
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()
    assert new_login.json()["user"]["role"] == "EMERGENCY_OFFICER"


@pytest.mark.anyio
async def test_resource_manager_simulated_otp_forgot_password(client: AsyncClient):
    """Verify complete simulated OTP forgot-password recovery for RESOURCE_MANAGER role."""
    rm_phone = "9999999003"
    
    # 1. Request OTP
    req_res = await client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"phone": rm_phone}
    )
    assert req_res.status_code == 200
    demo_otp = req_res.json()["demo_otp"]
    assert demo_otp is not None
    assert len(demo_otp) == 6

    # 2. Verify OTP
    verify_res = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"phone": rm_phone, "otp": demo_otp}
    )
    assert verify_res.status_code == 200
    reset_token = verify_res.json()["reset_token"]

    # 3. Reset password
    new_password = "NewResourceSecurePassword@2026"
    reset_res = await client.post(
        "/api/v1/auth/forgot-password/reset",
        json={
            "phone": rm_phone,
            "reset_token": reset_token,
            "new_password": new_password,
            "confirm_password": new_password,
        }
    )
    assert reset_res.status_code == 200

    # 4. Old password rejected
    old_login = await client.post(
        "/api/v1/auth/login",
        json={"phone": rm_phone, "password": "ResourcePassword@2026", "intended_role": "RESOURCE_MANAGER"}
    )
    assert old_login.status_code == 401

    # 5. New password accepted
    new_login = await client.post(
        "/api/v1/auth/login",
        json={"phone": rm_phone, "password": new_password, "intended_role": "RESOURCE_MANAGER"}
    )
    assert new_login.status_code == 200
    assert new_login.json()["user"]["role"] == "RESOURCE_MANAGER"


@pytest.mark.anyio
async def test_admin_simulated_otp_forgot_password(client: AsyncClient):
    """Verify complete simulated OTP forgot-password recovery for ADMIN role."""
    admin_phone = "9999999001"
    
    # 1. Request OTP
    req_res = await client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"phone": admin_phone}
    )
    assert req_res.status_code == 200
    demo_otp = req_res.json()["demo_otp"]
    assert demo_otp is not None

    # 2. Verify OTP
    verify_res = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"phone": admin_phone, "otp": demo_otp}
    )
    assert verify_res.status_code == 200
    reset_token = verify_res.json()["reset_token"]

    # 3. Reset password
    new_password = "NewAdminSecurePassword@2026"
    reset_res = await client.post(
        "/api/v1/auth/forgot-password/reset",
        json={
            "phone": admin_phone,
            "reset_token": reset_token,
            "new_password": new_password,
            "confirm_password": new_password,
        }
    )
    assert reset_res.status_code == 200

    # 4. Old password rejected
    old_login = await client.post(
        "/api/v1/auth/login",
        json={"phone": admin_phone, "password": "AdminPassword@2026", "intended_role": "ADMIN"}
    )
    assert old_login.status_code == 401

    # 5. New password accepted
    new_login = await client.post(
        "/api/v1/auth/login",
        json={"phone": admin_phone, "password": new_password, "intended_role": "ADMIN"}
    )
    assert new_login.status_code == 200
    assert new_login.json()["user"]["role"] == "ADMIN"


@pytest.mark.anyio
async def test_otp_cryptographic_randomness_no_hardcoded_values(client: AsyncClient):
    """Verify that every OTP generated is cryptographically random and not static."""
    test_phone = "9999999001"
    otps = set()
    
    # Request 3 fresh OTPs (below the 5 req limit)
    for _ in range(3):
        res = await client.post(
            "/api/v1/auth/forgot-password/request-otp",
            json={"phone": test_phone}
        )
        assert res.status_code == 200
        otp = res.json()["demo_otp"]
        assert len(otp) == 6
        assert otp not in ["123456", "111111", "000000", "654321"]
        otps.add(otp)
        
    # Verify we got unique randomized codes
    assert len(otps) == 3


@pytest.mark.anyio
async def test_simulated_mode_flag_suppresses_demo_otp_in_production(client: AsyncClient):
    """Verify that if SIMULATED_OTP_MODE is disabled, demo_otp is strictly omitted."""
    test_phone = "9999999002"
    
    # Temporarily toggle simulated mode off
    original_setting = settings.SIMULATED_OTP_MODE
    try:
        settings.SIMULATED_OTP_MODE = False
        res = await client.post(
            "/api/v1/auth/forgot-password/request-otp",
            json={"phone": test_phone}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["simulated_mode"] is False
        assert data["demo_otp"] is None
        assert "Verification code dispatched securely" in data["message"]
    finally:
        settings.SIMULATED_OTP_MODE = original_setting


@pytest.mark.anyio
async def test_max_attempts_exceeded_invalidates_otp(client: AsyncClient):
    """Verify that 5 failed attempts invalidates the OTP and prevents further verification."""
    test_phone = "9999999002"
    
    req_res = await client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"phone": test_phone}
    )
    demo_otp = req_res.json()["demo_otp"]
    wrong_code = "000000" if demo_otp != "000000" else "111111"

    # Make 4 failed attempts
    for attempt in range(1, 5):
        fail_res = await client.post(
            "/api/v1/auth/forgot-password/verify-otp",
            json={"phone": test_phone, "otp": wrong_code}
        )
        assert fail_res.status_code == 400
        assert f"{5 - attempt} attempt(s) remaining" in fail_res.json()["detail"]

    # 5th failed attempt should trigger lockout message
    fifth_res = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"phone": test_phone, "otp": wrong_code}
    )
    assert fifth_res.status_code == 400
    assert "Maximum verification attempts (5) exceeded" in fifth_res.json()["detail"]

    # 6th attempt (even with CORRECT OTP) should be rejected because code is invalidated
    locked_res = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"phone": test_phone, "otp": demo_otp}
    )
    assert locked_res.status_code == 400
    assert "Invalid or expired" in locked_res.json()["detail"] or "Maximum verification attempts" in locked_res.json()["detail"]


@pytest.mark.anyio
async def test_expired_otp_rejection(client: AsyncClient):
    """Verify that an expired OTP is rejected."""
    test_phone = "9999999003"
    
    req_res = await client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"phone": test_phone}
    )
    demo_otp = req_res.json()["demo_otp"]

    # Artificially expire the OTP record in the DB
    db = get_database()
    past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    await db["otps"].update_many(
        {"phone": test_phone, "is_used": False},
        {"$set": {"expires_at": past_time}}
    )

    verify_res = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"phone": test_phone, "otp": demo_otp}
    )
    assert verify_res.status_code == 400
    assert "Invalid or expired" in verify_res.json()["detail"]


@pytest.mark.anyio
async def test_single_use_otp_cannot_be_reused(client: AsyncClient):
    """Verify that an OTP becomes immediately invalid after successful verification."""
    test_phone = "9999999001"
    
    req_res = await client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"phone": test_phone}
    )
    demo_otp = req_res.json()["demo_otp"]

    # First verification succeeds
    first_res = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"phone": test_phone, "otp": demo_otp}
    )
    assert first_res.status_code == 200

    # Second verification with same OTP fails
    second_res = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"phone": test_phone, "otp": demo_otp}
    )
    assert second_res.status_code == 400
    assert "Invalid or expired" in second_res.json()["detail"]


@pytest.mark.anyio
async def test_resend_invalidates_previous_otp(client: AsyncClient):
    """Verify that resending an OTP invalidates the earlier code and validates the new code."""
    test_phone = "9999999002"
    
    # Request first OTP
    first_req = await client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"phone": test_phone}
    )
    first_otp = first_req.json()["demo_otp"]

    # Resend (second OTP)
    second_req = await client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"phone": test_phone}
    )
    second_otp = second_req.json()["demo_otp"]

    # First OTP must be rejected
    first_verify = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"phone": test_phone, "otp": first_otp}
    )
    assert first_verify.status_code == 400

    # Second OTP must succeed
    second_verify = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"phone": test_phone, "otp": second_otp}
    )
    assert second_verify.status_code == 200


@pytest.mark.anyio
async def test_unknown_account_enumeration_protection(client: AsyncClient):
    """Verify that unknown accounts return generic response without leaking existence."""
    unregistered_phone = "9112223334"
    
    res = await client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"phone": unregistered_phone}
    )
    assert res.status_code == 200
    data = res.json()
    assert "verification code has been processed" in data["message"]
    # demo_otp is suppressed for unknown account to prevent enumeration
    assert data["demo_otp"] is None


@pytest.mark.anyio
async def test_password_reset_validation_rules(client: AsyncClient):
    """Verify validation rules: minimum length, confirmation mismatch, invalid reset token."""
    test_phone = "9999999003"
    
    # 1. Invalid reset token
    invalid_tok_res = await client.post(
        "/api/v1/auth/forgot-password/reset",
        json={
            "phone": test_phone,
            "reset_token": "invalid.jwt.token",
            "new_password": "ValidPassword@123",
            "confirm_password": "ValidPassword@123",
        }
    )
    assert invalid_tok_res.status_code == 400
    assert "Invalid or expired password reset token" in invalid_tok_res.json()["detail"]

    # Generate valid token
    req = await client.post("/api/v1/auth/forgot-password/request-otp", json={"phone": test_phone})
    ver = await client.post("/api/v1/auth/forgot-password/verify-otp", json={"phone": test_phone, "otp": req.json()["demo_otp"]})
    token = ver.json()["reset_token"]

    # 2. Mismatched passwords
    mismatch_res = await client.post(
        "/api/v1/auth/forgot-password/reset",
        json={
            "phone": test_phone,
            "reset_token": token,
            "new_password": "ValidPassword@123",
            "confirm_password": "DifferentPassword@123",
        }
    )
    assert mismatch_res.status_code == 400
    assert "do not match" in mismatch_res.json()["detail"]

    # 3. Short password (< 8 chars)
    short_res = await client.post(
        "/api/v1/auth/forgot-password/reset",
        json={
            "phone": test_phone,
            "reset_token": token,
            "new_password": "short",
            "confirm_password": "short",
        }
    )
    assert short_res.status_code == 422 or short_res.status_code == 400
