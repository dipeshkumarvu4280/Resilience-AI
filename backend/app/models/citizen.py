from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.enums import (
    EmergencyType,
    ReportStatus,
    CitizenImpactLevel,
    EvidenceValidationStatus,
    ReportTrustState,
    VerificationStatus,
    EvidenceConfidenceBand,
    LocationMatchState,
    EvidenceFreshness,
    ReportCompleteness,
)


class CitizenOTPRequest(BaseModel):
    phone: str = Field(..., description="10-digit or valid phone number")
    name: Optional[str] = Field(None, description="Optional citizen name")


class CitizenOTPRequestResponse(BaseModel):
    message: str
    phone: str
    expires_in_seconds: int = 300
    cooldown_seconds: int = 60


class CitizenOTPVerifyRequest(BaseModel):
    phone: str
    otp: str


class CitizenOTPVerifyResponse(BaseModel):
    message: str
    phone: str
    citizen_id: str
    verification_token: str
    expires_in_seconds: int = 900


class LocationPayload(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    address: Optional[str] = None
    street_address: Optional[str] = None
    landmark: Optional[str] = None
    zone_or_district: Optional[str] = None
    district: Optional[str] = None
    display_name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    manual_zone: Optional[str] = None
    accuracy_meters: Optional[float] = None


class ReverseGeocodeResponse(BaseModel):
    latitude: float
    longitude: float
    address: Optional[str] = None
    street_address: Optional[str] = None
    landmark: Optional[str] = None
    zone_or_district: Optional[str] = None
    district: Optional[str] = None
    display_name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    resolved: bool = False


class MediaAttachment(BaseModel):
    filename: str
    file_url: str
    media_type: str
    size_bytes: int


class LiveEvidencePayload(BaseModel):
    image_base64: Optional[str] = Field(None, description="Base64 encoded live photo data URI or raw base64")
    capture_session_id: Optional[str] = None
    client_capture_timestamp: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy_meters: Optional[float] = None
    device_info: Optional[str] = None
    status: Optional[EvidenceValidationStatus] = EvidenceValidationStatus.VALIDATED
    error_reason: Optional[str] = None


class LiveEvidenceRecord(BaseModel):
    evidence_id: str
    report_id: Optional[str] = None
    evidence_type: str = "LIVE_CAMERA_PHOTO"
    source: str = "BROWSER_CAMERA"
    file_url: Optional[str] = None
    filename: Optional[str] = None
    content_hash: Optional[str] = None
    client_capture_timestamp: Optional[datetime] = None
    server_received_timestamp: datetime
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy_meters: Optional[float] = None
    distance_from_report_meters: Optional[float] = None
    capture_session_id: Optional[str] = None
    validation_status: EvidenceValidationStatus = EvidenceValidationStatus.VALIDATED
    trust_signals: List[str] = Field(default_factory=list)
    is_duplicate: bool = False
    duplicate_of_evidence_id: Optional[str] = None
    error_reason: Optional[str] = None


class EvidenceVerificationResult(BaseModel):
    report_id: str
    verification_status: VerificationStatus
    confidence_band: EvidenceConfidenceBand
    citizen_impact_level: CitizenImpactLevel = CitizenImpactLevel.NOT_SURE
    evidence_signals: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    verified_factors: List[str] = Field(default_factory=list)
    missing_factors: List[str] = Field(default_factory=list)
    location_match_state: LocationMatchState = LocationMatchState.UNAVAILABLE
    distance_from_report_meters: Optional[float] = None
    evidence_freshness: EvidenceFreshness = EvidenceFreshness.UNAVAILABLE
    evidence_age_seconds: Optional[float] = None
    report_completeness: ReportCompleteness = ReportCompleteness.INCOMPLETE
    recommendations: List[str] = Field(default_factory=list)
    has_live_photo: bool = False
    content_hash: Optional[str] = None
    is_duplicate: bool = False
    duplicate_of_report_id: Optional[str] = None
    last_evaluated_at: datetime


class EmergencyReportCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=7, max_length=20)
    emergency_type: EmergencyType
    citizen_impact_level: CitizenImpactLevel = Field(
        default=CitizenImpactLevel.NOT_SURE,
        description="Citizen-declared impact severity (LOW, MEDIUM, HIGH, CRITICAL, NOT_SURE)"
    )
    description: str = Field(..., min_length=10, max_length=3000)
    location: LocationPayload
    verification_token: Optional[str] = None
    bot_honeypot: Optional[str] = None
    media: Optional[List[MediaAttachment]] = Field(default_factory=list)
    evidence: Optional[LiveEvidencePayload] = None


from app.models.corroboration import CorroborationResult
from app.models.llm_extraction import LLMExtractionResult
from app.models.visual_evidence import VisualEvidenceAnalysis


class EmergencyReportResponse(BaseModel):
    report_id: str
    citizen_id: str
    citizen_name: str
    citizen_phone: str
    emergency_type: EmergencyType
    citizen_impact_level: CitizenImpactLevel = CitizenImpactLevel.NOT_SURE
    description: str
    location: LocationPayload
    media: List[MediaAttachment] = Field(default_factory=list)
    evidence: Optional[LiveEvidenceRecord] = None
    evidence_verification: Optional[EvidenceVerificationResult] = None
    corroboration: Optional[CorroborationResult] = None
    llm_extraction: Optional[LLMExtractionResult] = None
    visual_evidence: Optional[VisualEvidenceAnalysis] = None
    status: ReportStatus = ReportStatus.RECEIVED
    phone_verified: bool = False
    possible_duplicate: bool = False
    risk_level: str = "LOW"
    risk_reasons: List[str] = Field(default_factory=list)
    trust_state: ReportTrustState = ReportTrustState.NORMAL
    trust_signals: List[str] = Field(default_factory=list)
    situation_id: Optional[str] = None
    safety_guidance_id: Optional[str] = None
    safety_guidance_token: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CitizenReportUpdateRequest(BaseModel):
    citizen_token: Optional[str] = Field(None, description="Secure safety guidance token or verification token for authorization")
    description: Optional[str] = Field(None, min_length=10, max_length=3000, description="Updated or additional incident description")
    citizen_impact_level: Optional[CitizenImpactLevel] = Field(None, description="Updated citizen-declared impact severity")
    full_name: Optional[str] = Field(None, min_length=2, max_length=100, description="Updated citizen contact name")
    phone: Optional[str] = Field(None, min_length=7, max_length=20, description="Updated contact phone number")
    additional_notes: Optional[str] = Field(None, max_length=1000, description="Additional notes or updates from citizen")






