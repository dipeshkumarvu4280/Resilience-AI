import logging
from datetime import datetime, timezone
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
    Maintains bounded in-memory caching and strict zero-fake-data guarantees.
    """

    def __init__(self, provider: Optional[WeatherProvider] = None):
        self._provider = provider or self._init_provider()
        self._cache: Dict[str, Tuple[datetime, WeatherEvidence]] = {}

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

    async def get_weather_for_incident(
        self,
        latitude: Optional[float],
        longitude: Optional[float],
        use_cache: bool = True,
    ) -> WeatherEvidence:
        """
        Fetches genuine weather evidence for authoritative incident coordinates.
        Never substitutes fallback coordinates or fake data.
        """
        now = datetime.now(timezone.utc)

        # 1. Coordinate Validation
        if latitude is None or longitude is None or not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
            return WeatherEvidence(
                provider=self._provider.name,
                fetched_at=now,
                latitude=latitude or 0.0,
                longitude=longitude or 0.0,
                data_status=WeatherDataStatus.UNAVAILABLE,
                error_detail="Weather intelligence unavailable because incident location is missing.",
            )

        # 2. Check Cache
        cache_key = f"{self._provider.name}:{round(latitude, 4)}:{round(longitude, 4)}"
        cache_ttl = getattr(settings, "WEATHER_CACHE_TTL_SECONDS", 600)

        if use_cache and cache_key in self._cache:
            cached_at, cached_ev = self._cache[cache_key]
            if (now - cached_at).total_seconds() < cache_ttl and cached_ev.data_status in [WeatherDataStatus.FRESH, WeatherDataStatus.STALE]:
                return cached_ev

        # 3. Fetch from Provider
        weather_ev = await self._provider.fetch_weather(latitude, longitude)

        # 4. Cache successful responses
        if use_cache and weather_ev.data_status in [WeatherDataStatus.FRESH, WeatherDataStatus.STALE]:
            self._cache[cache_key] = (now, weather_ev)

        return weather_ev


# Singleton instance
weather_service = WeatherService()
