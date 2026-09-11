import secrets
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.enums import (
    EmergencyType,
    SeverityLevel,
    SituationStatus,
    AssessmentStatus,
    OfficerReviewAction,
)
from app.models.citizen import MediaAttachment


def generate_situation_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"SIT-{suffix}"


def generate_cluster_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"CLS-{suffix}"


def generate_assessment_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"ASM-{suffix}"


class SituationLocationCenter(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    address: Optional[str] = None
    street_address: Optional[str] = None
    landmark: Optional[str] = None
    zone_or_district: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None


class ImpactZone(BaseModel):
    center_latitude: float = Field(..., ge=-90.0, le=90.0)
    center_longitude: float = Field(..., ge=-180.0, le=180.0)
    radius_km: float = Field(..., ge=0.05, le=100.0, description="Estimated impact radius in kilometers")
    affected_zone_name: Optional[str] = None
    bounding_box: Optional[Dict[str, float]] = None
    is_estimated: bool = True
    estimation_rationale: Optional[str] = "Estimated from geographic cluster spread and hazard dispersion range."


class SituationAssessment(BaseModel):
    assessment_id: str = Field(default_factory=generate_assessment_id)
    situation_id: str
    severity_score: float = Field(..., ge=0.0, le=10.0, description="Explainable severity score (0.0 to 10.0)")
    severity_level: SeverityLevel
    estimated_affected_population: int = Field(..., ge=0)
    impact_radius_km: float = Field(..., ge=0.05, le=100.0)
    hazard_risk: str
    key_factors: List[str] = Field(default_factory=list)
    situation_summary: str
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in assessment based on evidence (0.0 to 1.0)")
    recommendations: List[str] = Field(default_factory=list)
    is_ai_generated: bool = False
    ai_provider: Optional[str] = None
    generated_by: str = "Deterministic Assessment Engine"
    created_at: datetime
    updated_at: datetime


class OfficerSituationReview(BaseModel):
    reviewed_by_id: str
    reviewed_by_name: str
    action: OfficerReviewAction
    operational_severity_level: SeverityLevel
    operational_severity_score: float = Field(..., ge=0.0, le=10.0)
    notes: Optional[str] = None
    reviewed_at: datetime


class OfficerSituationReviewRequest(BaseModel):
    action: OfficerReviewAction
    modified_severity_level: Optional[SeverityLevel] = None
    modified_severity_score: Optional[float] = Field(None, ge=0.0, le=10.0)
    notes: Optional[str] = Field(None, max_length=2000)
    reset_override: Optional[bool] = False


class ClusteredReportSummary(BaseModel):
    report_id: str
    emergency_type: EmergencyType
    description: str
    citizen_name: str
    citizen_phone: str
    latitude: float
    longitude: float
    address: Optional[str] = None
    zone_or_district: Optional[str] = None
    distance_to_center_km: float = 0.0
    status: str
    priority: str
    created_at: datetime
    media: List[MediaAttachment] = Field(default_factory=list)


class SituationCluster(BaseModel):
    situation_id: str
    cluster_id: str
    title: str
    emergency_type: EmergencyType
    primary_report_id: str
    report_ids: List[str] = Field(default_factory=list)
    report_count: int = 1
    center_location: SituationLocationCenter
    impact_zone: ImpactZone
    status: SituationStatus = SituationStatus.ACTIVE
    assessment_status: AssessmentStatus = AssessmentStatus.PENDING
    
    # Effective operational severity (officer override if set, otherwise computed severity)
    severity_score: float = 0.0
    severity_level: SeverityLevel = SeverityLevel.LOW
    
    # Deterministic / AI engine computed severity
    computed_severity_score: float = 0.0
    computed_severity_level: SeverityLevel = SeverityLevel.LOW
    
    # Authenticated Emergency Officer override
    officer_override_severity: Optional[SeverityLevel] = None
    officer_override_score: Optional[float] = None
    officer_override_by: Optional[str] = None
    officer_override_by_id: Optional[str] = None
    officer_override_at: Optional[datetime] = None
    officer_override_notes: Optional[str] = None
    
    estimated_affected_population: int = 0
    hazard_risk: str = "General Emergency Monitoring"
    confidence: float = 0.5
    situation_summary: str = "Situation detected from emergency report intake."
    assessment: Optional[SituationAssessment] = None
    officer_review: Optional[OfficerSituationReview] = None
    clustering_reasoning: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SensorEvidenceSummary(BaseModel):
    source_type: str = "SIMULATED_SENSOR"
    source_id: str
    sensor_id: str
    sensor_name: str
    sensor_type: str
    event_id: Optional[str] = None
    reading_id: Optional[str] = None
    value: float
    current_value: float
    previous_value: Optional[float] = None
    unit: str
    threshold: float
    threshold_state: str  # e.g. "BREACHED", "RECOVERED", "NORMAL", "CONTINUED_BREACH"
    is_breach: bool = False
    timestamp: datetime
    latitude: float
    longitude: float
    location_name: Optional[str] = None
    sensor_address: Optional[str] = None
    coverage_radius_meters: Optional[float] = None
    coverage_radius_km: Optional[float] = None
    distance_to_center_km: float = 0.0
    correlation_reason: str
    confidence_contribution: float = 0.0
    is_simulated: bool = True


class SituationEvidenceResponse(BaseModel):
    total_sources: int = 0
    citizen_reports_count: int = 0
    sensor_events_count: int = 0
    citizen_reports: List[ClusteredReportSummary] = Field(default_factory=list)
    sensor_evidence: List[SensorEvidenceSummary] = Field(default_factory=list)


from app.models.corroboration import CorroborationResult


class SituationDetailResponse(BaseModel):
    situation: SituationCluster
    clustered_reports: List[ClusteredReportSummary] = Field(default_factory=list)
    sensor_evidence: List[SensorEvidenceSummary] = Field(default_factory=list)
    evidence: Optional[SituationEvidenceResponse] = None
    corroboration: Optional[CorroborationResult] = None



class PaginatedSituationsResponse(BaseModel):
    items: List[SituationCluster]
    total: int
    page: int
    limit: int
    total_pages: int


class SituationStatsResponse(BaseModel):
    total_situations: int = 0
    active_situations: int = 0
    critical_situations: int = 0
    high_situations: int = 0
    total_clustered_reports: int = 0
    average_confidence: float = 0.0
