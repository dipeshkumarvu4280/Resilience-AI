import logging
import re
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.config import settings
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    generate_secure_otp,
    hash_otp,
    verify_otp_hash,
    create_password_reset_token,
    verify_password_reset_token,
)
from app.db.mongodb import get_database
from app.models.enums import UserRole
from app.models.user import (
    UserLogin,
    VolunteerRegister,
    GoogleAuthRequest,
    UserResponse,
    VolunteerProfile,
)
from app.models.auth import (
    Token,
    OTPRequest,
    OTPRequestResponse,
    OTPVerifyRequest,
    OTPVerifyResponse,
    PasswordResetRequest,
    PasswordResetResponse,
    GoogleAuthUrlResponse,
)
from app.services.google_oauth import google_oauth_service
from app.api.deps import get_current_user

logger = logging.getLogger("resilience.auth")
router = APIRouter()


@router.post("/login", response_model=Token)
async def login(
    payload: UserLogin,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    phone = payload.phone.strip()
    user_doc = await db["users"].find_one({"phone": phone})
    
    if not user_doc or not verify_password(payload.password, user_doc.get("hashed_password", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone number or password. Verification failed.",
        )
    
    if not user_doc.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact system control administrator.",
        )
        
    actual_role = UserRole(user_doc["role"])
    
    # If the user attempted to log in via a specific operational portal, verify authorization
    if payload.intended_role:
        if actual_role != payload.intended_role and actual_role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unauthorized portal entry: Your account role ({actual_role.value}) cannot access the {payload.intended_role.value} operations console.",
            )
            
    # Update last login timestamp
    now = datetime.now(timezone.utc)
    await db["users"].update_one({"_id": user_doc["_id"]}, {"$set": {"last_login": now}})
    
    # Record audit log
    await db["auth_audit_logs"].insert_one({
        "phone": phone,
        "event": "LOGIN_SUCCESS",
        "role": actual_role.value,
        "timestamp": now,
    })
    
    access_token = create_access_token(
        data={"sub": phone, "role": actual_role.value}
    )
    
    vol_prof = None
    if user_doc.get("volunteer_profile"):
        vol_prof = VolunteerProfile(**user_doc["volunteer_profile"])
        
    user_response = UserResponse(
        id=str(user_doc["_id"]),
        phone=user_doc["phone"],
        full_name=user_doc["full_name"],
        email=user_doc.get("email"),
        role=actual_role,
        is_active=user_doc.get("is_active", True),
        badge_number=user_doc.get("badge_number"),
        department_or_agency=user_doc.get("department_or_agency"),
        created_at=user_doc.get("created_at", now),
        volunteer_profile=vol_prof,
        google_sub=user_doc.get("google_sub"),
    )
    
    return Token(access_token=access_token, token_type="bearer", user=user_response)


@router.post("/register-volunteer", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register_volunteer(
    payload: VolunteerRegister,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    phone = payload.phone.strip()
    existing = await db["users"].find_one({"phone": phone})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this phone number is already registered in the RESILIENCE network.",
        )
        
    now = datetime.now(timezone.utc)
    vol_profile = VolunteerProfile(
        skills=payload.skills,
        availability=payload.availability,
        zone_or_district=payload.zone_or_district,
    )
    
    new_user = {
        "phone": phone,
        "full_name": payload.full_name.strip(),
        "email": None,
        "role": UserRole.VOLUNTEER.value,
        "is_active": True,
        "hashed_password": get_password_hash(payload.password),
        "volunteer_profile": vol_profile.model_dump(),
        "auth_provider": "local",
        "created_at": now,
        "updated_at": now,
        "last_login": now,
    }
    
    result = await db["users"].insert_one(new_user)
    new_user["_id"] = result.inserted_id
    
    # Audit log
    await db["auth_audit_logs"].insert_one({
        "phone": phone,
        "event": "VOLUNTEER_REGISTERED",
        "role": UserRole.VOLUNTEER.value,
        "timestamp": now,
    })
    
    access_token = create_access_token(
        data={"sub": phone, "role": UserRole.VOLUNTEER.value}
    )
    
    user_response = UserResponse(
        id=str(new_user["_id"]),
        phone=phone,
        full_name=payload.full_name.strip(),
        email=None,
        role=UserRole.VOLUNTEER,
        is_active=True,
        badge_number=None,
        department_or_agency="Community Volunteer Network",
        created_at=now,
        volunteer_profile=vol_profile,
        google_sub=None,
    )
    
    return Token(access_token=access_token, token_type="bearer", user=user_response)


async def process_google_auth_identity(
    verified_identity: dict,
    intended_role: Optional[UserRole],
    db: AsyncIOMotorDatabase,
) -> Token:
    sub = verified_identity.get("sub")
    email = verified_identity.get("email", "").lower().strip()
    name = verified_identity.get("name", "Verified Google User").strip()

    if not sub or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incomplete Google identity verification: Missing sub or email.",
        )

    now = datetime.now(timezone.utc)

    # Check if user already exists in DB by immutable google_sub or pre-authorized email (case-insensitive)
    user_doc = await db["users"].find_one({
        "$or": [
            {"google_sub": sub},
            {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
        ]
    })

    if user_doc:
        existing_sub = user_doc.get("google_sub")
        # google_sub mismatch protection: do not allow account hijacking
        if existing_sub and existing_sub != sub:
            await db["auth_audit_logs"].insert_one({
                "phone": user_doc["phone"],
                "email": email,
                "google_sub": sub,
                "existing_sub": existing_sub,
                "event": "GOOGLE_LOGIN_SUB_MISMATCH",
                "role": user_doc.get("role"),
                "timestamp": now,
            })
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security Policy Violation: Account is already securely linked to a different Google identity. Contact a system administrator.",
            )

        if not user_doc.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated. Contact system control administrator.",
            )

        actual_role = UserRole(user_doc["role"])

        # Enforce RBAC portal check if an intended role was specified
        if intended_role:
            if actual_role != intended_role and actual_role != UserRole.ADMIN:
                await db["auth_audit_logs"].insert_one({
                    "phone": user_doc["phone"],
                    "email": email,
                    "google_sub": sub,
                    "event": "GOOGLE_LOGIN_AUTHENTICATED_NOT_AUTHORIZED",
                    "role": actual_role.value,
                    "intended_role": intended_role.value,
                    "timestamp": now,
                })
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Your Google account is authenticated, but it is provisioned as '{actual_role.value}', not '{intended_role.value}'. Please sign in through the appropriate portal.",
                )

        # Securely link google_sub to pre-provisioned user on first Google login
        is_first_link = not existing_sub
        update_fields = {
            "last_login": now,
            "updated_at": now,
        }
        if name and name.strip() and name.strip() != "Verified Google User":
            update_fields["full_name"] = name.strip()
            user_doc["full_name"] = name.strip()

        if is_first_link:
            update_fields["google_sub"] = sub
            update_fields["auth_provider"] = "google"
            await db["auth_audit_logs"].insert_one({
                "phone": user_doc["phone"],
                "email": email,
                "google_sub": sub,
                "event": "GOOGLE_IDENTITY_LINKED",
                "role": actual_role.value,
                "timestamp": now,
            })

        await db["users"].update_one(
            {"_id": user_doc["_id"]},
            {"$set": update_fields}
        )
    else:
        # User is not pre-provisioned in database
        # Privileged roles (ADMIN, EMERGENCY_OFFICER, RESOURCE_MANAGER) are STRICTLY REJECTED
        if intended_role in [UserRole.EMERGENCY_OFFICER, UserRole.RESOURCE_MANAGER, UserRole.ADMIN]:
            role_label = intended_role.value.replace("_", " ").title()
            event_name = (
                "GOOGLE_RESOURCE_MANAGER_UNAUTHORIZED"
                if intended_role == UserRole.RESOURCE_MANAGER
                else "GOOGLE_LOGIN_AUTHENTICATED_NOT_AUTHORIZED"
            )
            await db["auth_audit_logs"].insert_one({
                "email": email,
                "google_sub": sub,
                "event": event_name,
                "intended_role": intended_role.value,
                "timestamp": now,
            })
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Security Policy Violation: Your Google account is authenticated, but it is not pre-provisioned or authorized for the {role_label} role. Official roles require prior administrative authorization.",
            )

        # Create genuine volunteer account with verified Google identity
        phone_fallback = f"G-{hash_otp(email)[:10]}"
        existing_phone = await db["users"].find_one({"phone": phone_fallback})
        if existing_phone:
            phone_fallback = f"G-{hash_otp(sub)[:10]}"

        vol_profile = VolunteerProfile(
            skills=["General Community Support"],
            availability="Available Immediately",
        )
        new_user = {
            "phone": phone_fallback,
            "full_name": name,
            "email": email,
            "google_sub": sub,
            "role": UserRole.VOLUNTEER.value,
            "is_active": True,
            "hashed_password": get_password_hash("GOOGLE_OAUTH_ACCOUNT_NO_LOCAL_PASSWORD"),
            "volunteer_profile": vol_profile.model_dump(),
            "auth_provider": "google",
            "created_at": now,
            "updated_at": now,
            "last_login": now,
        }
        res = await db["users"].insert_one(new_user)
        user_doc = new_user
        user_doc["_id"] = res.inserted_id
        actual_role = UserRole.VOLUNTEER

    # Record security audit log
    event_name = (
        "GOOGLE_RESOURCE_MANAGER_AUTHORIZED"
        if actual_role == UserRole.RESOURCE_MANAGER
        else "GOOGLE_LOGIN_SUCCESS"
    )
    await db["auth_audit_logs"].insert_one({
        "phone": user_doc["phone"],
        "email": email,
        "google_sub": sub,
        "event": event_name,
        "role": actual_role.value,
        "timestamp": now,
    })

    access_token = create_access_token(
        data={"sub": user_doc["phone"], "role": actual_role.value}
    )

    vol_prof = None
    if user_doc.get("volunteer_profile"):
        vol_prof = VolunteerProfile(**user_doc["volunteer_profile"])

    user_response = UserResponse(
        id=str(user_doc["_id"]),
        phone=user_doc["phone"],
        full_name=user_doc["full_name"],
        email=user_doc.get("email"),
        role=actual_role,
        is_active=user_doc.get("is_active", True),
        badge_number=user_doc.get("badge_number"),
        department_or_agency=user_doc.get("department_or_agency"),
        created_at=user_doc.get("created_at", now),
        volunteer_profile=vol_prof,
        google_sub=user_doc.get("google_sub") or sub,
    )

    return Token(access_token=access_token, token_type="bearer", user=user_response)


@router.get("/google/url", response_model=GoogleAuthUrlResponse)
async def get_google_auth_url(
    intended_role: Optional[UserRole] = None,
    redirect_uri: Optional[str] = None,
    state: Optional[str] = None,
):
    """
    Generate Google OAuth 2.0 / OpenID Connect authorization URL.
    Returns 503 if Google OAuth is not configured in this environment.
    """
    if not google_oauth_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured for this environment.",
        )
    try:
        url = google_oauth_service.generate_authorization_url(
            intended_role=intended_role.value if intended_role else "VOLUNTEER",
            redirect_uri=redirect_uri,
            state=state,
        )
        return GoogleAuthUrlResponse(
            auth_url=url,
            client_id=settings.GOOGLE_CLIENT_ID,
            redirect_uri=redirect_uri or settings.GOOGLE_REDIRECT_URI,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/google/callback", response_model=Token)
@router.post("/google", response_model=Token)
async def google_auth_callback(
    payload: GoogleAuthRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Google OAuth 2.0 / OpenID Connect Authentication Endpoint:
    Accepts authorization code or verified ID token.
    Enforces server-side verification and strict RBAC.
    """
    parsed_role = payload.intended_role
    if not parsed_role and payload.state:
        state_data = google_oauth_service.parse_state(payload.state)
        if "intended_role" in state_data:
            try:
                parsed_role = UserRole(state_data["intended_role"])
            except Exception:
                pass

    id_token_to_verify = payload.id_token or payload.token

    # 1. Exchange authorization code if provided
    if payload.code:
        try:
            tokens = await google_oauth_service.exchange_code_for_tokens(
                code=payload.code,
                redirect_uri=payload.redirect_uri
            )
            id_token_to_verify = tokens.get("id_token")
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Google authentication exchange failed: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Error during Google OAuth exchange: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Unable to complete Google sign-in. Please try again."
            )

    if not id_token_to_verify:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google authentication token or authorization code is required."
        )

    # 2. Cryptographic/Server-side verification of Google ID token
    try:
        verified_identity = await google_oauth_service.verify_id_token(id_token_to_verify)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Google authentication could not be verified: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error verifying Google ID token: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to complete Google sign-in. Please try again."
        )

    # 3. Role authorization and session token generation
    return await process_google_auth_identity(
        verified_identity=verified_identity,
        intended_role=parsed_role,
        db=db
    )


@router.post("/forgot-password/request-otp", response_model=OTPRequestResponse)
async def request_otp(
    payload: OTPRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    phone = payload.phone.strip()
    user_doc = await db["users"].find_one({"phone": phone})
    
    # Generic security response even if user doesn't exist, preventing user enumeration
    if not user_doc:
        return OTPRequestResponse(
            message="If an account is associated with this phone number, a verification code has been processed.",
            phone=phone,
            expires_in_seconds=settings.OTP_EXPIRE_MINUTES * 60,
            simulated_mode=settings.SIMULATED_OTP_MODE,
            demo_otp=None,
            cooldown_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS,
        )
        
    # Rate-limiting check: count OTP requests in the last 15 minutes
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=15)
    recent_requests = await db["otps"].count_documents({
        "phone": phone,
        "created_at": {"$gte": window_start}
    })
    
    if recent_requests >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Too many OTP requests. Please wait 15 minutes before trying again.",
        )
        
    # Invalidate any previously active OTPs for this phone (single-use / supersession)
    await db["otps"].update_many(
        {"phone": phone, "is_used": False},
        {"$set": {"is_used": True, "invalidated_reason": "SUPERSEDED"}}
    )
    
    raw_otp = generate_secure_otp()
    hashed = hash_otp(raw_otp)
    expires_at = now + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    
    await db["otps"].insert_one({
        "phone": phone,
        "hashed_otp": hashed,
        "attempts": 0,
        "is_used": False,
        "purpose": "FORGOT_PASSWORD",
        "created_at": now,
        "expires_at": expires_at,
    })
    
    if settings.SIMULATED_OTP_MODE:
        # Prototype/demo mode: return demo OTP directly in response payload with clear non-production indicators
        return OTPRequestResponse(
            message="Prototype verification code generated (Demo mode — no SMS/email sent).",
            phone=phone,
            expires_in_seconds=settings.OTP_EXPIRE_MINUTES * 60,
            simulated_mode=True,
            demo_otp=raw_otp,
            cooldown_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS,
        )
    else:
        # Production mode: external messaging gateway would dispatch; OTP is never returned to frontend
        logger.info(f"[SECURE DISPATCH] Verification OTP for {phone[:4]}***{phone[-2:]} generated. Expiry: 5m.")
        return OTPRequestResponse(
            message="Verification code dispatched securely to your registered phone.",
            phone=phone,
            expires_in_seconds=settings.OTP_EXPIRE_MINUTES * 60,
            simulated_mode=False,
            demo_otp=None,
            cooldown_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS,
        )


@router.post("/forgot-password/verify-otp", response_model=OTPVerifyResponse)
async def verify_otp(
    payload: OTPVerifyRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    phone = payload.phone.strip()
    now = datetime.now(timezone.utc)
    
    otp_record = await db["otps"].find_one({
        "phone": phone,
        "is_used": False,
        "expires_at": {"$gt": now}
    }, sort=[("created_at", -1)])
    
    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code. Please request a new code.",
        )
        
    # Check attempt limit
    if otp_record.get("attempts", 0) >= settings.MAX_OTP_ATTEMPTS:
        await db["otps"].update_one(
            {"_id": otp_record["_id"]},
            {"$set": {"is_used": True, "invalidated_reason": "MAX_ATTEMPTS_EXCEEDED"}}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum verification attempts (5) exceeded. This verification code has been invalidated. Please request a new code.",
        )
        
    is_valid = verify_otp_hash(payload.otp.strip(), otp_record["hashed_otp"])
    if not is_valid:
        await db["otps"].update_one(
            {"_id": otp_record["_id"]},
            {"$inc": {"attempts": 1}}
        )
        current_attempts = otp_record.get("attempts", 0) + 1
        if current_attempts >= settings.MAX_OTP_ATTEMPTS:
            await db["otps"].update_one(
                {"_id": otp_record["_id"]},
                {"$set": {"is_used": True, "invalidated_reason": "MAX_ATTEMPTS_EXCEEDED"}}
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum verification attempts (5) exceeded. This verification code has been invalidated. Please request a new code.",
            )
        
        remaining = settings.MAX_OTP_ATTEMPTS - current_attempts
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Incorrect verification code. {remaining} attempt(s) remaining.",
        )
        
    # Mark OTP as successfully used immediately (single-use)
    await db["otps"].update_one(
        {"_id": otp_record["_id"]},
        {"$set": {"is_used": True, "verified_at": now, "invalidated_reason": "VERIFIED"}}
    )
    
    reset_token = create_password_reset_token(phone)
    
    return OTPVerifyResponse(
        message="Verification successful. You may now reset your password.",
        phone=phone,
        reset_token=reset_token,
        expires_in_seconds=600,
    )


@router.post("/forgot-password/reset", response_model=PasswordResetResponse)
async def reset_password(
    payload: PasswordResetRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    phone = payload.phone.strip()
    
    if not verify_password_reset_token(payload.reset_token, phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token. Please restart verification.",
        )
        
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation password do not match.",
        )
        
    if len(payload.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters in length.",
        )
        
    user_doc = await db["users"].find_one({"phone": phone})
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Operational user account not found.",
        )
        
    new_hashed = get_password_hash(payload.new_password)
    now = datetime.now(timezone.utc)
    
    await db["users"].update_one(
        {"_id": user_doc["_id"]},
        {"$set": {"hashed_password": new_hashed, "updated_at": now}}
    )
    
    # Invalidate any remaining OTP records for this phone
    await db["otps"].update_many(
        {"phone": phone, "is_used": False},
        {"$set": {"is_used": True, "invalidated_reason": "PASSWORD_RESET_COMPLETED"}}
    )
    
    # Audit log
    await db["auth_audit_logs"].insert_one({
        "phone": phone,
        "event": "PASSWORD_RESET_SUCCESS",
        "timestamp": now,
    })
    
    return PasswordResetResponse()


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserResponse = Depends(get_current_user)):
    return current_user


@router.post("/logout")
async def logout(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    now = datetime.now(timezone.utc)
    await db["auth_audit_logs"].insert_one({
        "phone": current_user.phone,
        "event": "LOGOUT",
        "timestamp": now,
    })
    return {"message": "Operational session terminated successfully."}
