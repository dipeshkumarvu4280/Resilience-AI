import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.models.enums import (
    SeverityLevel,
    DestinationType,
    RouteStatus,
    PushSubscriptionStatus,
    GuidanceApprovalState,
    SafetyNotificationType,
    GuidanceStatus,
)


def generate_guidance_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"GUD-{suffix}"


def generate_secure_access_token() -> str:
    return secrets.token_urlsafe(32)


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    keys: PushKeys
    user_agent: Optional[str] = None
    report_id: Optional[str] = None
    session_id: Optional[str] = None


class PushUnsubscribeRequest(BaseModel):
    endpoint: Optional[str] = None


class PushSubscriptionRecord(BaseModel):
    subscription_id: str
    endpoint: str
    p256dh: str
    auth: str
    user_agent: Optional[str] = None
    status: PushSubscriptionStatus = PushSubscriptionStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    report_ids: List[str] = Field(default_factory=list)
    session_ids: List[str] = Field(default_factory=list)
    subscription_fingerprint: str = ""

    @classmethod
    def compute_fingerprint(cls, endpoint: str, p256dh: str) -> str:
        raw = f"{endpoint}:{p256dh}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PushDeliveryRecord(BaseModel):
    delivery_id: str
    idempotency_key: str
    event_id: str
    recipient_endpoint: str
    notification_type: SafetyNotificationType
    guidance_version: int
    delivered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "DELIVERED"


class VerifiedDestination(BaseModel):
    destination_id: str
    destination_name: str
    destination_type: DestinationType
    latitude: float
    longitude: float
    address_or_landmark: str = "Verified Emergency Response Site"
    distance_km: float = Field(..., ge=0.0)
    available_capacity: Optional[float] = None
    total_capacity: Optional[float] = None
    operational_status: str = "OPERATIONAL"
    suitability_reason: str = "Geographically closest verified operational facility."
    contact_phone: Optional[str] = None
    place_id: Optional[str] = None
    provider: Optional[str] = "Live Discovery / Verified DB"
    last_checked: Optional[datetime] = None
    estimated_drive_minutes: Optional[float] = None
    rating: Optional[float] = None
    open_now: Optional[bool] = None


class HazardAvoidanceZone(BaseModel):
    hazard_id: str
    hazard_type: str
    latitude: float
    longitude: float
    radius_km: float = 1.0
    warning_message: str


class RouteDetails(BaseModel):
    origin_latitude: float
    origin_longitude: float
    destination_latitude: float
    destination_longitude: float
    distance_km: float = Field(..., ge=0.0)
    estimated_duration_minutes: float = Field(..., ge=0.0)
    route_status: RouteStatus = RouteStatus.CALCULATED
    polyline_points: List[List[float]] = Field(default_factory=list, description="Array of [lat, lng] coordinates")
    encoded_polyline: Optional[str] = Field(default=None, description="Authoritative Google Routes encoded polyline")
    route_warnings: List[str] = Field(default_factory=list)
    avoid_areas: List[HazardAvoidanceZone] = Field(default_factory=list)
    provider: str = "Google Maps Road Network (Driving)"
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CitizenSafetyGuidance(BaseModel):
    """
    Structured, contextual Citizen Safety Guidance model.
    CRITICAL CONSTRAINTS:
    - Purely advisory for civilian safety.
    - Zero hallucinated destinations or hardcoded routes.
    - Preserves uncertainty: explicit status if facility or route unavailable.
    - Immutable versioning: V1, V2, V3 with auditable supersession.
    - HITL gate: critical evacuation directives require officer approval.
    """
    guidance_id: str = Field(default_factory=generate_guidance_id)
    secure_access_token: str = Field(default_factory=generate_secure_access_token)
    report_id: str
    situation_id: Optional[str] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until: datetime = Field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=4))
    status: str = "ACTIVE"
    emergency_type: str
    risk_level: SeverityLevel = SeverityLevel.MEDIUM
    immediate_actions: List[str] = Field(default_factory=list)
    precautions: List[str] = Field(default_factory=list)
    recommended_destination: Optional[VerifiedDestination] = None
    nearby_alternatives: List[VerifiedDestination] = Field(default_factory=list)
    destination_reason: Optional[str] = None
    route: Optional[RouteDetails] = None
    route_warnings: List[str] = Field(default_factory=list)
    avoid_locations: List[HazardAvoidanceZone] = Field(default_factory=list)
    confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    evidence_references: List[str] = Field(default_factory=list)
    requires_officer_approval: bool = False
    approval_state: GuidanceApprovalState = GuidanceApprovalState.AUTO_PUBLISHED
    officer_review_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    version: int = 1
    supersedes_guidance_id: Optional[str] = None
    superseded_by_guidance_id: Optional[str] = None
    trigger_event_id: Optional[str] = None
    change_reason: Optional[str] = None
    is_stale: bool = False
    history: List[Dict[str, Any]] = Field(default_factory=list)


class CitizenSafetyGuidanceResponse(BaseModel):
    success: bool = True
    guidance: Optional[CitizenSafetyGuidance] = None
    secure_access_token: Optional[str] = None
    message: str = "Safety guidance retrieved successfully."
    latest_active_token: Optional[str] = None


class SafetyGuidanceReviewRequest(BaseModel):
    action: str = Field(..., description="APPROVE, MODIFY, REJECT")
    modified_actions: Optional[List[str]] = None
    modified_precautions: Optional[List[str]] = None
    officer_notes: Optional[str] = None


class PushNotificationPayload(BaseModel):
    title: str
    body: str
    icon: str = "/favicon.svg"
    badge: str = "/favicon.svg"
    url: str
    tag: str = "emergency-safety-guidance"
    urgency: str = "high"
    notification_type: Optional[SafetyNotificationType] = None
    data: Dict[str, Any] = Field(default_factory=dict)

