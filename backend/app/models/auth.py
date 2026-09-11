from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.models.user import UserResponse


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenPayload(BaseModel):
    sub: str
    role: str
    exp: int


class OTPRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)


class OTPRequestResponse(BaseModel):
    message: str = "Verification code generated and dispatched securely"
    phone: str
    expires_in_seconds: int = 300


class OTPVerifyRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class OTPVerifyResponse(BaseModel):
    message: str = "OTP verification successful"
    phone: str
    reset_token: str
    expires_in_seconds: int = 600


class PasswordResetRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    reset_token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)


class PasswordResetResponse(BaseModel):
    message: str = "Password reset successfully. Please log in with your new credentials."


class GoogleAuthUrlResponse(BaseModel):
    auth_url: str
    client_id: str
    redirect_uri: str


class GoogleCallbackRequest(BaseModel):
    code: Optional[str] = None
    state: Optional[str] = None
    id_token: Optional[str] = None
    redirect_uri: Optional[str] = None
    intended_role: Optional[str] = None
