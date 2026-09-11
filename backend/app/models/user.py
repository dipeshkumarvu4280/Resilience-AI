from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.models.enums import UserRole, VolunteerSkill, VolunteerAvailability


class VolunteerProfile(BaseModel):
    skills: List[str] = Field(default_factory=list)
    availability: str = VolunteerAvailability.IMMEDIATE.value
    zone_or_district: Optional[str] = None
    notes: Optional[str] = None


class UserBase(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15, description="E.164 or 10-digit standard phone")
    full_name: str = Field(..., min_length=2, max_length=100)
    email: Optional[str] = None
    role: UserRole = UserRole.VOLUNTEER
    is_active: bool = True
    badge_number: Optional[str] = None
    department_or_agency: Optional[str] = None
    google_sub: Optional[str] = None


class VolunteerRegister(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=10, max_length=15)
    password: str = Field(..., min_length=8, max_length=128)
    skills: List[str] = Field(default_factory=list)
    availability: str = VolunteerAvailability.IMMEDIATE.value
    zone_or_district: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)
    volunteer_profile: Optional[VolunteerProfile] = None


class UserLogin(BaseModel):
    phone: str
    password: str
    intended_role: Optional[UserRole] = None


class GoogleAuthRequest(BaseModel):
    code: Optional[str] = Field(None, description="Google OAuth 2.0 authorization code")
    id_token: Optional[str] = Field(None, description="Google OpenID Connect ID token")
    token: Optional[str] = Field(None, description="Legacy token field for compatibility")
    redirect_uri: Optional[str] = None
    state: Optional[str] = None
    email: Optional[str] = None  # Deprecated legacy field; server extracts verified email
    name: Optional[str] = None   # Deprecated legacy field; server extracts verified name
    intended_role: Optional[UserRole] = None


class UserResponse(UserBase):
    id: str
    created_at: datetime
    volunteer_profile: Optional[VolunteerProfile] = None


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, min_length=7, max_length=15)
    email: Optional[str] = None
    department_or_agency: Optional[str] = None
    badge_number: Optional[str] = None
    volunteer_profile: Optional[VolunteerProfile] = None


class UserInDB(UserBase):
    id: str = Field(..., alias="_id")
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    volunteer_profile: Optional[VolunteerProfile] = None
    auth_provider: str = "local"  # 'local' or 'google'
    last_login: Optional[datetime] = None
