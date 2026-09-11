from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.enums import (
    EmergencyType,
    ReportStatus,
    ReportPriority,
    TimelineEventType,
    UserRole,
    CitizenImpactLevel,
    EvidenceValidationStatus,
    ReportTrustState,
)
from app.models.citizen import (
    LocationPayload,
    MediaAttachment,
    LiveEvidenceRecord,
    EvidenceVerificationResult,
)


class OfficerNote(BaseModel):
    note_id: str
    author_id: str
    author_name: str
    author_role: UserRole
    note: str
    created_at: datetime


class TimelineEvent(BaseModel):
    event_id: str
    event_type: TimelineEventType
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None
    details: str
    previous_value: Optional[str] = None
    new_value: Optional[str] = None
    timestamp: datetime


class ReportPriorityUpdateRequest(BaseModel):
    priority: ReportPriority


class ReportStatusUpdateRequest(BaseModel):
    status: ReportStatus
    reason: Optional[str] = None


class OfficerNoteCreateRequest(BaseModel):
    note: str = Field(..., min_length=2, max_length=2000)


class OfficerReportStatsResponse(BaseModel):
    total_incoming: int = 0
    acknowledged: int = 0
    under_assessment: int = 0
    action_required: int = 0
    resolved: int = 0
    total_reports: int = 0


from app.models.corroboration import CorroborationResult
from app.models.llm_extraction import LLMExtractionResult
from app.models.visual_evidence import VisualEvidenceAnalysis


class OfficerReportDetailResponse(BaseModel):
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
    priority_recommendation: Optional[Dict[str, Any]] = None
    status: ReportStatus
    priority: ReportPriority = ReportPriority.UNASSESSED
    phone_verified: bool = False
    possible_duplicate: bool = False
    risk_level: str = "LOW"
    risk_reasons: List[str] = Field(default_factory=list)
    trust_state: ReportTrustState = ReportTrustState.NORMAL
    trust_signals: List[str] = Field(default_factory=list)
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    situation_id: Optional[str] = None
    notes: List[OfficerNote] = Field(default_factory=list)
    timeline: List[TimelineEvent] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime



class PaginatedOfficerReportsResponse(BaseModel):
    items: List[OfficerReportDetailResponse]
    total: int
    page: int
    limit: int
    total_pages: int
