import logging
import secrets
import string
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Request, Header
from motor.motor_asyncio import AsyncIOMotorDatabase
import jwt

from app.core.config import settings
from app.core.security import (
    generate_secure_otp,
    hash_otp,
    verify_otp_hash,
)
from app.db.mongodb import get_database
from app.api.deps import require_officer
from app.models.user import UserResponse
from app.models.enums import (
    EmergencyType,
    ReportStatus,
    CitizenImpactLevel,
    EvidenceValidationStatus,
    ReportTrustState,
    TimelineEventType,
    UserRole,
)
from app.models.citizen import (
    CitizenOTPRequest,
    CitizenOTPRequestResponse,
    CitizenOTPVerifyRequest,
    CitizenOTPVerifyResponse,
    EmergencyReportCreate,
    EmergencyReportResponse,
    MediaAttachment,
    LocationPayload,
    ReverseGeocodeResponse,
    LiveEvidencePayload,
    LiveEvidenceRecord,
    EvidenceVerificationResult,
    CitizenReportUpdateRequest,
)
from app.models.corroboration import CorroborationResult
from app.models.incident_evolution import IncidentEvolutionTimelineResponse
from app.models.visual_evidence import VisualEvidenceAnalysis
from app.services.geocoding import (
    reverse_geocode_coordinates,
    validate_coordinates,
)
from app.services.evidence_service import EvidenceValidationService
from app.services.evidence_verification_service import EvidenceVerificationService
from app.services.corroboration_service import EvidenceCorroborationService
from app.services.gemini_service import GeminiIntelligenceService
from app.models.llm_extraction import LLMExtractionResult, ExtractionStatus
from app.services.timeline import record_timeline_event


logger = logging.getLogger("resilience.citizen")
router = APIRouter()

# Directory for citizen media attachments
UPLOAD_DIR = os.path.join(settings.UPLOAD_DIR, "citizen_reports")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB


def normalize_phone_number(phone: str) -> str:
    """Normalize phone by stripping whitespace, hyphens, dots, and parentheses."""
    if not phone:
        return ""
    cleaned = re.sub(r"[\s\-\(\)\.]", "", phone.strip())
    return cleaned


def validate_phone_format(phone: str) -> bool:
    """Validate phone format: 7 to 15 digits, optionally prefixed with '+'."""
    normalized = normalize_phone_number(phone)
    return bool(re.match(r"^\+?[0-9]{7,15}$", normalized))


def generate_unique_report_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"RES-{suffix}"


def generate_citizen_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"CIT-{suffix}"


def create_citizen_verification_token(phone: str, citizen_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode = {
        "sub": phone,
        "citizen_id": citizen_id,
        "type": "citizen_report_submission",
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_citizen_verification_token(token: Optional[str], expected_phone: str) -> Optional[dict]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("sub") != expected_phone:
            return None
        if payload.get("type") != "citizen_report_submission":
            return None
        return payload
    except Exception:
        return None


async def check_submission_rate_limit(
    db: AsyncIOMotorDatabase,
    client_ip: str,
    phone: str,
    now: datetime
) -> Tuple[bool, bool]:
    """
    Check rate limiting for emergency report creation (Emergency-First Principle).
    Prevents spam bursts without blocking multiple emergency reporters sharing an IP / NAT.
    Returns: (is_blocked: bool, is_high_frequency: bool)
    """
    one_minute_ago = now - timedelta(minutes=1)
    five_minutes_ago = now - timedelta(minutes=5)

    # 1. Per-phone limit: maximum 5 reports per minute from the exact same phone number
    phone_count_1min = await db["citizen_reports"].count_documents({
        "citizen_phone": phone,
        "created_at": {"$gte": one_minute_ago},
    })
    if phone_count_1min >= 5:
        return True, True

    # 2. Per-IP limit (for public remote IPs): maximum 30 reports per minute per IP
    if client_ip and client_ip not in ["testclient", "unknown", "127.0.0.1", "localhost", "::1"]:
        ip_count_1min = await db["citizen_reports"].count_documents({
            "client_ip": client_ip,
            "created_at": {"$gte": one_minute_ago},
        })
        if ip_count_1min >= 30:
            return True, True

    # 3. High submission frequency flag: 3+ reports within 5 minutes from this phone
    phone_count_5min = await db["citizen_reports"].count_documents({
        "citizen_phone": phone,
        "created_at": {"$gte": five_minutes_ago},
    })
    is_high_frequency = phone_count_5min >= 3

    return False, is_high_frequency



async def detect_duplicate_report(
    db: AsyncIOMotorDatabase,
    emergency_type: str,
    phone: str,
    lat: float,
    lon: float,
    now: datetime
) -> Tuple[bool, Optional[str]]:
    """
    Lightweight duplicate detection:
    Checks if a report with the same emergency type was created within the last 15 minutes
    from the same phone or within ~200 meters (+/- 0.002 degrees latitude/longitude).
    """
    window_start = now - timedelta(minutes=15)
    query = {
        "created_at": {"$gte": window_start},
        "emergency_type": emergency_type,
        "$or": [
            {"citizen_phone": phone},
            {
                "location.latitude": {"$gte": lat - 0.002, "$lte": lat + 0.002},
                "location.longitude": {"$gte": lon - 0.002, "$lte": lon + 0.002},
            }
        ]
    }
    duplicate = await db["citizen_reports"].find_one(query, sort=[("created_at", -1)])
    if duplicate:
        return True, duplicate.get("report_id")
    return False, None


@router.post("/otp/send", response_model=CitizenOTPRequestResponse)
async def send_citizen_otp(
    payload: CitizenOTPRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    phone = normalize_phone_number(payload.phone)
    if not validate_phone_format(phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid phone number (7-15 digits).",
        )

    now = datetime.now(timezone.utc)
    
    # Rate limit check: maximum 5 OTP requests per 15-minute window
    window_start = now - timedelta(minutes=15)
    recent_count = await db["citizen_otps"].count_documents({
        "phone": phone,
        "created_at": {"$gte": window_start}
    })
    if recent_count >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification attempts. Please wait 15 minutes before requesting another code.",
        )

    # Invalidate existing active OTPs for this phone
    await db["citizen_otps"].update_many(
        {"phone": phone, "is_used": False},
        {"$set": {"is_used": True, "invalidated_reason": "SUPERSEDED"}}
    )

    raw_otp = generate_secure_otp()
    hashed = hash_otp(raw_otp)
    expires_at = now + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

    await db["citizen_otps"].insert_one({
        "phone": phone,
        "name": payload.name.strip() if payload.name else None,
        "hashed_otp": hashed,
        "attempts": 0,
        "is_used": False,
        "created_at": now,
        "expires_at": expires_at,
    })

    # Internal logging without raw OTP in production logs
    logger.info(f"[CITIZEN DISPATCH] OTP issued for {phone[:3]}***{phone[-2:]}")
    # Development local terminal gateway print:
    print(f"\n========================================\n[LOCAL CITIZEN EMERGENCY OTP GATEWAY]\nPHONE: {phone}\nOTP: {raw_otp}\n========================================\n")

    return CitizenOTPRequestResponse(
        message="Verification code dispatched securely to your phone.",
        phone=phone,
        expires_in_seconds=settings.OTP_EXPIRE_MINUTES * 60,
        cooldown_seconds=60,
    )


@router.post("/otp/verify", response_model=CitizenOTPVerifyResponse)
async def verify_citizen_otp(
    payload: CitizenOTPVerifyRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    phone = normalize_phone_number(payload.phone)
    otp_code = payload.otp.strip()
    now = datetime.now(timezone.utc)

    otp_record = await db["citizen_otps"].find_one({
        "phone": phone,
        "is_used": False,
        "expires_at": {"$gt": now}
    }, sort=[("created_at", -1), ("_id", -1)])

    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code. Please request a new OTP.",
        )

    if otp_record.get("attempts", 0) >= settings.MAX_OTP_ATTEMPTS:
        await db["citizen_otps"].update_one(
            {"_id": otp_record["_id"]},
            {"$set": {"is_used": True, "invalidated_reason": "MAX_ATTEMPTS_EXCEEDED"}}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum verification attempts exceeded. Please request a new code.",
        )

    if not verify_otp_hash(otp_code, otp_record["hashed_otp"]):
        await db["citizen_otps"].update_one(
            {"_id": otp_record["_id"]},
            {"$inc": {"attempts": 1}}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect verification code. Please try again.",
        )

    # Mark OTP as verified
    await db["citizen_otps"].update_one(
        {"_id": otp_record["_id"]},
        {"$set": {"is_used": True, "verified_at": now}}
    )

    # Update Citizen Identity record
    citizen = await db["citizen_identities"].find_one({"phone": phone})
    if not citizen:
        citizen_id = generate_citizen_id()
        citizen_doc = {
            "citizen_id": citizen_id,
            "phone": phone,
            "name": otp_record.get("name") or "Community Citizen",
            "phone_verified": True,
            "created_at": now,
            "updated_at": now,
        }
        await db["citizen_identities"].insert_one(citizen_doc)
    else:
        citizen_id = citizen["citizen_id"]
        await db["citizen_identities"].update_one(
            {"_id": citizen["_id"]},
            {"$set": {"phone_verified": True, "updated_at": now}}
        )

    verification_token = create_citizen_verification_token(phone, citizen_id)

    return CitizenOTPVerifyResponse(
        message="Phone number verified successfully.",
        phone=phone,
        citizen_id=citizen_id,
        verification_token=verification_token,
        expires_in_seconds=900,
    )


@router.post("/upload-media", response_model=MediaAttachment)
async def upload_citizen_media(
    file: UploadFile = File(...)
):
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type ({file.content_type}). Allowed types: JPG, PNG, WEBP, MP4, WEBM.",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds maximum allowed limit (15MB).",
        )

    ext = ALLOWED_MIME_TYPES[file.content_type]
    safe_token = secrets.token_hex(8)
    filename = f"media_{safe_token}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    return MediaAttachment(
        filename=filename,
        file_url=f"/uploads/citizen_reports/{filename}",
        media_type=file.content_type,
        size_bytes=len(content),
    )


@router.get("/location/reverse-geocode", response_model=ReverseGeocodeResponse)
async def reverse_geocode_endpoint(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude between -90 and +90"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude between -180 and +180"),
):
    """
    Reverse geocodes latitude & longitude coordinates into a human-readable address.
    Uses OpenStreetMap Nominatim with in-memory caching and rate limiting.
    """
    if not validate_coordinates(lat, lon):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid coordinates. Latitude must be in [-90, 90] and Longitude in [-180, 180].",
        )

    geocoded = await reverse_geocode_coordinates(lat, lon)
    if geocoded:
        return ReverseGeocodeResponse(
            latitude=lat,
            longitude=lon,
            address=geocoded.get("address"),
            street_address=geocoded.get("street_address"),
            landmark=geocoded.get("landmark"),
            zone_or_district=geocoded.get("zone_or_district"),
            district=geocoded.get("district"),
            display_name=geocoded.get("display_name"),
            city=geocoded.get("city"),
            state=geocoded.get("state"),
            country=geocoded.get("country"),
            postal_code=geocoded.get("postal_code"),
            resolved=True,
        )

    return ReverseGeocodeResponse(
        latitude=lat,
        longitude=lon,
        address=None,
        resolved=False,
    )


@router.post("/reports", response_model=EmergencyReportResponse, status_code=status.HTTP_201_CREATED)
async def create_emergency_report(
    payload: EmergencyReportCreate,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    # 1. Anti-bot honeypot protection: if hidden bot honeypot is filled, reject automated submission
    if payload.bot_honeypot and payload.bot_honeypot.strip():
        logger.warning("[ANTI-BOT] Automated bot submission rejected via honeypot trigger.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Automated submission detected. If you are a human citizen, please leave the security verification field empty.",
        )

    # 2. Mandatory Full Name validation
    full_name = payload.full_name.strip()
    if len(full_name) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Full Name is required (minimum 2 characters).",
        )

    # 3. Mandatory Phone validation & normalization
    normalized_phone = normalize_phone_number(payload.phone)
    if not validate_phone_format(normalized_phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid phone number (7-15 digits).",
        )

    # 4. Mandatory Description validation
    description = payload.description.strip()
    if len(description) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a descriptive explanation of the incident (at least 10 characters).",
        )

    # 5. Mandatory Coordinates validation
    lat = payload.location.latitude
    lon = payload.location.longitude
    if not validate_coordinates(lat, lon):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid coordinates. Latitude must be in [-90, 90] and Longitude in [-180, 180].",
        )

    client_ip = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)

    # 6. Backend Rate Limiting (Emergency-First Principle)
    is_blocked, is_high_frequency = await check_submission_rate_limit(db, client_ip, normalized_phone, now)
    if is_blocked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Submission rate limit reached. Please wait a moment before submitting another report.",
        )

    # 7. Duplicate Report Detection & Idempotency Protection
    # If the exact same report was already created within 15 minutes, return the existing genuine report to prevent duplicates
    dup_window_start = now - timedelta(minutes=15)
    existing_duplicate = await db["citizen_reports"].find_one({
        "created_at": {"$gte": dup_window_start},
        "citizen_phone": normalized_phone,
        "emergency_type": payload.emergency_type.value,
        "$or": [
            {
                "location.latitude": {"$gte": lat - 0.002, "$lte": lat + 0.002},
                "location.longitude": {"$gte": lon - 0.002, "$lte": lon + 0.002},
            },
            {"description": description},
        ],
    }, sort=[("created_at", -1)])

    if existing_duplicate:
        dup_report_id = existing_duplicate["report_id"]
        logger.info(f"[IDEMPOTENT RETRY] Returning existing genuine report {dup_report_id} for phone {normalized_phone[:3]}***")
        
        guidance_doc = await db["citizen_safety_guidance"].find_one({
            "report_id": dup_report_id,
            "status": "ACTIVE",
        })
        guidance_id_val = guidance_doc.get("guidance_id") if guidance_doc else None
        guidance_token_val = guidance_doc.get("secure_access_token") if guidance_doc else None

        raw_impact = existing_duplicate.get("citizen_impact_level", CitizenImpactLevel.NOT_SURE.value)
        try:
            impact_obj = CitizenImpactLevel(raw_impact)
        except Exception:
            impact_obj = CitizenImpactLevel.NOT_SURE

        raw_trust = existing_duplicate.get("trust_state", ReportTrustState.NORMAL.value)
        try:
            trust_obj = ReportTrustState(raw_trust)
        except Exception:
            trust_obj = ReportTrustState.NORMAL

        evidence_doc = existing_duplicate.get("evidence")
        evidence_obj = None
        if isinstance(evidence_doc, dict):
            try:
                evidence_obj = LiveEvidenceRecord(**evidence_doc)
            except Exception:
                pass

        return EmergencyReportResponse(
            report_id=dup_report_id,
            citizen_id=existing_duplicate["citizen_id"],
            citizen_name=existing_duplicate["citizen_name"],
            citizen_phone=existing_duplicate["citizen_phone"],
            emergency_type=EmergencyType(existing_duplicate["emergency_type"]),
            citizen_impact_level=impact_obj,
            description=existing_duplicate["description"],
            location=LocationPayload(**existing_duplicate["location"]),
            media=[MediaAttachment(**m) for m in existing_duplicate.get("media", [])],
            evidence=evidence_obj,
            status=ReportStatus(existing_duplicate.get("status", ReportStatus.RECEIVED.value)),
            phone_verified=existing_duplicate.get("phone_verified", False),
            possible_duplicate=True,
            risk_level=existing_duplicate.get("risk_level", "LOW"),
            risk_reasons=existing_duplicate.get("risk_reasons", []),
            trust_state=trust_obj,
            trust_signals=existing_duplicate.get("trust_signals", []),
            situation_id=existing_duplicate.get("situation_id"),
            safety_guidance_id=guidance_id_val,
            safety_guidance_token=guidance_token_val,
            created_at=existing_duplicate["created_at"],
            updated_at=existing_duplicate.get("updated_at", existing_duplicate["created_at"]),
        )

    is_duplicate, duplicate_id = await detect_duplicate_report(
        db, payload.emergency_type.value, normalized_phone, lat, lon, now
    )

    # 8. Identity & Phone Verification Semantics
    # Check if an optional valid verification token was provided
    token_data = verify_citizen_verification_token(payload.verification_token, normalized_phone)
    phone_verified = bool(token_data)

    # Manage citizen identity document
    citizen = await db["citizen_identities"].find_one({"phone": normalized_phone})
    if not citizen:
        citizen_id = generate_citizen_id()
        citizen_doc = {
            "citizen_id": citizen_id,
            "phone": normalized_phone,
            "name": full_name,
            "phone_verified": phone_verified,
            "created_at": now,
            "updated_at": now,
        }
        await db["citizen_identities"].insert_one(citizen_doc)
    else:
        citizen_id = citizen["citizen_id"]
        # Only update phone_verified to True if explicitly verified with valid token
        if phone_verified and not citizen.get("phone_verified", False):
            await db["citizen_identities"].update_one(
                {"_id": citizen["_id"]},
                {"$set": {"phone_verified": True, "updated_at": now}}
            )

    # 9. Real-signal Risk & Trust Assessment Calculation
    risk_reasons = []
    risk_level = "LOW"

    if not phone_verified:
        # Note: Unverified phone is standard in emergency reporting; do not label user fake
        pass

    if is_duplicate:
        risk_level = "MEDIUM"
        risk_reasons.append(f"Possible duplicate of recent report ({duplicate_id})")

    if is_high_frequency:
        risk_level = "HIGH"
        risk_reasons.append("High submission frequency from this source")

    # 10. Authoritative backend reverse geocoding
    geocoded = await reverse_geocode_coordinates(lat, lon)
    if geocoded and geocoded.get("address"):
        resolved_address = geocoded["address"]
        resolved_street_address = geocoded.get("street_address") or payload.location.street_address or payload.location.address
        resolved_landmark = geocoded.get("landmark") or payload.location.landmark
        resolved_zone_or_district = payload.location.manual_zone or geocoded.get("zone_or_district") or payload.location.zone_or_district
        resolved_district = geocoded.get("district") or payload.location.district
        resolved_display_name = geocoded.get("display_name")
        resolved_city = geocoded.get("city")
        resolved_state = geocoded.get("state")
        resolved_country = geocoded.get("country")
        resolved_postal_code = geocoded.get("postal_code")
    else:
        # Fallback to user-entered manual address/landmark or explicit unavailable notice (never fake)
        resolved_address = payload.location.address or "Address unavailable"
        resolved_street_address = payload.location.street_address or payload.location.address or "Address unavailable"
        resolved_landmark = payload.location.landmark
        resolved_zone_or_district = payload.location.manual_zone or payload.location.zone_or_district
        resolved_district = payload.location.district
        resolved_display_name = payload.location.display_name
        resolved_city = payload.location.city
        resolved_state = payload.location.state
        resolved_country = payload.location.country
        resolved_postal_code = payload.location.postal_code

    canonical_location = LocationPayload(
        latitude=lat,
        longitude=lon,
        address=resolved_address,
        street_address=resolved_street_address,
        landmark=resolved_landmark,
        zone_or_district=resolved_zone_or_district,
        district=resolved_district,
        display_name=resolved_display_name,
        city=resolved_city,
        state=resolved_state,
        country=resolved_country,
        postal_code=resolved_postal_code,
        manual_zone=payload.location.manual_zone or resolved_zone_or_district,
        accuracy_meters=payload.location.accuracy_meters,
    )

    # 11. Generate unique human-readable report ID: RES-XXXXXXXX
    report_id = generate_unique_report_id()
    while await db["citizen_reports"].find_one({"report_id": report_id}):
        report_id = generate_unique_report_id()

    # 12. Process Live Camera Evidence & Cryptographic / Geo-temporal Validation
    evidence_record, trust_state, trust_signals = await EvidenceValidationService.process_live_evidence(
        evidence_payload=payload.evidence,
        report_location=canonical_location,
        report_id=report_id,
        db=db,
    )

    # 12b. Extract Structured Evidence via Gemini Hybrid Intelligence Layer (Advisory Only)
    llm_extraction = None
    try:
        llm_extraction = await GeminiIntelligenceService.extract_structured_evidence(
            source_id=report_id,
            source_type="CITIZEN_REPORT",
            text_content=description,
            context_metadata={
                "emergency_type": payload.emergency_type.value,
                "location_address": resolved_address,
            },
        )
    except Exception as llm_err:
        logger.warning(f"LLM evidence extraction notice for {report_id}: {llm_err}")
        llm_extraction = LLMExtractionResult.unavailable(
            source_id=report_id,
            source_type="CITIZEN_REPORT",
            reason=str(llm_err),
        )

    # 12c. Analyze Live Camera Visual Evidence via Gemini Vision Multimodal Intelligence (Advisory Only)
    visual_evidence = None
    if payload.evidence and payload.evidence.image_base64 and evidence_record and evidence_record.content_hash:
        try:
            visual_evidence = await GeminiIntelligenceService.analyze_visual_evidence(
                source_id=report_id,
                image_base64=payload.evidence.image_base64,
                content_hash=evidence_record.content_hash,
                citizen_text=description,
                declared_type=payload.emergency_type.value,
                report_id=report_id,
                evidence_id=evidence_record.evidence_id,
            )
        except Exception as vis_err:
            logger.warning(f"Gemini vision analysis notice for {report_id}: {vis_err}")
            visual_evidence = VisualEvidenceAnalysis.unavailable(
                source_id=report_id,
                reason=str(vis_err),
                report_id=report_id,
                evidence_id=evidence_record.evidence_id,
                content_hash=evidence_record.content_hash,
            )

    report_doc = {
        "report_id": report_id,
        "citizen_id": citizen_id,
        "citizen_name": full_name,
        "citizen_phone": normalized_phone,
        "emergency_type": payload.emergency_type.value,
        "citizen_impact_level": payload.citizen_impact_level.value,
        "description": description,
        "location": canonical_location.model_dump(),
        "media": [m.model_dump() for m in (payload.media or [])],
        "evidence": evidence_record.model_dump() if evidence_record else None,
        "llm_extraction": llm_extraction.model_dump() if llm_extraction else None,
        "visual_evidence": visual_evidence.model_dump() if visual_evidence else None,
        "status": ReportStatus.RECEIVED.value,
        "priority": "UNASSESSED",
        "phone_verified": phone_verified,
        "possible_duplicate": is_duplicate,
        "risk_level": risk_level,
        "risk_reasons": risk_reasons,
        "trust_state": trust_state.value,
        "trust_signals": trust_signals,
        "client_ip": client_ip,
        "created_at": now,
        "updated_at": now,
    }


    await db["citizen_reports"].insert_one(report_doc)

    # Record Authoritative Timeline Event for Report Creation
    try:
        await record_timeline_event(
            db=db,
            report_id=report_id,
            event_type=TimelineEventType.REPORT_RECEIVED,
            details=f"Emergency report {report_id} received from {full_name} ({payload.emergency_type.value}, Citizen Impact: {payload.citizen_impact_level.value}).",
            actor_id=citizen_id,
            actor_name=full_name,
            actor_role=UserRole.CITIZEN,
        )

        if evidence_record:
            if evidence_record.validation_status == EvidenceValidationStatus.UNAVAILABLE:
                await record_timeline_event(
                    db=db,
                    report_id=report_id,
                    event_type=TimelineEventType.EVIDENCE_FLAGGED,
                    details=f"Camera evidence marked UNAVAILABLE: {evidence_record.error_reason}",
                    actor_id=citizen_id,
                    actor_name=full_name,
                    actor_role=UserRole.CITIZEN,
                )
            else:
                await record_timeline_event(
                    db=db,
                    report_id=report_id,
                    event_type=TimelineEventType.EVIDENCE_CAPTURED,
                    details=f"Live browser camera evidence {evidence_record.evidence_id} captured (Hash: {evidence_record.content_hash[:12]}...).",
                    actor_id=citizen_id,
                    actor_name=full_name,
                    actor_role=UserRole.CITIZEN,
                )
                await record_timeline_event(
                    db=db,
                    report_id=report_id,
                    event_type=TimelineEventType.EVIDENCE_VALIDATED if trust_state == ReportTrustState.NORMAL else TimelineEventType.EVIDENCE_FLAGGED,
                    details=f"Evidence {evidence_record.evidence_id} validation status: {evidence_record.validation_status.value}. Trust Signals: {', '.join(trust_signals) or 'None'}.",
                    actor_id="SYSTEM_VALIDATOR",
                    actor_name="Automated Evidence Validator",
                    actor_role=None,
                )
    except Exception as tl_err:
        logger.warning(f"Timeline event recording notice for {report_id}: {tl_err}")

    # Phase 4: Deterministic Incident Fusion into Situation Cluster
    sit_doc = None
    try:
        from app.services.incident_fusion import fuse_or_create_situation_for_report
        sit_doc = await fuse_or_create_situation_for_report(db, report_doc)
    except Exception as fusion_err:
        logger.warning(f"Incident fusion sync notice for {report_id}: {fusion_err}")

    # Phase 6: Live Monitoring Telemetry Event Emission
    try:
        from app.services.monitoring.monitoring_service import MonitoringService
        from app.models.enums import MonitoringEventType, EventSourceType
        
        sit_id = sit_doc.get("situation_id") if sit_doc else None
        await MonitoringService.record_change_event(
            event_type=MonitoringEventType.REPORT_CREATED,
            source_type=EventSourceType.CITIZEN_REPORT,
            source_id=report_id,
            previous_state={},
            new_state={
                "report_id": report_id,
                "emergency_type": payload.emergency_type.value,
                "citizen_impact_level": payload.citizen_impact_level.value,
                "description": description,
                "status": ReportStatus.RECEIVED.value,
                "risk_level": risk_level,
                "citizen_name": full_name,
                "trust_state": trust_state.value,
            },
            situation_id=sit_id,
            location=canonical_location.model_dump(),
            actor={
                "id": citizen_id,
                "full_name": full_name,
                "role": "CITIZEN",
            },
            db=db,
        )
    except Exception as mon_err:
        logger.warning(f"Monitoring event recording notice for report {report_id}: {mon_err}")

    # Phase 1: Live Citizen Safety Guidance Synthesis
    guidance_id_val = None
    guidance_token_val = None
    try:
        from app.services.agents.adapters.safety_guidance_agent import SafetyGuidanceAgent
        guidance = await SafetyGuidanceAgent.generate_safety_guidance(
            report_id=report_id,
            db=db,
            force_refresh=False,
        )
        guidance_id_val = guidance.guidance_id
        guidance_token_val = guidance.secure_access_token
    except Exception as g_err:
        logger.warning(f"Safety guidance generation notice for report {report_id}: {g_err}")

    # Canonical Public Safety Guidelines URL
    from app.core.config import settings
    frontend_base = getattr(settings, "FRONTEND_BASE_URL", "https://resilience-ai-pied.vercel.app").rstrip("/")
    if guidance_token_val:
        safety_guidelines_url = f"{frontend_base}/safety-guidance/{guidance_token_val}"
    else:
        safety_guidelines_url = f"{frontend_base}/safety-guidance"

    # Phase 7: Event-Driven Notification Dispatch
    try:
        from app.services.notification import get_notification_service
        from app.models.enums import NotificationCategory, NotificationSeverity
        
        notif_sev = NotificationSeverity.HIGH
        if payload.emergency_type.value in ["Building Collapse", "Fire", "Flood", "Medical Emergency"] or risk_level == "HIGH" or payload.citizen_impact_level.value == "CRITICAL":
            notif_sev = NotificationSeverity.CRITICAL
        
        notif_service = get_notification_service()

        # 1. Operational Notification to Emergency Officers and Admins
        await notif_service.dispatch_event(
            category=NotificationCategory.CITIZEN_REPORT,
            event_type="REPORT_CREATED",
            severity=notif_sev,
            title=f"New Emergency Report: {payload.emergency_type.value} [Impact: {payload.citizen_impact_level.value}]",
            message=f"{description[:140]} | Location: {resolved_address}",
            entity_type="CITIZEN_REPORT",
            entity_id=report_id,
            situation_id=sit_id,
            view_hint="reports",
            target_roles=[UserRole.EMERGENCY_OFFICER, UserRole.ADMIN],
            material_state={"report_id": report_id, "status": ReportStatus.RECEIVED.value, "severity": notif_sev.value},
            metadata={
                "report_id": report_id,
                "emergency_type": payload.emergency_type.value,
                "citizen_impact_level": payload.citizen_impact_level.value,
                "location_name": resolved_address,
                "citizen_name": full_name,
            },
            db=db,
        )

        # 2. Citizen Reporter Safety Guidance Notification (In-App + SMS with Twilio Trial compatibility)
        reporter_title = "Emergency Report Received — Safety Guidance"
        reporter_message = (
            f"Your emergency report has been received.\n"
            f"Please follow the safety guidance while responders review your report.\n\n"
            f"View Safety Guidelines: {safety_guidelines_url}"
        )

        await notif_service.dispatch_event(
            category=NotificationCategory.CITIZEN_REPORT,
            event_type="REPORTER_SAFETY_GUIDANCE",
            severity=notif_sev,
            title=reporter_title,
            message=reporter_message,
            entity_type="CITIZEN_REPORT",
            entity_id=report_id,
            situation_id=sit_id,
            view_hint="citizen",
            target_user_ids=[normalized_phone],
            material_state={
                "report_id": report_id,
                "action": "SAFETY_GUIDANCE_REPORT_RECEIVED",
            },
            metadata={
                "report_id": report_id,
                "safety_guidelines_url": safety_guidelines_url,
                "safety_guidance_token": guidance_token_val,
                "safety_guidance_id": guidance_id_val,
                "emergency_type": payload.emergency_type.value,
                "recipient_role": "CITIZEN",
                "citizen_phone": normalized_phone,
                "citizen_name": full_name,
            },
            db=db,
        )
    except Exception as notif_err:
        logger.warning(f"Notification dispatch notice for report {report_id}: {notif_err}")

    logger.info(
        f"[EMERGENCY RECEIVED] Report {report_id} ({payload.emergency_type.value}, Impact: {payload.citizen_impact_level.value}) at "
        f"lat={lat}, lon={lon}, phone={normalized_phone[:3]}***, verified={phone_verified}, "
        f"duplicate={is_duplicate}, risk={risk_level}, trust={trust_state.value}"
    )

    return EmergencyReportResponse(
        report_id=report_id,
        citizen_id=citizen_id,
        citizen_name=full_name,
        citizen_phone=normalized_phone,
        emergency_type=payload.emergency_type,
        citizen_impact_level=payload.citizen_impact_level,
        description=description,
        location=canonical_location,
        media=payload.media or [],
        evidence=evidence_record,
        llm_extraction=llm_extraction,
        visual_evidence=visual_evidence,
        status=ReportStatus.RECEIVED,
        phone_verified=phone_verified,
        possible_duplicate=is_duplicate,
        risk_level=risk_level,
        risk_reasons=risk_reasons,
        trust_state=trust_state,
        trust_signals=trust_signals,
        situation_id=sit_id,
        safety_guidance_id=guidance_id_val,
        safety_guidance_token=guidance_token_val,
        created_at=now,
        updated_at=now,
    )



@router.get("/reports", response_model=List[EmergencyReportResponse])
async def list_emergency_reports(
    status_filter: Optional[ReportStatus] = Query(None, alias="status"),
    emergency_type: Optional[EmergencyType] = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    List emergency reports for authorized emergency officers, responders, and admins.
    Preserves canonical location with real coordinates, human-readable address, risk, duplicate indicators,
    and evidence validation trust signals.
    """
    query = {}
    if status_filter:
        query["status"] = status_filter.value
    if emergency_type:
        query["emergency_type"] = emergency_type.value

    cursor = db["citizen_reports"].find(query).sort("created_at", -1).limit(limit)
    reports = []
    async for doc in cursor:
        loc_dict = doc.get("location")
        if isinstance(loc_dict, dict):
            loc_payload = LocationPayload(**loc_dict)
        else:
            loc_payload = LocationPayload(
                latitude=float(doc.get("latitude", 0.0)),
                longitude=float(doc.get("longitude", 0.0)),
                address=doc.get("location_summary") or doc.get("address") or "Operational Zone"
            )
        now_utc = datetime.now(timezone.utc)
        
        raw_et = doc.get("emergency_type", EmergencyType.OTHER.value)
        et_obj = EmergencyType(raw_et) if raw_et in [e.value for e in EmergencyType] else EmergencyType.OTHER

        raw_impact = doc.get("citizen_impact_level", CitizenImpactLevel.NOT_SURE.value)
        try:
            impact_obj = CitizenImpactLevel(raw_impact)
        except Exception:
            impact_obj = CitizenImpactLevel.NOT_SURE

        evidence_doc = doc.get("evidence")
        evidence_obj = None
        if isinstance(evidence_doc, dict):
            try:
                evidence_obj = LiveEvidenceRecord(**evidence_doc)
            except Exception:
                pass

        raw_trust = doc.get("trust_state", ReportTrustState.NORMAL.value)
        try:
            trust_obj = ReportTrustState(raw_trust)
        except Exception:
            trust_obj = ReportTrustState.NORMAL

        llm_ext_doc = doc.get("llm_extraction")
        llm_ext_obj = None
        if isinstance(llm_ext_doc, dict):
            try:
                llm_ext_obj = LLMExtractionResult(**llm_ext_doc)
            except Exception:
                pass

        visual_ev_doc = doc.get("visual_evidence")
        visual_ev_obj = None
        if isinstance(visual_ev_doc, dict):
            try:
                visual_ev_obj = VisualEvidenceAnalysis(**visual_ev_doc)
            except Exception:
                pass

        reports.append(EmergencyReportResponse(
            report_id=doc.get("report_id", "UNKNOWN"),
            citizen_id=doc.get("citizen_id", "CIT-ANON"),
            citizen_name=doc.get("citizen_name", "Anonymous Citizen"),
            citizen_phone=doc.get("citizen_phone", "9999999999"),
            emergency_type=et_obj,
            citizen_impact_level=impact_obj,
            description=doc.get("description", "Emergency report"),
            location=loc_payload,
            media=[MediaAttachment(**m) for m in doc.get("media", []) if isinstance(m, dict)],
            evidence=evidence_obj,
            llm_extraction=llm_ext_obj,
            visual_evidence=visual_ev_obj,
            status=ReportStatus(doc.get("status", ReportStatus.RECEIVED.value)),
            phone_verified=doc.get("phone_verified", False),
            possible_duplicate=doc.get("possible_duplicate", False),
            risk_level=doc.get("risk_level", "LOW"),
            risk_reasons=doc.get("risk_reasons", []),
            trust_state=trust_obj,
            trust_signals=doc.get("trust_signals", []),
            created_at=doc.get("created_at") or now_utc,
            updated_at=doc.get("updated_at") or now_utc,
        ))
    return reports


@router.get("/reports/{report_id}", response_model=EmergencyReportResponse)
async def get_emergency_report(
    report_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    report_doc = await db["citizen_reports"].find_one({"report_id": report_id.strip().upper()})
    if not report_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report with ID '{report_id}' not found.",
        )

    raw_impact = report_doc.get("citizen_impact_level", CitizenImpactLevel.NOT_SURE.value)
    try:
        impact_obj = CitizenImpactLevel(raw_impact)
    except Exception:
        impact_obj = CitizenImpactLevel.NOT_SURE

    evidence_doc = report_doc.get("evidence")
    evidence_obj = None
    if isinstance(evidence_doc, dict):
        try:
            evidence_obj = LiveEvidenceRecord(**evidence_doc)
        except Exception:
            pass

    llm_ext_doc = report_doc.get("llm_extraction")
    llm_ext_obj = None
    if isinstance(llm_ext_doc, dict):
        try:
            llm_ext_obj = LLMExtractionResult(**llm_ext_doc)
        except Exception:
            pass

    # Auto-refresh failed or missing LLM extraction via TextAnalysisRouter (triggers OpenAI fallback)
    status_val = str(getattr(llm_ext_obj, "status", "")).upper()
    if (not llm_ext_obj or status_val in ["FAILED", "UNAVAILABLE", ExtractionStatus.FAILED.value, ExtractionStatus.UNAVAILABLE.value]) and report_doc.get("description"):
        try:
            from app.services.text_analysis_router import TextAnalysisRouter
            router = TextAnalysisRouter.get_instance()
            new_llm = await router.extract_structured_evidence(
                source_id=report_doc["report_id"],
                source_type="CITIZEN_REPORT",
                text_content=report_doc["description"],
                context_metadata={
                    "emergency_type": report_doc.get("emergency_type", "UNSPECIFIED"),
                    "location_address": report_doc.get("location", {}).get("address", "Not provided") if isinstance(report_doc.get("location"), dict) else "Not provided",
                },
                report_id=report_doc["report_id"],
            )
            new_status = str(getattr(new_llm, "status", "")).upper()
            if new_llm and (new_llm.status == ExtractionStatus.SUCCESS or new_status == "SUCCESS"):
                llm_ext_obj = new_llm
                await db["citizen_reports"].update_one(
                    {"_id": report_doc["_id"]},
                    {"$set": {"llm_extraction": new_llm.model_dump(mode="json"), "updated_at": datetime.now(timezone.utc)}}
                )
        except Exception as e:
            logger.warning(f"Auto-refresh LLM extraction error on citizen get_report: {e}")

    visual_ev_doc = report_doc.get("visual_evidence")
    visual_ev_obj = None
    if isinstance(visual_ev_doc, dict):
        try:
            visual_ev_obj = VisualEvidenceAnalysis(**visual_ev_doc)
        except Exception:
            pass

    evidence_verification = EvidenceVerificationService.evaluate_report_evidence(report_doc)
    corroboration_result = await EvidenceCorroborationService.get_or_evaluate_report_corroboration(report_doc["report_id"], db)

    raw_trust = report_doc.get("trust_state", ReportTrustState.NORMAL.value)
    try:
        trust_obj = ReportTrustState(raw_trust)
    except Exception:
        trust_obj = ReportTrustState.NORMAL

    guidance_doc = await db["citizen_safety_guidance"].find_one({
        "report_id": report_doc["report_id"],
        "status": "ACTIVE",
    })
    guidance_id_val = guidance_doc.get("guidance_id") if guidance_doc else None
    guidance_token_val = guidance_doc.get("secure_access_token") if guidance_doc else None

    return EmergencyReportResponse(
        report_id=report_doc["report_id"],
        citizen_id=report_doc["citizen_id"],
        citizen_name=report_doc["citizen_name"],
        citizen_phone=report_doc["citizen_phone"],
        emergency_type=EmergencyType(report_doc["emergency_type"]),
        citizen_impact_level=impact_obj,
        description=report_doc["description"],
        location=LocationPayload(**report_doc["location"]),
        media=[MediaAttachment(**m) for m in report_doc.get("media", [])],
        evidence=evidence_obj,
        evidence_verification=evidence_verification,
        corroboration=corroboration_result,
        llm_extraction=llm_ext_obj,
        visual_evidence=visual_ev_obj,
        status=ReportStatus(report_doc.get("status", ReportStatus.RECEIVED.value)),
        phone_verified=report_doc.get("phone_verified", False),
        possible_duplicate=report_doc.get("possible_duplicate", False),
        risk_level=report_doc.get("risk_level", "LOW"),
        risk_reasons=report_doc.get("risk_reasons", []),
        trust_state=trust_obj,
        trust_signals=report_doc.get("trust_signals", []),
        situation_id=report_doc.get("situation_id"),
        safety_guidance_id=guidance_id_val,
        safety_guidance_token=guidance_token_val,
        created_at=report_doc["created_at"],
        updated_at=report_doc["updated_at"],
    )


@router.patch("/reports/{report_id}", response_model=EmergencyReportResponse)
async def update_citizen_report(
    report_id: str,
    payload: CitizenReportUpdateRequest,
    x_citizen_token: Optional[str] = Header(None, alias="X-Citizen-Token"),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Update permitted fields of an existing citizen emergency report in-place.
    Protected by scoped citizen access token (safety guidance token or phone verification token) to prevent IDOR.
    Enforces immutable core fields (report_id, created_at, location coordinates, evidence hashes).
    """
    clean_id = report_id.strip().upper()
    report_doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not report_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report with ID '{report_id}' not found.",
        )

    # 1. Authorization: Citizen token validation
    provided_token = payload.citizen_token or x_citizen_token
    is_authorized = False

    if provided_token:
        # Check if the token matches any safety guidance record (active or historical) for this report
        guidance_doc = await db["citizen_safety_guidance"].find_one({
            "report_id": clean_id,
            "secure_access_token": provided_token.strip(),
        })
        if guidance_doc:
            is_authorized = True
        else:
            # Also check if token matches citizen verification token (phone token)
            token_data = verify_citizen_verification_token(provided_token.strip(), report_doc.get("citizen_phone", ""))
            if token_data:
                is_authorized = True

    if not is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized. A valid citizen safety guidance token or verification token is required to modify this report.",
        )

    # 2. Lifecycle check: terminal states cannot be modified
    current_status = report_doc.get("status", ReportStatus.RECEIVED.value)
    if current_status == ReportStatus.RESOLVED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Report {clean_id} is in status '{current_status}' and cannot be modified.",
        )

    # 3. Apply mutable updates (Protecting immutable: report_id, created_at, location, evidence, media)
    update_fields = {}
    changes = []
    now = datetime.now(timezone.utc)

    if payload.description is not None:
        new_desc = payload.description.strip()
        if len(new_desc) < 10:
            raise HTTPException(status_code=400, detail="Description must be at least 10 characters.")
        if new_desc != report_doc.get("description"):
            update_fields["description"] = new_desc
            changes.append(f"Description updated: '{new_desc[:60]}...'")

    if payload.citizen_impact_level is not None:
        if payload.citizen_impact_level.value != report_doc.get("citizen_impact_level"):
            update_fields["citizen_impact_level"] = payload.citizen_impact_level.value
            changes.append(f"Citizen Impact Level changed to {payload.citizen_impact_level.value}")

    if payload.full_name is not None:
        new_name = payload.full_name.strip()
        if len(new_name) < 2:
            raise HTTPException(status_code=400, detail="Full name must be at least 2 characters.")
        if new_name != report_doc.get("citizen_name"):
            update_fields["citizen_name"] = new_name
            changes.append(f"Citizen contact name updated to '{new_name}'")

    if payload.phone is not None:
        new_phone = normalize_phone_number(payload.phone)
        if not validate_phone_format(new_phone):
            raise HTTPException(status_code=400, detail="Invalid phone format.")
        if new_phone != report_doc.get("citizen_phone"):
            update_fields["citizen_phone"] = new_phone
            changes.append(f"Contact phone updated to '{new_phone}'")

    if payload.additional_notes is not None and payload.additional_notes.strip():
        note = payload.additional_notes.strip()
        existing_notes = report_doc.get("additional_notes", [])
        if not isinstance(existing_notes, list):
            existing_notes = [existing_notes] if existing_notes else []
        existing_notes.append({
            "note": note,
            "added_at": now.isoformat(),
        })
        update_fields["additional_notes"] = existing_notes
        changes.append(f"Citizen note added: '{note[:60]}...'")

    if not update_fields:
        # No changes submitted, return existing report
        return await get_emergency_report(clean_id, db=db)

    update_fields["updated_at"] = now
    await db["citizen_reports"].update_one(
        {"report_id": clean_id},
        {"$set": update_fields}
    )

    # 4. Audit Timeline Event
    try:
        await record_timeline_event(
            db=db,
            report_id=clean_id,
            event_type=TimelineEventType.CITIZEN_REPORT_MODIFIED,
            details=f"Citizen modified report details: {'; '.join(changes)}",
            actor_id=report_doc.get("citizen_id", "CIT-ANON"),
            actor_name=update_fields.get("citizen_name") or report_doc.get("citizen_name", "Citizen"),
            actor_role=UserRole.CITIZEN,
        )
    except Exception as tl_err:
        logger.warning(f"Timeline event recording notice for report modification {clean_id}: {tl_err}")

    # 5. Safety Guidance Re-Evaluation (if description or impact level changed)
    if "description" in update_fields or "citizen_impact_level" in update_fields:
        try:
            from app.services.agents.adapters.safety_guidance_agent import SafetyGuidanceAgent
            await SafetyGuidanceAgent.generate_safety_guidance(
                report_id=clean_id,
                db=db,
                force_refresh=True,
                change_reason=f"Citizen updated report: {'; '.join(changes)}"
            )
        except Exception as g_err:
            logger.warning(f"Safety guidance re-generation notice for modified report {clean_id}: {g_err}")

    # 6. Return updated report doc
    return await get_emergency_report(clean_id, db=db)


@router.get("/reports/{report_id}/evidence-verification", response_model=EvidenceVerificationResult)
async def get_report_evidence_verification(
    report_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Authoritative Evidence Trust & Verification Result (Phase A).
    Returns explainable verified factors, missing factors, spatial validation distance,
    temporal freshness, duplicate status, and advisory recommendations.
    """
    clean_id = report_id.strip().upper()
    result = await EvidenceVerificationService.get_or_evaluate_report_verification(clean_id, db)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report with ID '{report_id}' not found.",
        )
    return result


@router.get("/reports/{report_id}/corroboration", response_model=CorroborationResult)
async def get_report_corroboration(
    report_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Multi-Source Corroboration & Conflict Detection (Phase B).
    Evaluates peer citizen reports, live camera evidence, IoT sensor events, and field updates.
    Returns deterministic supporting/conflicting/neutral source breakdown and explainable conflict analysis.
    """
    clean_id = report_id.strip().upper()
    result = await EvidenceCorroborationService.get_or_evaluate_report_corroboration(clean_id, db)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report with ID '{report_id}' not found.",
        )
    return result


@router.get("/reports/{report_id}/evolution-timeline", response_model=IncidentEvolutionTimelineResponse)
async def get_report_evolution_timeline(
    report_id: str,
    order: str = Query("asc", description="Sort order: 'asc' or 'desc'"),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> IncidentEvolutionTimelineResponse:
    """
    Incident Evolution Timeline (Phase C).
    Aggregates report intake, evidence validation, corroboration, field verification,
    and operational milestone events chronologically from genuine database records.
    """
    clean_id = report_id.strip().upper()
    rep_doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not rep_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report with ID '{report_id}' not found.",
        )
    from app.services.incident_evolution_service import IncidentEvolutionService
    return await IncidentEvolutionService.get_evolution_timeline(
        target_id=clean_id,
        db=db,
        order=order,
    )




