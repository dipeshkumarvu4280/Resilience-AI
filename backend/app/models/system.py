from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.enums import ServiceStatus


class ServiceInfo(BaseModel):
    name: str
    status: ServiceStatus
    phase: str
    description: str
    last_check: datetime = Field(default_factory=datetime.utcnow)
    details: Optional[str] = None


class SystemHealthResponse(BaseModel):
    system_name: str = "RESILIENCE"
    environment: str = "production-foundation"
    version: str = "v0.9.0-operations"
    overall_status: str = "OPERATIONAL"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    active_phase: str = "Phase 9 (Emergency Intelligence & Integrated Operations)"
    services: Dict[str, ServiceInfo]
    database_connected: bool


class PlatformConfigModel(BaseModel):
    system_name: str = "RESILIENCE AI"
    organization_name: str = "National Disaster Management Network"
    operational_mode: str = "ACTIVE_RESPONSE"
    spatial_cluster_radius_km: float = 3.5
    temporal_window_hours: int = 6
    ai_coordination_enabled: bool = True
    require_human_approval_for_dispatch: bool = True
    monitoring_poll_interval_sec: int = 15
    whatsapp_notifications_enabled: bool = True
    session_timeout_minutes: int = 120
    audit_retention_days: int = 365
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


class PlatformConfigUpdate(BaseModel):
    system_name: Optional[str] = None
    organization_name: Optional[str] = None
    operational_mode: Optional[str] = None
    spatial_cluster_radius_km: Optional[float] = None
    temporal_window_hours: Optional[int] = None
    ai_coordination_enabled: Optional[bool] = None
    require_human_approval_for_dispatch: Optional[bool] = None
    monitoring_poll_interval_sec: Optional[int] = None
    whatsapp_notifications_enabled: Optional[bool] = None
    session_timeout_minutes: Optional[int] = None
    audit_retention_days: Optional[int] = None
