from datetime import datetime, timezone
from typing import List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.security import decode_access_token
from app.db.mongodb import get_database
from app.models.enums import UserRole
from app.models.user import UserResponse, VolunteerProfile

security_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> UserResponse:
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired operational session token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    phone = payload.get("sub")
    if not phone:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing operational subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_doc = await db["users"].find_one({"phone": phone})
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorized operator account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user_doc.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operational account is suspended or inactive"
        )
    
    vol_prof = None
    if user_doc.get("volunteer_profile"):
        vol_prof = VolunteerProfile(**user_doc["volunteer_profile"])
        
    return UserResponse(
        id=str(user_doc["_id"]),
        phone=user_doc["phone"],
        full_name=user_doc["full_name"],
        email=user_doc.get("email"),
        role=UserRole(user_doc["role"]),
        is_active=user_doc.get("is_active", True),
        badge_number=user_doc.get("badge_number"),
        department_or_agency=user_doc.get("department_or_agency"),
        created_at=user_doc.get("created_at") or datetime.now(timezone.utc),
        volunteer_profile=vol_prof,
    )


def require_roles(allowed_roles: List[UserRole]):
    async def role_checker(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
        if current_user.role not in allowed_roles and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Operational role '{current_user.role.value}' is not authorized for this section."
            )
        return current_user
    return role_checker


require_admin = require_roles([UserRole.ADMIN])
require_officer = require_roles([UserRole.EMERGENCY_OFFICER, UserRole.ADMIN])
require_resource_manager = require_roles([UserRole.RESOURCE_MANAGER, UserRole.ADMIN])
require_resource_operator = require_roles([UserRole.RESOURCE_MANAGER, UserRole.EMERGENCY_OFFICER, UserRole.ADMIN])
require_volunteer = require_roles([UserRole.VOLUNTEER, UserRole.ADMIN])
