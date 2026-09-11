from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from app.models.enums import SeverityLevel, EmergencyType, ReportStatus, SituationStatus
from app.models.citizen import LocationPayload
from app.models.situation import SituationCluster
from app.models.officer import OfficerReportDetailResponse
from app.models.resource import ResourceResponse


class PublicEmergencyHotspot(BaseModel):
    hotspot_id: str
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    severity_level: SeverityLevel = SeverityLevel.MEDIUM
    impact_radius_km: float = 1.5
    active_incident_count: int = 1
    emergency_type: Optional[EmergencyType] = None
    general_area_name: Optional[str] = "Operational Response Sector"
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PublicActiveHotspotsResponse(BaseModel):
    hotspots: List[PublicEmergencyHotspot] = Field(default_factory=list)
    total_active_hotspots: int = 0
    total_active_incidents: int = 0
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OfficerMapDataResponse(BaseModel):
    view_mode: str = "active"  # "active", "history", "all"
    situations: List[SituationCluster] = Field(default_factory=list)
    reports: List[OfficerReportDetailResponse] = Field(default_factory=list)
    shelters: List[ResourceResponse] = Field(default_factory=list)
    total_active_situations: int = 0
    total_resolved_situations: int = 0
    total_active_reports: int = 0
    total_resolved_reports: int = 0
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
