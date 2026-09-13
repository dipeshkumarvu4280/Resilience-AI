from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.models.enums import SeverityLevel


from app.models.weather import WeatherEvidence, WeatherForecastPeriod


class PredictiveDataSufficiency(str):
    SUFFICIENT_DATA = "SUFFICIENT_DATA"
    LIMITED_DATA = "LIMITED_DATA"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NO_DATA = "NO_DATA"


class EscalationRiskLevel(str):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TrendDirection(str):
    RISING = "RISING"
    STABLE = "STABLE"
    FALLING = "FALLING"
    UNKNOWN = "UNKNOWN"


class PredictiveFeature(BaseModel):
    name: str = Field(..., description="Canonical feature identifier")
    value: float = Field(..., description="Deterministic numeric value of the feature")
    source: str = Field(..., description="Underlying database source collection or domain")
    time_window: str = Field(..., description="Time window evaluated, e.g. '60m', '6h', '24h'")
    data_points: int = Field(default=0, description="Genuine database records evaluated for this feature")
    raw_records: Optional[int] = Field(None, description="Total raw measurement records aggregated")
    aggregation_method: Optional[str] = Field(None, description="Method used to aggregate raw time-series records")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Detailed time-series telemetry metrics")
    description: Optional[str] = Field(None, description="Human-readable explanation of the feature")


class PredictiveEvidenceItem(BaseModel):
    source_type: str = Field(..., description="Source domain: CITIZEN_REPORT, SENSOR, FIELD_VERIFICATION, MONITORING, TASK_PRESSURE, WEATHER_API")
    source_id: str = Field(..., description="Exact database record ID or identifier")
    timestamp: datetime = Field(..., description="Authoritative timestamp of the evidence")
    contribution: str = Field(..., description="Explainable contribution description")
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Evidentiary weight applied")


class ForecastHorizonResult(BaseModel):
    horizon_minutes: int = Field(..., description="Forecast horizon in minutes: 15, 30, or 60")
    risk_level: str = Field(..., description="Deterministic risk level: LOW, MEDIUM, HIGH, CRITICAL")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Normalized risk score from 0.0 to 1.0 (capped at 0.98)")
    raw_score: Optional[float] = Field(None, description="Uncapped continuous raw projected score")
    projected_score: Optional[float] = Field(None, description="Uncapped continuous raw projected score")
    is_capped: bool = Field(default=False, description="Whether projection reached the advisory ceiling (0.98)")
    ceiling_threshold: float = Field(default=0.98, description="Maximum bounded advisory risk ceiling")
    trend: str = Field(..., description="Observed temporal trend: RISING, STABLE, FALLING, UNKNOWN")
    data_status: str = Field(..., description="Sufficiency status: SUFFICIENT_DATA, LIMITED_DATA, INSUFFICIENT_DATA, NO_DATA")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in forecast based on data availability")
    confidence_label: str = Field(..., description="Confidence tier: LOW, MEDIUM, HIGH")
    contributing_factors: List[str] = Field(default_factory=list, description="Top genuine contributing signals")
    limitations: List[str] = Field(default_factory=list, description="Honest limitations or missing signals")
    
    # Exact Deterministic Signal Contributions
    weather_contribution: Optional[float] = Field(None, description="Advisory risk component from real weather observation & forecast")
    sensor_contribution: Optional[float] = Field(None, description="Advisory risk component from IoT sensor telemetry")
    incident_contribution: Optional[float] = Field(None, description="Advisory risk component from citizen report velocity")
    field_contribution: Optional[float] = Field(None, description="Advisory risk component from ground verifications")
    monitoring_contribution: Optional[float] = Field(None, description="Advisory risk component from telemetry events")
    task_contribution: Optional[float] = Field(None, description="Advisory risk component from task blockage pressure")
    weather_forecast: Optional[WeatherForecastPeriod] = Field(None, description="Aligned weather forecast period for this horizon")


class IncidentPredictionResponse(BaseModel):
    incident_id: str = Field(..., description="Target situation or report ID")
    incident_title: Optional[str] = Field(None, description="Descriptive title of the incident")
    emergency_type: Optional[str] = Field(None, description="Type of hazard/emergency")
    prediction_status: str = Field(..., description="AVAILABLE, LIMITED, INSUFFICIENT_DATA, NO_DATA")
    data_status: str = Field(..., description="Data sufficiency status")
    
    # Authoritative Current State (strictly separate from prediction)
    current_authoritative_severity: str = Field(..., description="Current operational severity: LOW, MEDIUM, HIGH, CRITICAL")
    current_severity_score: float = Field(..., description="Current authoritative severity score 0.0-10.0")
    is_officer_override: bool = Field(default=False, description="Whether current severity was set by officer override")
    
    # Primary Forecast (default horizon, typically 30m)
    forecast: ForecastHorizonResult = Field(..., description="Primary advisory forecast")
    
    # Multiple Horizons (15m, 30m, 60m)
    horizons: Dict[str, ForecastHorizonResult] = Field(default_factory=dict, description="Forecast breakdown by horizon (15m, 30m, 60m)")
    all_horizons_capped: bool = Field(default=False, description="Whether 15m, 30m, and 60m all reached advisory ceiling (0.98)")
    
    # Source Independence
    independent_sources_count: int = Field(default=0, description="Deduplicated independent physical sources (sensors, reports, field, monitoring)")
    independent_physical_sources_count: int = Field(default=0, description="Deduplicated physical corroboration sources")
    external_context_sources_count: int = Field(default=0, description="External context evidence sources (e.g. weather API)")
    
    # Real Weather Intelligence Evidence
    weather: Optional[WeatherEvidence] = Field(None, description="Location-specific genuine weather observation and forecast")
    
    # Explainability & Provenance
    features: List[PredictiveFeature] = Field(default_factory=list, description="Extracted explainable features")
    missing_features: List[str] = Field(default_factory=list, description="Features unavailable due to lack of sensors/events")
    evidence: List[PredictiveEvidenceItem] = Field(default_factory=list, description="Genuine corroborating evidence items")
    data_points_used: Dict[str, int] = Field(default_factory=dict, description="Counts of genuine database records evaluated")
    
    # Model Metadata & Safety Notices
    historical_window_minutes: int = Field(default=60, description="Historical observation window in minutes")
    model: Dict[str, str] = Field(default_factory=lambda: {
        "name": "deterministic_escalation_v1",
        "version": "1.0",
        "type": "Deterministic Predictive Intelligence Engine",
        "method": "Temporal Rate, Atmospheric Context & Weighted Multi-Source Signal Synthesis",
    })
    limitations: List[str] = Field(default_factory=list)
    advisory_notice: str = Field(
        default="ADVISORY ONLY: Predictive Analysis estimates escalation risk from genuine temporal trends and atmospheric conditions. It does NOT automatically change authoritative severity, allocate resources, or dispatch responders. Emergency Officer verification remains mandatory."
    )
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PredictiveTrendPoint(BaseModel):
    time_label: str
    minutes_from_now: int
    risk_score: float
    risk_level: str
    is_forecast: bool
    data_status: str


class PredictiveTrendResponse(BaseModel):
    incident_id: str
    data_status: str
    trend_direction: str
    historical_window_minutes: int
    timeline_points: List[PredictiveTrendPoint] = Field(default_factory=list)
    summary: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PredictiveFeaturesResponse(BaseModel):
    incident_id: str
    historical_window_minutes: int
    data_status: str
    features: List[PredictiveFeature] = Field(default_factory=list)
    missing_features: List[str] = Field(default_factory=list)
    total_records_evaluated: int = 0
    records_by_source: Dict[str, int] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PredictiveHealthResponse(BaseModel):
    status: str = "HEALTHY"
    engine_version: str = "1.0-phase1"
    model_name: str = "deterministic_escalation_v1"
    supported_horizons_minutes: List[int] = Field(default_factory=lambda: [15, 30, 60])
    default_window_minutes: int = 60
    zero_dummy_data_enforced: bool = True
    advisory_mode_enforced: bool = True
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
