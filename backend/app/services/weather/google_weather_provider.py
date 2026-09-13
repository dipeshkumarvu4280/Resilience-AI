import httpx
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from app.models.weather import (
    WeatherEvidence,
    WeatherForecastPeriod,
    WeatherDataStatus,
)
from app.services.weather.interfaces import WeatherProvider
from app.core.config import settings

logger = logging.getLogger("resilience.weather.google")


class GoogleWeatherProvider(WeatherProvider):
    """
    Google Weather Platform Provider.
    Invokes Google Weather API endpoint when configured with API key.
    """

    @property
    def name(self) -> str:
        return "google"

    async def fetch_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> WeatherEvidence:
        now = datetime.now(timezone.utc)
        api_key = settings.WEATHER_API_KEY or settings.GOOGLE_MAPS_API_KEY
        if not api_key:
            return WeatherEvidence(
                provider=self.name,
                fetched_at=now,
                latitude=latitude,
                longitude=longitude,
                data_status=WeatherDataStatus.UNAVAILABLE,
                error_detail="Google Weather API key is not configured.",
            )

        url = "https://weather.googleapis.com/v1/currentConditions:lookup"
        params = {
            "key": api_key,
            "location.latitude": latitude,
            "location.longitude": longitude,
        }

        try:
            async with httpx.AsyncClient(timeout=getattr(settings, "WEATHER_TIMEOUT_SECONDS", 4.0)) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 429:
                    return WeatherEvidence(
                        provider=self.name,
                        fetched_at=now,
                        latitude=latitude,
                        longitude=longitude,
                        data_status=WeatherDataStatus.ERROR,
                        error_detail="Google Weather API rate limit exceeded.",
                    )
                if resp.status_code != 200:
                    return WeatherEvidence(
                        provider=self.name,
                        fetched_at=now,
                        latitude=latitude,
                        longitude=longitude,
                        data_status=WeatherDataStatus.ERROR,
                        error_detail=f"Google Weather API returned HTTP {resp.status_code}.",
                    )
                data = resp.json()
        except Exception as exc:
            return WeatherEvidence(
                provider=self.name,
                fetched_at=now,
                latitude=latitude,
                longitude=longitude,
                data_status=WeatherDataStatus.ERROR,
                error_detail=f"Google Weather connection error: {str(exc)}",
            )

        # Parse Google format
        temp_c = data.get("temperature", {}).get("degrees")
        humidity = data.get("relativeHumidity")
        wind_spd = data.get("wind", {}).get("speed", {}).get("value")
        wind_gust = data.get("wind", {}).get("gust", {}).get("value")
        precip_mm = data.get("precipitation", {}).get("qpf", {}).get("quantity")
        cond_text = data.get("weatherCondition", {}).get("description", {}).get("text")

        return WeatherEvidence(
            provider=self.name,
            fetched_at=now,
            observation_timestamp=now,
            latitude=latitude,
            longitude=longitude,
            temperature_c=temp_c,
            precipitation_mm=precip_mm,
            humidity_percent=humidity,
            wind_speed_mps=wind_spd,
            wind_gust_mps=wind_gust,
            condition=cond_text,
            data_status=WeatherDataStatus.FRESH,
            freshness_seconds=0,
        )
