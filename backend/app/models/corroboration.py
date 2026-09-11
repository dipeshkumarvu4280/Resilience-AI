import secrets
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.models.enums import (
    CorroborationStatus,
    CorroborationSourceType,
    CorroborationSpatialRelationship,
    CorroborationTemporalRelationship,
    CorroborationAlignment,
    EvidenceConflictCategory,
)


def generate_conflict_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"CFL-{suffix}"


class CorroboratingSource(BaseModel):
    source_type: CorroborationSourceType
    source_id: str
    source_name: Optional[str] = None
    summary: str
    alignment: CorroborationAlignment  # SUPPORTING, NEUTRAL, CONFLICTING
    spatial_relationship: CorroborationSpatialRelationship = CorroborationSpatialRelationship.UNAVAILABLE
    distance_meters: Optional[float] = None
    temporal_relationship: CorroborationTemporalRelationship = CorroborationTemporalRelationship.UNAVAILABLE
    time_difference_seconds: Optional[float] = None
    timestamp: Optional[datetime] = None
    
    # Sensor specific metadata (when source_type == SENSOR_EVENT)
    sensor_type: Optional[str] = None
    reading_value: Optional[float] = None
    reading_unit: Optional[str] = None
    threshold: Optional[float] = None
    is_breach: Optional[bool] = None
    coverage_radius_meters: Optional[float] = None
    within_coverage: Optional[bool] = None
    
    # Generic structured details
    details: Dict[str, Any] = Field(default_factory=dict)


class ConflictDetail(BaseModel):
    conflict_id: str = Field(default_factory=generate_conflict_id)
    category: EvidenceConflictCategory
    conflicting_source_id: str
    conflicting_source_type: CorroborationSourceType
    conflicting_source_name: Optional[str] = None
    summary: str
    reason: str
    severity: str = "HIGH"
    recommended_action: str


class CorroborationResult(BaseModel):
    target_id: str
    target_type: str = "CITIZEN_REPORT"  # "CITIZEN_REPORT" or "SITUATION"
    corroboration_status: CorroborationStatus = CorroborationStatus.NO_CORROBORATION
    total_sources_evaluated: int = 0
    supporting_source_count: int = 0
    conflicting_source_count: int = 0
    neutral_source_count: int = 0
    supporting_sources: List[CorroboratingSource] = Field(default_factory=list)
    conflicting_sources: List[CorroboratingSource] = Field(default_factory=list)
    neutral_sources: List[CorroboratingSource] = Field(default_factory=list)
    conflict_details: List[ConflictDetail] = Field(default_factory=list)
    corroboration_factors: List[str] = Field(default_factory=list)
    conflict_factors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    explanation: str
    recommendations: List[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
