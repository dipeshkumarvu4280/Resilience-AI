from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class WeatherDataStatus:
    FRESH = "FRESH"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


class WeatherForecastPeriod(BaseModel):
    horizon_minutes: int = Field(..., description="Forecast horizon in minutes: 15, 30, or 60")
    forecast_timestamp: datetime = Field(..., description="Timestamp of the forecast projection")
    precipitation_mm: Optional[float] = Field(None, description="Projected precipitation in mm (null if unavailable, never fake 0)")
    precipitation_probability: Optional[float] = Field(None, description="Precipitation probability 0-100% (null if unavailable)")
    temperature_c: Optional[float] = Field(None, description="Projected temperature in Celsius")
    wind_speed_mps: Optional[float] = Field(None, description="Projected wind speed in m/s")
    wind_gust_mps: Optional[float] = Field(None, description="Projected wind gust in m/s")
    condition: Optional[str] = Field(None, description="Meteorological condition text e.g. 'Moderate Rain'")


class WeatherEvidence(BaseModel):
    provider: str = Field(..., description="Weather data provider e.g. 'open_meteo', 'google'")
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when weather was fetched")
    observation_timestamp: Optional[datetime] = Field(None, description="Authoritative timestamp of weather observation")
    latitude: float = Field(..., description="Authoritative incident latitude queried")
    longitude: float = Field(..., description="Authoritative incident longitude queried")
    
    # Current Observations (null if unavailable, NEVER fake 0)
    temperature_c: Optional[float] = Field(None, description="Observed temperature in Celsius")
    precipitation_mm: Optional[float] = Field(None, description="Observed precipitation in mm/h")
    precipitation_probability: Optional[float] = Field(None, description="Current precipitation probability 0-100%")
    humidity_percent: Optional[float] = Field(None, description="Relative humidity percentage")
    wind_speed_mps: Optional[float] = Field(None, description="Observed wind speed in m/s")
    wind_gust_mps: Optional[float] = Field(None, description="Observed wind gust in m/s")
    condition: Optional[str] = Field(None, description="Observed weather condition description")
    
    # Multi-Horizon Forecast Periods (+15m, +30m, +60m)
    forecast_periods: List[WeatherForecastPeriod] = Field(default_factory=list, description="Future forecast periods")
    
    # Freshness & Status
    data_status: str = Field(default=WeatherDataStatus.UNAVAILABLE, description="FRESH, STALE, UNAVAILABLE, ERROR")
    freshness_seconds: Optional[int] = Field(None, description="Age of observation in seconds")
    error_detail: Optional[str] = Field(None, description="Error reason if data_status is UNAVAILABLE or ERROR")
