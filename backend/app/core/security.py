import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import jwt
import bcrypt
from app.core.config import settings


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": int(expire.timestamp())})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


def generate_secure_otp() -> str:
    """Generate a cryptographically secure 6-digit OTP."""
    return f"{secrets.SystemRandom().randint(100000, 999999)}"


def hash_otp(otp: str) -> str:
    """Hash OTP using SHA-256 with project secret salt for DB storage."""
    return hashlib.sha256(f"{otp}:{settings.SECRET_KEY}".encode("utf-8")).hexdigest()


def verify_otp_hash(plain_otp: str, stored_hash: str) -> bool:
    expected_hash = hash_otp(plain_otp)
    return secrets.compare_digest(expected_hash, stored_hash)


def create_password_reset_token(phone: str) -> str:
    """Create a short-lived reset token valid for 10 minutes."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload = {
        "sub": phone,
        "type": "password_reset",
        "exp": int(expire.timestamp())
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_password_reset_token(token: str, phone: str) -> bool:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "password_reset":
            return False
        return payload.get("sub") == phone
    except jwt.PyJWTError:
        return False
