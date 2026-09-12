from typing import List, Optional
from bson import ObjectId
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.api.deps import require_admin, get_current_user
from app.db.mongodb import get_database
from app.models.enums import UserRole
from app.models.user import UserResponse, VolunteerProfile, UserCreate, UserProfileUpdate, UserPhoneUpdateRequest
from app.core.security import get_password_hash
from app.services.notification.sms_provider import normalize_phone_e164

router = APIRouter()


@router.get("", response_model=List[UserResponse])
async def list_users(
    role: Optional[UserRole] = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_admin: UserResponse = Depends(require_admin)
):
    """
    List actual authorized platform operators and registered volunteers.
    Only authorized system administrators can call this endpoint.
    """
    query = {}
    if role:
        query["role"] = role.value
        
    cursor = db["users"].find(query).sort("created_at", -1).limit(limit)
    users = []
    
    async for doc in cursor:
        vol_prof = None
        if doc.get("volunteer_profile"):
            vol_prof = VolunteerProfile(**doc["volunteer_profile"])
            
        users.append(UserResponse(
            id=str(doc["_id"]),
            phone=doc["phone"],
            full_name=doc["full_name"],
            email=doc.get("email"),
            role=UserRole(doc["role"]),
            is_active=doc.get("is_active", True),
            badge_number=doc.get("badge_number"),
            department_or_agency=doc.get("department_or_agency"),
            created_at=doc.get("created_at", datetime.now(timezone.utc)),
            volunteer_profile=vol_prof,
            google_sub=doc.get("google_sub"),
        ))
        
    return users


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def provision_user(
    payload: UserCreate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_admin: UserResponse = Depends(require_admin)
):
    """
    Provision a new authorized operational user (Emergency Officer, Resource Manager, Admin).
    """
    phone = payload.phone.strip()
    existing = await db["users"].find_one({"phone": phone})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An operator with this phone number already exists."
        )
        
    now = datetime.now(timezone.utc)
    new_user = {
        "phone": phone,
        "full_name": payload.full_name.strip(),
        "email": payload.email.strip().lower() if payload.email else None,
        "role": payload.role.value,
        "is_active": payload.is_active,
        "badge_number": payload.badge_number,
        "department_or_agency": payload.department_or_agency,
        "google_sub": payload.google_sub,
        "hashed_password": get_password_hash(payload.password),
        "volunteer_profile": payload.volunteer_profile.model_dump() if payload.volunteer_profile else None,
        "auth_provider": "local" if not payload.google_sub else "google",
        "created_at": now,
        "updated_at": now,
    }
    
    res = await db["users"].insert_one(new_user)
    new_user["_id"] = res.inserted_id
    
    return UserResponse(
        id=str(new_user["_id"]),
        phone=new_user["phone"],
        full_name=new_user["full_name"],
        email=new_user["email"],
        role=payload.role,
        is_active=new_user["is_active"],
        badge_number=new_user["badge_number"],
        department_or_agency=new_user["department_or_agency"],
        created_at=now,
        volunteer_profile=payload.volunteer_profile,
        google_sub=new_user.get("google_sub"),
    )


@router.patch("/me/profile", response_model=UserResponse)
async def update_my_profile(
    payload: UserProfileUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(get_current_user),
):
    """
    Update own profile attributes (volunteer skills, availability status, zone, phone, email, etc.).
    """
    try:
        obj_id = ObjectId(current_user.id)
        query = {"_id": obj_id}
    except Exception:
        query = {"phone": current_user.phone}

    user_doc = await db["users"].find_one(query)
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account record not found.",
        )

    now = datetime.now(timezone.utc)
    update_data = {"updated_at": now}

    if payload.full_name is not None and payload.full_name.strip():
        update_data["full_name"] = payload.full_name.strip()
    if payload.phone is not None and payload.phone.strip():
        update_data["phone"] = payload.phone.strip()
    if payload.email is not None:
        update_data["email"] = payload.email.strip().lower() if payload.email.strip() else None
    if payload.department_or_agency is not None:
        update_data["department_or_agency"] = payload.department_or_agency.strip()
    if payload.badge_number is not None:
        update_data["badge_number"] = payload.badge_number.strip()
    if payload.volunteer_profile is not None:
        update_data["volunteer_profile"] = payload.volunteer_profile.model_dump()

    await db["users"].update_one(query, {"$set": update_data})

    # Record audit log
    await db["audit_logs"].insert_one({
        "event_id": f"EVT-PROF-{current_user.id[-8:]}",
        "action": "USER_PROFILE_UPDATED",
        "actor_id": current_user.id,
        "actor_name": current_user.full_name,
        "actor_role": current_user.role.value,
        "target_user_id": current_user.id,
        "details": f"User '{current_user.full_name}' updated profile settings.",
        "timestamp": now,
    })

    updated_doc = await db["users"].find_one(query)
    vol_prof = None
    if updated_doc.get("volunteer_profile"):
        vol_prof = VolunteerProfile(**updated_doc["volunteer_profile"])

    return UserResponse(
        id=str(updated_doc["_id"]),
        phone=updated_doc["phone"],
        full_name=updated_doc["full_name"],
        email=updated_doc.get("email"),
        role=UserRole(updated_doc["role"]),
        is_active=updated_doc.get("is_active", True),
        badge_number=updated_doc.get("badge_number"),
        department_or_agency=updated_doc.get("department_or_agency"),
        created_at=updated_doc.get("created_at", now),
        volunteer_profile=vol_prof,
        google_sub=updated_doc.get("google_sub"),
    )


@router.get("/audit-logs", response_model=List[dict])
async def get_system_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    event_type: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_admin: UserResponse = Depends(require_admin),
):
    """
    Get comprehensive immutable system and security audit logs for Administrator.
    """
    query = {}
    if event_type and event_type.strip():
        query["$or"] = [
            {"action": {"$regex": event_type.strip(), "$options": "i"}},
            {"event": {"$regex": event_type.strip(), "$options": "i"}},
            {"event_type": {"$regex": event_type.strip(), "$options": "i"}},
        ]

    # Fetch from both audit_logs and auth_audit_logs
    audit_cursor = db["audit_logs"].find(query).sort("timestamp", -1).limit(limit)
    auth_cursor = db["auth_audit_logs"].find().sort("timestamp", -1).limit(limit)

    logs = []
    async for doc in audit_cursor:
        doc["_id"] = str(doc["_id"])
        doc["source"] = "operational_audit"
        logs.append(doc)

    async for doc in auth_cursor:
        doc["_id"] = str(doc["_id"])
        doc["source"] = "security_auth"
        if "action" not in doc and "event" in doc:
            doc["action"] = doc["event"]
        if "details" not in doc:
            doc["details"] = f"Auth event: {doc.get('event')} for operator {doc.get('operator_phone') or doc.get('phone')} (Admin: {doc.get('admin_phone', 'Self')})"
        logs.append(doc)

    # Sort merged list by timestamp descending
    logs.sort(key=lambda x: x.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return logs[:limit]


@router.patch("/{user_id}/provision-google", response_model=UserResponse)
async def provision_operator_google_identity(
    user_id: str,
    google_email: str = Query(..., description="Authorized Google email address"),
    google_sub: Optional[str] = Query(None, description="Optional immutable Google subject identifier"),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_admin: UserResponse = Depends(require_admin)
):
    """
    Securely associate an authorized Google email/sub with an existing official operator.
    Only authorized system administrators can call this endpoint.
    """
    clean_email = google_email.strip().lower()
    if "@" not in clean_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid Google identity email address is required.",
        )

    try:
        obj_id = ObjectId(user_id)
        query = {"_id": obj_id}
    except Exception:
        query = {"phone": user_id}

    user_doc = await db["users"].find_one(query)
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Operator user record not found.",
        )

    now = datetime.now(timezone.utc)
    update_data = {
        "email": clean_email,
        "updated_at": now,
    }
    if google_sub:
        update_data["google_sub"] = google_sub.strip()
        update_data["auth_provider"] = "google"
    elif user_doc.get("email") != clean_email:
        # If email was updated without a specific sub, reset google_sub to allow initial Google OAuth linking
        update_data["google_sub"] = None

    await db["users"].update_one({"_id": user_doc["_id"]}, {"$set": update_data})
    
    # Audit log
    await db["auth_audit_logs"].insert_one({
        "admin_phone": current_admin.phone,
        "operator_phone": user_doc["phone"],
        "provisioned_email": clean_email,
        "event": "OPERATOR_GOOGLE_PROVISIONED",
        "role": user_doc.get("role"),
        "timestamp": now,
    })
    
    updated_doc = await db["users"].find_one({"_id": user_doc["_id"]})

    vol_prof = None
    if updated_doc.get("volunteer_profile"):
        vol_prof = VolunteerProfile(**updated_doc["volunteer_profile"])

    return UserResponse(
        id=str(updated_doc["_id"]),
        phone=updated_doc["phone"],
        full_name=updated_doc["full_name"],
        email=updated_doc.get("email"),
        role=UserRole(updated_doc["role"]),
        is_active=updated_doc.get("is_active", True),
        badge_number=updated_doc.get("badge_number"),
        department_or_agency=updated_doc.get("department_or_agency"),
        created_at=updated_doc.get("created_at", now),
        volunteer_profile=vol_prof,
        google_sub=updated_doc.get("google_sub"),
    )


@router.patch("/{user_id}", response_model=UserResponse, summary="Admin Update User Phone")
@router.patch("/{user_id}/phone", response_model=UserResponse, summary="Admin Update User Phone (Alias)")
async def update_user_phone_by_admin(
    user_id: str,
    payload: UserPhoneUpdateRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_admin: UserResponse = Depends(require_admin),
):
    """
    Admin-only endpoint to update an existing Emergency Officer or operator's real phone number.
    Normalizes phone to E.164 format (+<country_code><national_number>).
    Synchronizes with notification preferences if present and records an immutable audit log entry.
    Does not allow modifying role, password, permissions, or arbitrary fields.
    """
    raw_phone = payload.phone.strip() if payload.phone else ""
    if not raw_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number cannot be empty.",
        )

    norm_phone = normalize_phone_e164(raw_phone)
    if not norm_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid phone number format: '{raw_phone}'. Must normalize to valid E.164 format (+<country_code><digits>).",
        )

    try:
        obj_id = ObjectId(user_id)
        query = {"_id": obj_id}
    except Exception:
        query = {"$or": [{"user_id": user_id}, {"phone": user_id}]}

    user_doc = await db["users"].find_one(query)
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User record '{user_id}' not found.",
        )

    # Check if another user already has this phone number
    existing_phone_user = await db["users"].find_one({
        "phone": norm_phone,
        "_id": {"$ne": user_doc["_id"]},
    })
    if existing_phone_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Phone number '{norm_phone}' is already registered to another user ({existing_phone_user.get('full_name')}).",
        )

    prev_phone = user_doc.get("phone")
    now = datetime.now(timezone.utc)
    uid_str = str(user_doc["_id"])

    # 1. Update canonical user document in MongoDB users collection
    await db["users"].update_one(
        {"_id": user_doc["_id"]},
        {"$set": {"phone": norm_phone, "updated_at": now}},
    )

    # 2. Synchronize notification preferences if record exists
    await db["notification_preferences"].update_many(
        {"user_id": {"$in": [uid_str, prev_phone]}},
        {"$set": {"phone_number": norm_phone, "updated_at": now}},
    )

    # 3. Create immutable audit log record
    audit_doc = {
        "event_id": f"EVT-PHONE-{uid_str[-8:]}",
        "action": "ADMIN_OFFICER_PHONE_UPDATED",
        "actor_id": current_admin.id,
        "actor_name": current_admin.full_name,
        "actor_role": current_admin.role.value,
        "target_user_id": uid_str,
        "target_user_name": user_doc.get("full_name"),
        "target_user_role": user_doc.get("role"),
        "previous_phone": prev_phone,
        "new_phone": norm_phone,
        "details": f"Admin '{current_admin.full_name}' updated phone number for {user_doc.get('role')} '{user_doc.get('full_name')}' from {prev_phone} to {norm_phone}.",
        "timestamp": now,
        "status": "SUCCESS",
    }
    await db["audit_logs"].insert_one(audit_doc)

    updated_doc = await db["users"].find_one({"_id": user_doc["_id"]})

    vol_prof = None
    if updated_doc.get("volunteer_profile"):
        vol_prof = VolunteerProfile(**updated_doc["volunteer_profile"])

    return UserResponse(
        id=str(updated_doc["_id"]),
        phone=updated_doc["phone"],
        full_name=updated_doc["full_name"],
        email=updated_doc.get("email"),
        role=UserRole(updated_doc["role"]),
        is_active=updated_doc.get("is_active", True),
        badge_number=updated_doc.get("badge_number"),
        department_or_agency=updated_doc.get("department_or_agency"),
        created_at=updated_doc.get("created_at", now),
        volunteer_profile=vol_prof,
        google_sub=updated_doc.get("google_sub"),
    )
