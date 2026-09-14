import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Tuple, Any

from app.models.weather import (
    WeatherEvidence,
    WeatherDataStatus,
)
from app.services.weather.interfaces import WeatherProvider
from app.services.weather.open_meteo_provider import OpenMeteoWeatherProvider
from app.services.weather.google_weather_provider import GoogleWeatherProvider
from app.core.config import settings

logger = logging.getLogger("resilience.weather.service")


class WeatherService:
    """
    Incident-Specific Weather Intelligence Service.
    Orchestrates real-world weather observation and multi-horizon forecasts.
    Features:
      - Location-based canonical spatial caching (normalized coordinate grid)
      - Single-flight request deduplication (coalesces concurrent requests for same location)
      - HTTP 429 Rate-Limit Circuit Breaker with configurable cooldown
      - Stale-While-Revalidate fallback on rate limits and transient errors
      - Strict zero fake/dummy data guarantees
    """

    def __init__(self, provider: Optional[WeatherProvider] = None):
        self._provider = provider or self._init_provider()
        self._cache: Dict[str, Tuple[datetime, WeatherEvidence]] = {}
        self._in_flight: Dict[str, asyncio.Task] = {}
        self._rate_limited_until: Optional[datetime] = None
        self._lock_obj: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock_obj is None:
            self._lock_obj = asyncio.Lock()
        return self._lock_obj

    def _init_provider(self) -> WeatherProvider:
        p_name = getattr(settings, "WEATHER_PROVIDER", "open_meteo").lower()
        if p_name == "google":
            return GoogleWeatherProvider()
        return OpenMeteoWeatherProvider()

    def set_provider(self, provider: WeatherProvider):
        """Allows test suites to inject controlled providers."""
        self._provider = provider

    def clear_cache(self):
        self._cache.clear()
        self._in_flight.clear()
        self._rate_limited_until = None
        self._lock_obj = None

    def reset_rate_limit(self):
        """Resets the circuit breaker rate-limit state."""
        self._rate_limited_until = None

    def is_rate_limited(self) -> bool:
        if self._rate_limited_until is None:
            return False
        return datetime.now(timezone.utc) < self._rate_limited_until

    def get_rate_limit_cooldown_remaining(self) -> float:
        if self._rate_limited_until is None:
            return 0.0
        remaining = (self._rate_limited_until - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, remaining)

    def _get_canonical_location(self, latitude: float, longitude: float) -> Tuple[float, float, str]:
        """
        Normalizes coordinates into a canonical spatial grid to cluster nearby incidents
        and prevent duplicate weather queries for adjacent coordinates.
        """
        precision = getattr(settings, "WEATHER_COORDINATE_PRECISION_DECIMALS", 3)
        canon_lat = round(latitude, precision)
        canon_lon = round(longitude, precision)
        canon_key = f"{canon_lat:.{precision}f}:{canon_lon:.{precision}f}"
        return canon_lat, canon_lon, canon_key

    def _make_cache_key(self, canonical_loc: str) -> str:
        return f"weather:{self._provider.name}:{canonical_loc}"

    def _clone_for_incident(
        self,
        evidence: WeatherEvidence,
        incident_lat: float,
        incident_lon: float,
        canonical_loc: str,
        cached: bool = True,
        override_status: Optional[str] = None,
        override_error: Optional[str] = None,
        override_rate_limited: Optional[bool] = None,
    ) -> WeatherEvidence:
        """
        Creates an incident-specific WeatherEvidence instance preserving exact requested
        incident coordinates and refreshed age calculation.
        """
        now = datetime.now(timezone.utc)
        obs_time = evidence.observation_timestamp or evidence.fetched_at
        freshness_sec = int((now - obs_time).total_seconds()) if obs_time else 0

        status = override_status or evidence.data_status
        if status in [WeatherDataStatus.FRESH, WeatherDataStatus.STALE]:
            if freshness_sec > 3600:
                status = WeatherDataStatus.STALE

        is_rl = override_rate_limited if override_rate_limited is not None else (getattr(evidence, "rate_limited", False) or self.is_rate_limited())

        return WeatherEvidence(
            provider=evidence.provider,
            provider_type=getattr(evidence, "provider_type", "WEATHER_MODEL"),
            fetched_at=evidence.fetched_at,
            observation_timestamp=evidence.observation_timestamp,
            latitude=incident_lat,
            longitude=incident_lon,
            canonical_location=canonical_loc,
            cached=cached,
            rate_limited=is_rl,
            temperature_c=evidence.temperature_c,
            precipitation_mm=evidence.precipitation_mm,
            precipitation_probability=evidence.precipitation_probability,
            humidity_percent=evidence.humidity_percent,
            wind_speed_mps=evidence.wind_speed_mps,
            wind_gust_mps=evidence.wind_gust_mps,
            condition=evidence.condition,
            forecast_periods=evidence.forecast_periods,
            data_status=status,
            freshness_seconds=freshness_sec,
            error_detail=override_error if override_error is not None else evidence.error_detail,
        )

    async def get_weather_for_incident(
        self,
        latitude: Optional[float],
        longitude: Optional[float],
        use_cache: bool = True,
    ) -> WeatherEvidence:
        """
        Fetches genuine weather evidence for authoritative incident coordinates.
        Utilizes canonical coordinate caching, single-flight request coalescing,
        bounded 429 rate-limit circuit breaking, and stale-while-revalidate.
        Never substitutes fallback coordinates or fake data.
        """
        now = datetime.now(timezone.utc)

        # 1. Coordinate Validation
        if latitude is None or longitude is None or not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
            return WeatherEvidence(
                provider=self._provider.name,
                provider_type="WEATHER_MODEL",
                fetched_at=now,
                latitude=latitude or 0.0,
                longitude=longitude or 0.0,
                data_status=WeatherDataStatus.UNAVAILABLE,
                error_detail="Weather intelligence unavailable because incident location is missing.",
            )

        # 2. Compute Canonical Location and Cache Key
        canon_lat, canon_lon, canon_loc = self._get_canonical_location(latitude, longitude)
        cache_key = self._make_cache_key(canon_loc)
        cache_ttl = getattr(settings, "WEATHER_CACHE_TTL_SECONDS", 600)

        # 3. Check In-Memory Cache (Cache Hit within TTL)
        if use_cache and cache_key in self._cache:
            cached_at, cached_ev = self._cache[cache_key]
            age_sec = (now - cached_at).total_seconds()
            if age_sec < cache_ttl and cached_ev.data_status in [WeatherDataStatus.FRESH, WeatherDataStatus.STALE]:
                logger.debug("Weather cache HIT for key=%s (age=%.1fs)", cache_key, age_sec)
                return self._clone_for_incident(cached_ev, latitude, longitude, canon_loc, cached=True)

        # 4. Check Circuit Breaker Rate-Limit Cooldown
        if self.is_rate_limited():
            remaining_cd = self.get_rate_limit_cooldown_remaining()
            logger.warning("Weather provider '%s' in 429 cooldown (%.1fs remaining). Blocking outbound fetch.", self._provider.name, remaining_cd)

            # Stale-While-Revalidate: Return cached snapshot if available
            if cache_key in self._cache:
                _, cached_ev = self._cache[cache_key]
                if cached_ev.data_status in [WeatherDataStatus.FRESH, WeatherDataStatus.STALE]:
                    logger.info("Serving STALE cached weather snapshot during provider rate-limit cooldown for %s", canon_loc)
                    return self._clone_for_incident(
                        cached_ev,
                        latitude,
                        longitude,
                        canon_loc,
                        cached=True,
                        override_status=WeatherDataStatus.STALE,
                        override_error="Weather provider temporarily rate limited (HTTP 429). Serving cached snapshot.",
                    )

            # Truthful RATE_LIMITED response when no cache exists
            return WeatherEvidence(
                provider=self._provider.name,
                provider_type="WEATHER_MODEL",
                fetched_at=now,
                latitude=latitude,
                longitude=longitude,
                canonical_location=canon_loc,
                data_status=WeatherDataStatus.RATE_LIMITED,
                rate_limited=True,
                error_detail=f"Weather provider temporarily rate limited (HTTP 429). Cooldown active ({int(remaining_cd)}s remaining).",
            )

        # 5. Single-Flight Request Deduplication (Coalesce concurrent calls for same location)
        task = None
        async with self._get_lock():
            if cache_key in self._in_flight:
                logger.debug("Joining existing in-flight weather request for %s", cache_key)
                task = self._in_flight[cache_key]
            else:
                logger.debug("Initiating new single-flight weather request for %s", cache_key)
                # Create background task for single-flight execution
                coro = self._execute_fetch_and_cache(canon_lat, canon_lon, cache_key, canon_loc)
                task = asyncio.create_task(coro)
                self._in_flight[cache_key] = task

        try:
            raw_evidence = await task
        except Exception as exc:
            logger.error("Error awaiting weather task for %s: %s", cache_key, exc)
            raw_evidence = WeatherEvidence(
                provider=self._provider.name,
                provider_type="WEATHER_MODEL",
                fetched_at=now,
                latitude=latitude,
                longitude=longitude,
                canonical_location=canon_loc,
                data_status=WeatherDataStatus.ERROR,
                error_detail=f"Weather fetch error: {str(exc)}",
            )
        finally:
            async with self._get_lock():
                if cache_key in self._in_flight and self._in_flight[cache_key] == task:
                    self._in_flight.pop(cache_key, None)

        # 6. Apply Incident Specific Coordinates
        return self._clone_for_incident(
            raw_evidence,
            latitude,
            longitude,
            canon_loc,
            cached=getattr(raw_evidence, "cached", False),
        )

    async def _execute_fetch_and_cache(
        self,
        canon_lat: float,
        canon_lon: float,
        cache_key: str,
        canon_loc: str,
    ) -> WeatherEvidence:
        """
        Executes single outbound HTTP request to provider, handles 429 circuit breaking,
        updates cache, and implements stale-while-revalidate fallback.
        """
        now = datetime.now(timezone.utc)
        cooldown_sec = getattr(settings, "WEATHER_RATE_LIMIT_COOLDOWN_SECONDS", 60)

        # Fetch from underlying provider
        weather_ev = await self._provider.fetch_weather(canon_lat, canon_lon)
        weather_ev.canonical_location = canon_loc

        # Check for HTTP 429 / Rate Limited
        if weather_ev.data_status == WeatherDataStatus.RATE_LIMITED or getattr(weather_ev, "rate_limited", False):
            logger.warning("Triggering %ds circuit breaker cooldown for weather provider '%s'", cooldown_sec, self._provider.name)
            self._rate_limited_until = now + timedelta(seconds=cooldown_sec)

            # Stale-While-Revalidate: Return last valid cached snapshot if one exists
            if cache_key in self._cache:
                _, cached_ev = self._cache[cache_key]
                if cached_ev.data_status in [WeatherDataStatus.FRESH, WeatherDataStatus.STALE]:
                    logger.info("Serving previous valid snapshot as STALE following 429 response for %s", canon_loc)
                    return self._clone_for_incident(
                        cached_ev,
                        canon_lat,
                        canon_lon,
                        canon_loc,
                        cached=True,
                        override_status=WeatherDataStatus.STALE,
                        override_error="Weather provider temporarily rate limited (HTTP 429). Serving cached snapshot.",
                    )

            return weather_ev

        # If fetch succeeded with valid data
        if weather_ev.data_status in [WeatherDataStatus.FRESH, WeatherDataStatus.STALE]:
            self._rate_limited_until = None  # Clear circuit breaker on successful fresh probe
            self._cache[cache_key] = (now, weather_ev)
            logger.info("Successfully fetched and cached weather for key=%s (temp=%s, precip=%s)", cache_key, weather_ev.temperature_c, weather_ev.precipitation_mm)
            return weather_ev

        # If fetch failed with error or timeout, check if stale cache exists
        if cache_key in self._cache:
            _, cached_ev = self._cache[cache_key]
            if cached_ev.data_status in [WeatherDataStatus.FRESH, WeatherDataStatus.STALE]:
                logger.info("Serving STALE cached snapshot following provider failure for %s", canon_loc)
                return self._clone_for_incident(
                    cached_ev,
                    canon_lat,
                    canon_lon,
                    canon_loc,
                    cached=True,
                    override_status=WeatherDataStatus.STALE,
                    override_error=f"Provider error ({weather_ev.error_detail}). Serving cached snapshot.",
                )

        return weather_ev


# Singleton instance
weather_service = WeatherService()

