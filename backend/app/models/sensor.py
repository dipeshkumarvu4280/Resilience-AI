import secrets
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    SensorType,
    SensorStatus,
    SensorReadingSource,
    SensorAlertStatus,
    SimulationTrend,
    SeverityLevel,
    SensorReportingState,
    SensorHealthState,
)


def generate_sensor_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"SNS-{suffix}"


def generate_reading_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"SRD-{suffix}"


def generate_sensor_alert_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"SALT-{suffix}"


def generate_session_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"SSES-{suffix}"


DEFAULT_SENSOR_UNITS: Dict[SensorType, str] = {
    SensorType.WATER_LEVEL: "meters",
    SensorType.RAINFALL: "mm/hr",
    SensorType.TEMPERATURE: "°C",
    SensorType.SMOKE_AIR_QUALITY: "AQI",
    SensorType.AQI: "AQI",
}


# --- Location & Coverage Domain Models ---

class SensorLocation(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Authoritative GPS latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Authoritative GPS longitude")
    address: Optional[str] = Field(None, max_length=250, description="Formatted address or location name")
    street_address: Optional[str] = Field(None, max_length=250)
    landmark: Optional[str] = Field(None, max_length=250)
    zone: Optional[str] = Field(None, max_length=150)
    district: Optional[str] = Field(None, max_length=150)
    city: Optional[str] = Field(None, max_length=150)
    state: Optional[str] = Field(None, max_length=150)
    country: Optional[str] = Field(None, max_length=150)
    postal_code: Optional[str] = Field(None, max_length=50)


class SensorCoverage(BaseModel):
    radius_meters: float = Field(..., gt=0, description="Normalized coverage radius in meters")
    display_value: Optional[float] = Field(None, description="User-configured numeric value")
    display_unit: Optional[str] = Field("km", description="Display unit ('m' or 'km')")

    @model_validator(mode="after")
    def validate_radius(self):
        import math
        if math.isnan(self.radius_meters) or math.isinf(self.radius_meters) or self.radius_meters <= 0:
            raise ValueError("Coverage radius_meters must be a finite positive number greater than 0.")
        if self.display_value is None:
            if self.radius_meters >= 1000:
                self.display_value = round(self.radius_meters / 1000.0, 2)
                self.display_unit = "km"
            else:
                self.display_value = round(self.radius_meters, 2)
                self.display_unit = "m"
        return self


# --- Request & DTO Models ---

class SensorCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150, description="Descriptive sensor name")
    sensor_type: SensorType
    location_name: Optional[str] = Field(None, max_length=200, description="Operational location or zone")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    location: Optional[SensorLocation] = None
    coverage_radius_value: Optional[float] = None
    coverage_radius_unit: Optional[str] = None
    coverage: Optional[SensorCoverage] = None
    unit: Optional[str] = Field(None, min_length=1, max_length=50)
    threshold: float = Field(..., description="Numerical critical threshold above which breach is detected")
    linked_situation_id: Optional[str] = Field(None, description="Optional linked situation ID")
    description: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def populate_and_validate_fields(self):
        import math
        # 1. Populate default measurement unit if missing
        if not self.unit:
            self.unit = DEFAULT_SENSOR_UNITS.get(self.sensor_type, "units")

        # 2. Reconcile location coordinates & address
        if self.location:
            self.latitude = self.location.latitude
            self.longitude = self.location.longitude
            if not self.location_name:
                self.location_name = self.location.address or self.location.city or self.location.zone or f"Location ({self.latitude:.4f}, {self.longitude:.4f})"
        else:
            if self.latitude is None or self.longitude is None:
                raise ValueError("Sensor physical coordinates (latitude and longitude) are required.")
            if math.isnan(self.latitude) or math.isinf(self.latitude) or not (-90.0 <= self.latitude <= 90.0):
                raise ValueError("Latitude must be a valid number between -90 and 90.")
            if math.isnan(self.longitude) or math.isinf(self.longitude) or not (-180.0 <= self.longitude <= 180.0):
                raise ValueError("Longitude must be a valid number between -180 and 180.")
            if not self.location_name:
                self.location_name = f"Location ({self.latitude:.4f}, {self.longitude:.4f})"
            self.location = SensorLocation(
                latitude=self.latitude,
                longitude=self.longitude,
                address=self.location_name,
            )

        # 3. Reconcile coverage radius
        if self.coverage:
            if math.isnan(self.coverage.radius_meters) or math.isinf(self.coverage.radius_meters) or self.coverage.radius_meters <= 0:
                raise ValueError("Coverage range / radius must be a positive number greater than 0.")
        elif self.coverage_radius_value is not None:
            if math.isnan(self.coverage_radius_value) or math.isinf(self.coverage_radius_value) or self.coverage_radius_value <= 0:
                raise ValueError("Coverage range / radius must be a positive number greater than 0.")
            raw_unit = (self.coverage_radius_unit or "km").strip().lower()
            allowed_units = {"m", "meter", "meters", "km", "kilometer", "kilometers"}
            if raw_unit not in allowed_units:
                raise ValueError(f"Invalid coverage radius unit '{self.coverage_radius_unit}'. Supported units: 'meters' (m) or 'kilometers' (km).")
            multiplier = 1000.0 if raw_unit in {"km", "kilometer", "kilometers"} else 1.0
            radius_m = self.coverage_radius_value * multiplier
            self.coverage = SensorCoverage(
                radius_meters=radius_m,
                display_value=self.coverage_radius_value,
                display_unit="km" if multiplier == 1000.0 else "m",
            )
        else:
            self.coverage = SensorCoverage(
                radius_meters=2000.0,
                display_value=2.0,
                display_unit="km",
            )

        return self


class SensorUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    sensor_type: Optional[SensorType] = None
    location_name: Optional[str] = Field(None, min_length=2, max_length=200)
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    location: Optional[SensorLocation] = None
    coverage_radius_value: Optional[float] = None
    coverage_radius_unit: Optional[str] = None
    coverage: Optional[SensorCoverage] = None
    unit: Optional[str] = Field(None, min_length=1, max_length=50)
    threshold: Optional[float] = None
    linked_situation_id: Optional[str] = None
    description: Optional[str] = None

    @model_validator(mode="after")
    def validate_update_fields(self):
        import math
        if self.latitude is not None:
            if math.isnan(self.latitude) or math.isinf(self.latitude) or not (-90.0 <= self.latitude <= 90.0):
                raise ValueError("Latitude must be a valid number between -90 and 90.")
        if self.longitude is not None:
            if math.isnan(self.longitude) or math.isinf(self.longitude) or not (-180.0 <= self.longitude <= 180.0):
                raise ValueError("Longitude must be a valid number between -180 and 180.")
        if self.coverage_radius_value is not None:
            if math.isnan(self.coverage_radius_value) or math.isinf(self.coverage_radius_value) or self.coverage_radius_value <= 0:
                raise ValueError("Coverage range / radius must be a positive number greater than 0.")
            raw_unit = (self.coverage_radius_unit or "km").strip().lower()
            allowed_units = {"m", "meter", "meters", "km", "kilometer", "kilometers"}
            if raw_unit not in allowed_units:
                raise ValueError(f"Invalid coverage radius unit '{self.coverage_radius_unit}'. Supported units: 'meters' (m) or 'kilometers' (km).")
            multiplier = 1000.0 if raw_unit in {"km", "kilometer", "kilometers"} else 1.0
            radius_m = self.coverage_radius_value * multiplier
            self.coverage = SensorCoverage(
                radius_meters=radius_m,
                display_value=self.coverage_radius_value,
                display_unit="km" if multiplier == 1000.0 else "m",
            )
        if self.coverage is not None:
            if math.isnan(self.coverage.radius_meters) or math.isinf(self.coverage.radius_meters) or self.coverage.radius_meters <= 0:
                raise ValueError("Coverage range / radius must be a positive number greater than 0.")
        return self


class SensorReadingCreate(BaseModel):
    value: float = Field(..., description="Numeric sensor reading value")
    source_type: SensorReadingSource = Field(default=SensorReadingSource.MANUAL_SIMULATION)
    simulation: bool = Field(default=True, description="Flag indicating simulated IoT reading")
    notes: Optional[str] = None


class LiveStreamStartRequest(BaseModel):
    starting_value: float = Field(..., description="Initial sensor reading to begin simulation from")
    min_value: float = Field(..., description="Lower bound for dynamic simulation")
    max_value: float = Field(..., description="Upper bound for dynamic simulation")
    interval_seconds: float = Field(default=5.0, ge=1.0, le=60.0, description="Interval in seconds between simulated emissions")
    trend: SimulationTrend = Field(default=SimulationTrend.RISING, description="Trajectory trend for simulated data")
    step_size: Optional[float] = Field(None, ge=0.01, le=100.0, description="Step increment/decrement per interval")

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.min_value >= self.max_value:
            raise ValueError("min_value must be strictly less than max_value")
        if self.starting_value < self.min_value or self.starting_value > self.max_value:
            raise ValueError("starting_value must be within [min_value, max_value] range")
        return self


# --- Domain & Persisted Models ---

class SensorReading(BaseModel):
    reading_id: str = Field(default_factory=generate_reading_id)
    sensor_id: str
    value: float
    unit: str
    previous_value: Optional[float] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_type: SensorReadingSource = SensorReadingSource.MANUAL_SIMULATION
    simulation: bool = True
    threshold: float
    is_breach: bool = False
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    notes: Optional[str] = None


class SensorAlert(BaseModel):
    alert_id: str = Field(default_factory=generate_sensor_alert_id)
    event_id: str
    sensor_id: str
    sensor_name: str
    sensor_type: SensorType
    reading_id: str
    severity: SeverityLevel
    threshold: float
    current_value: float
    previous_value: Optional[float] = None
    unit: str
    location_name: str
    latitude: float
    longitude: float
    coverage_radius_meters: Optional[float] = None
    situation_id: Optional[str] = None
    status: SensorAlertStatus = SensorAlertStatus.ACTIVE_BREACH
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None


class LiveStreamSession(BaseModel):
    session_id: str = Field(default_factory=generate_session_id)
    sensor_id: str
    status: str = "RUNNING"  # "RUNNING" or "STOPPED"
    started_by: Optional[str] = None
    started_by_name: Optional[str] = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stopped_at: Optional[datetime] = None
    configuration: Dict[str, Any] = Field(default_factory=dict)
    readings_emitted: int = 0


# --- Response Models ---

class SensorResponse(BaseModel):
    sensor_id: str
    name: str
    sensor_type: SensorType
    status: SensorStatus
    location_name: str
    latitude: float
    longitude: float
    location: Optional[SensorLocation] = None
    coverage: Optional[SensorCoverage] = None
    unit: str
    threshold: float
    current_reading: Optional[float] = None
    previous_reading: Optional[float] = None
    last_updated: Optional[datetime] = None
    in_alert: bool = False
    current_alert: Optional[Dict[str, Any]] = None
    linked_situation_id: Optional[str] = None
    active_stream_session_id: Optional[str] = None
    is_streaming: bool = False
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    description: Optional[str] = None


class PaginatedSensorsResponse(BaseModel):
    items: List[SensorResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class SensorStatsResponse(BaseModel):
    total_sensors: int = 0
    active_sensors: int = 0
    paused_sensors: int = 0
    inactive_sensors: int = 0
    draft_sensors: int = 0
    sensors_in_alert: int = 0
    total_readings_today: int = 0
    type_counts: Dict[str, int] = Field(default_factory=dict)


class PaginatedReadingsResponse(BaseModel):
    items: List[SensorReading]
    total: int
    page: int
    limit: int
    total_pages: int


class PaginatedAlertsResponse(BaseModel):
    items: List[SensorAlert]
    total: int
    page: int
    limit: int
    total_pages: int


class LiveStreamSessionResponse(BaseModel):
    session_id: str
    sensor_id: str
    status: str
    started_at: datetime
    stopped_at: Optional[datetime] = None
    configuration: Dict[str, Any]
    readings_emitted: int


# --- Phase D: Sensor Health & Stale Data Intelligence Models ---

class SensorHealthDetail(BaseModel):
    sensor_id: str
    name: str
    sensor_type: SensorType
    status: SensorStatus
    location_name: str
    latitude: float
    longitude: float
    location: Optional[SensorLocation] = None
    coverage: Optional[SensorCoverage] = None
    unit: str
    threshold: float
    reporting_state: SensorReportingState
    health_state: SensorHealthState
    last_reading_at: Optional[datetime] = None
    reading_age_seconds: Optional[float] = None
    reading_age_human: str = "Never reported"
    stale_threshold_seconds: float = 300.0
    latest_reading_id: Optional[str] = None
    latest_reading_value: Optional[float] = None
    previous_reading_value: Optional[float] = None
    is_breach: bool = False
    in_alert: bool = False
    current_alert_id: Optional[str] = None
    linked_situation_id: Optional[str] = None
    is_usable_for_intelligence: bool = False
    reliability_score: float = 0.0
    reason: str = "No readings received."
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SensorHealthSummary(BaseModel):
    total_sensors: int = 0
    healthy_count: int = 0
    stale_count: int = 0
    never_reported_count: int = 0
    inactive_count: int = 0
    unavailable_count: int = 0
    in_alert_count: int = 0
    stale_threshold_seconds: float = 300.0
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SensorHealthResponse(BaseModel):
    summary: SensorHealthSummary
    items: List[SensorHealthDetail]
    total: int
    page: int
    limit: int
    total_pages: int
