import secrets
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.models.enums import (
    UserRole,
    FieldVerificationStatus,
    FieldObservationCategory,
    LocationMatchState,
)
from app.models.citizen import LocationPayload, LiveEvidencePayload, LiveEvidenceRecord


def generate_verification_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"FLV-{suffix}"


class FieldVerificationCreateRequest(BaseModel):
    target_id: str = Field(..., description="Report ID (RES-XXXX) or Situation ID (SIT-XXXX)")
    target_type: str = Field("CITIZEN_REPORT", description="CITIZEN_REPORT or SITUATION")
    verification_status: FieldVerificationStatus = Field(..., description="Ground truth verification status")
    observation_category: FieldObservationCategory = Field(..., description="Structured ground observation category")
    notes: Optional[str] = Field(None, description="Detailed field notes from ground responder")
    location: Optional[LocationPayload] = Field(None, description="Current GPS coordinates of responder")
    evidence: Optional[LiveEvidencePayload] = Field(None, description="Optional photographic evidence captured on site")
    task_id: Optional[str] = Field(None, description="Optional associated response task ID")
    observed_at: Optional[datetime] = Field(None, description="Timestamp of actual observation")


class FieldVerificationRecord(BaseModel):
    verification_id: str
    target_id: str
    target_type: str  # CITIZEN_REPORT or SITUATION
    responder_id: str
    responder_name: str
    responder_role: UserRole
    verification_status: FieldVerificationStatus
    observation_category: FieldObservationCategory
    notes: str = ""
    location: Optional[LocationPayload] = None
    distance_from_target_meters: Optional[float] = None
    location_match_state: LocationMatchState = LocationMatchState.UNAVAILABLE
    evidence: Optional[LiveEvidenceRecord] = None
    task_id: Optional[str] = None
    observed_at: datetime
    submitted_at: datetime
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PaginatedFieldVerificationsResponse(BaseModel):
    items: List[FieldVerificationRecord]
    total: int
    page: int
    limit: int
    total_pages: int
