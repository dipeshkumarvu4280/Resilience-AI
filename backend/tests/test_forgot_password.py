import pytest
import uuid
from httpx import AsyncClient
from app.db.mongodb import get_database


@pytest.mark.anyio
async def test_forgot_password_full_flow(client: AsyncClient):
    # First create a test user
    unique_phone = f"977{uuid.uuid4().int % 10000000:07d}"
    reg_res = await client.post(
        "/api/v1/auth/register-volunteer",
        json={
            "full_name": "Test User",
            "phone": unique_phone,
            "password": "OldPassword@123",
            "skills": ["First Aid & CPR"],
            "availability": "Available Immediately",
        },
    )
    assert reg_res.status_code == 201

    # Step 1: Request OTP
    otp_req = await client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"phone": unique_phone}
    )
    assert otp_req.status_code == 200
    assert "Verification code dispatched" in otp_req.json()["message"]
    # Ensure raw OTP is NOT in the response
    assert "otp" not in otp_req.json()

    # Retrieve raw OTP hash from DB for testing verification
    db = get_database()
    otp_doc = await db["otps"].find_one({"phone": unique_phone, "is_used": False})
    assert otp_doc is not None

    # Step 2: Test wrong OTP rejection
    wrong_verify = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"phone": unique_phone, "otp": "000000"}
    )
    assert wrong_verify.status_code == 400

    # Step 3: Now verify with matching OTP by re-fetching the updated doc
    from app.core.security import hash_otp
    # Update doc with a known test OTP hash
    test_otp = "852963"
    await db["otps"].update_one(
        {"_id": otp_doc["_id"]},
        {"$set": {"hashed_otp": hash_otp(test_otp)}}
    )

    verify_res = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"phone": unique_phone, "otp": test_otp}
    )
    assert verify_res.status_code == 200
    reset_token = verify_res.json()["reset_token"]
    assert reset_token is not None

    # Step 4: Reset password with new password
    reset_res = await client.post(
        "/api/v1/auth/forgot-password/reset",
        json={
            "phone": unique_phone,
            "reset_token": reset_token,
            "new_password": "NewSecurePassword@2026",
            "confirm_password": "NewSecurePassword@2026",
        }
    )
    assert reset_res.status_code == 200
    assert "Password reset successfully" in reset_res.json()["message"]

    # Step 5: Test login with new password
    new_login = await client.post(
        "/api/v1/auth/login",
        json={"phone": unique_phone, "password": "NewSecurePassword@2026"}
    )
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()
