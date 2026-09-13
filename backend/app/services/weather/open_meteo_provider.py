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

logger = logging.getLogger("resilience.weather.open_meteo")

WMO_WEATHER_CODES: Dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    62: "Moderate rain",
    63: "Moderate rain",
    64: "Heavy rain",
    65: "Heavy continuous rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _parse_iso_utc(ts_str: Optional[str]) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        # Open-Meteo returns '2026-09-13T10:30'
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


class OpenMeteoWeatherProvider(WeatherProvider):
    """
    Real-world meteorological provider using Open-Meteo API.
    Provides verifiable live observations and minutely/hourly forecasts
    for exact incident coordinates without dummy fallback.
    """

    @property
    def name(self) -> str:
        return "open_meteo"

    async def fetch_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> WeatherEvidence:
        now = datetime.now(timezone.utc)
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": round(latitude, 4),
            "longitude": round(longitude, 4),
            "current": "temperature_2m,relative_humidity_2m,precipitation,rain,weather_code,wind_speed_10m,wind_gusts_10m",
            "minutely_15": "precipitation,temperature_2m,wind_speed_10m",
            "hourly": "precipitation_probability,precipitation,temperature_2m,wind_speed_10m,wind_gusts_10m,weather_code",
            "forecast_days": 1,
            "timezone": "UTC",
        }
        if settings.WEATHER_API_KEY:
            params["apikey"] = settings.WEATHER_API_KEY

        timeout_sec = getattr(settings, "WEATHER_TIMEOUT_SECONDS", 4.0)

        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                resp = await client.get(url, params=params)

                if resp.status_code == 429:
                    logger.warning("Open-Meteo rate limit (429) hit for %f, %f", latitude, longitude)
                    return WeatherEvidence(
                        provider=self.name,
                        fetched_at=now,
                        latitude=latitude,
                        longitude=longitude,
                        data_status=WeatherDataStatus.ERROR,
                        error_detail="Weather API rate limit (HTTP 429) exceeded.",
                    )

                if resp.status_code != 200:
                    logger.warning("Open-Meteo HTTP %d for %f, %f: %s", resp.status_code, latitude, longitude, resp.text)
                    return WeatherEvidence(
                        provider=self.name,
                        fetched_at=now,
                        latitude=latitude,
                        longitude=longitude,
                        data_status=WeatherDataStatus.ERROR,
                        error_detail=f"Weather API returned HTTP {resp.status_code}.",
                    )

                data = resp.json()

        except httpx.TimeoutException:
            logger.warning("Open-Meteo request timed out for %f, %f", latitude, longitude)
            return WeatherEvidence(
                provider=self.name,
                fetched_at=now,
                latitude=latitude,
                longitude=longitude,
                data_status=WeatherDataStatus.ERROR,
                error_detail="Weather API request timed out.",
            )
        except Exception as exc:
            logger.warning("Open-Meteo request error for %f, %f: %s", latitude, longitude, exc)
            return WeatherEvidence(
                provider=self.name,
                fetched_at=now,
                latitude=latitude,
                longitude=longitude,
                data_status=WeatherDataStatus.ERROR,
                error_detail=f"Weather API connection error: {str(exc)}",
            )

        # -------------------------------------------------------------
        # Parse Current Observation
        # -------------------------------------------------------------
        current = data.get("current") or {}
        obs_time_str = current.get("time")
        obs_time = _parse_iso_utc(obs_time_str) or now

        temp_c = current.get("temperature_2m")
        precip_mm = current.get("precipitation")
        humidity = current.get("relative_humidity_2m")
        w_code = current.get("weather_code")
        condition_text = WMO_WEATHER_CODES.get(w_code, f"Weather code {w_code}") if w_code is not None else None
        wind_spd = current.get("wind_speed_10m")
        wind_gust = current.get("wind_gusts_10m")

        # Convert wind speed km/h to m/s if returned in km/h
        wind_spd_mps = round(wind_spd / 3.6, 2) if wind_spd is not None else None
        wind_gust_mps = round(wind_gust / 3.6, 2) if wind_gust is not None else None

        # Determine Freshness
        freshness_sec = int((now - obs_time).total_seconds()) if obs_time else 0
        if freshness_sec <= 3600:
            data_status = WeatherDataStatus.FRESH
        elif freshness_sec <= 86400:
            data_status = WeatherDataStatus.STALE
        else:
            data_status = WeatherDataStatus.UNAVAILABLE

        # -------------------------------------------------------------
        # Align Multi-Horizon Forecast Periods (+15m, +30m, +60m)
        # -------------------------------------------------------------
        forecast_periods: List[WeatherForecastPeriod] = []
        min15 = data.get("minutely_15") or {}
        min15_times = min15.get("time", [])
        min15_precips = min15.get("precipitation", [])
        min15_temps = min15.get("temperature_2m", [])
        min15_winds = min15.get("wind_speed_10m", [])

        hourly = data.get("hourly") or {}
        hourly_times = hourly.get("time", [])
        hourly_probs = hourly.get("precipitation_probability", [])
        hourly_precips = hourly.get("precipitation", [])
        hourly_temps = hourly.get("temperature_2m", [])
        hourly_winds = hourly.get("wind_speed_10m", [])
        hourly_gusts = hourly.get("wind_gusts_10m", [])
        hourly_codes = hourly.get("weather_code", [])

        current_prob = None
        if hourly_times and hourly_probs:
            # Match current probability from hourly
            current_prob = hourly_probs[0] if len(hourly_probs) > 0 else None

        for target_min in [15, 30, 60]:
            target_dt = obs_time + timedelta(minutes=target_min)
            
            f_precip: Optional[float] = None
            f_prob: Optional[float] = None
            f_temp: Optional[float] = None
            f_wind: Optional[float] = None
            f_gust: Optional[float] = None
            f_cond: Optional[str] = None

            # Attempt fine-grained 15-minutely match
            best_15_idx = None
            min_15_diff = 999999
            for idx, t_str in enumerate(min15_times):
                t_dt = _parse_iso_utc(t_str)
                if t_dt:
                    diff = abs((t_dt - target_dt).total_seconds())
                    if diff < min_15_diff and diff <= 900:  # within 15 min
                        min_15_diff = diff
                        best_15_idx = idx

            if best_15_idx is not None:
                if best_15_idx < len(min15_precips):
                    f_precip = min15_precips[best_15_idx]
                if best_15_idx < len(min15_temps):
                    f_temp = min15_temps[best_15_idx]
                if best_15_idx < len(min15_winds) and min15_winds[best_15_idx] is not None:
                    f_wind = round(min15_winds[best_15_idx] / 3.6, 2)

            # Match hourly for probability, gusts, and condition code
            best_h_idx = None
            min_h_diff = 999999
            for idx, t_str in enumerate(hourly_times):
                t_dt = _parse_iso_utc(t_str)
                if t_dt:
                    diff = abs((t_dt - target_dt).total_seconds())
                    if diff < min_h_diff and diff <= 3600:
                        min_h_diff = diff
                        best_h_idx = idx

            if best_h_idx is not None:
                if best_h_idx < len(hourly_probs):
                    f_prob = float(hourly_probs[best_h_idx]) if hourly_probs[best_h_idx] is not None else None
                if f_precip is None and best_h_idx < len(hourly_precips):
                    f_precip = hourly_precips[best_h_idx]
                if f_temp is None and best_h_idx < len(hourly_temps):
                    f_temp = hourly_temps[best_h_idx]
                if f_wind is None and best_h_idx < len(hourly_winds) and hourly_winds[best_h_idx] is not None:
                    f_wind = round(hourly_winds[best_h_idx] / 3.6, 2)
                if best_h_idx < len(hourly_gusts) and hourly_gusts[best_h_idx] is not None:
                    f_gust = round(hourly_gusts[best_h_idx] / 3.6, 2)
                if best_h_idx < len(hourly_codes) and hourly_codes[best_h_idx] is not None:
                    c_code = hourly_codes[best_h_idx]
                    f_cond = WMO_WEATHER_CODES.get(c_code, f"Weather code {c_code}")

            forecast_periods.append(
                WeatherForecastPeriod(
                    horizon_minutes=target_min,
                    forecast_timestamp=target_dt,
                    precipitation_mm=f_precip,
                    precipitation_probability=f_prob,
                    temperature_c=f_temp,
                    wind_speed_mps=f_wind,
                    wind_gust_mps=f_gust,
                    condition=f_cond or condition_text,
                )
            )

        return WeatherEvidence(
            provider=self.name,
            fetched_at=now,
            observation_timestamp=obs_time,
            latitude=latitude,
            longitude=longitude,
            temperature_c=temp_c,
            precipitation_mm=precip_mm,
            precipitation_probability=current_prob,
            humidity_percent=humidity,
            wind_speed_mps=wind_spd_mps,
            wind_gust_mps=wind_gust_mps,
            condition=condition_text,
            forecast_periods=forecast_periods,
            data_status=data_status,
            freshness_seconds=freshness_sec,
        )
