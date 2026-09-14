import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.models.weather import (
    WeatherEvidence,
    WeatherForecastPeriod,
    WeatherDataStatus,
)
from app.services.weather.open_meteo_provider import OpenMeteoWeatherProvider
from app.services.weather.weather_service import WeatherService, weather_service
from app.core.config import settings


@pytest.fixture(autouse=True)
def clean_weather_state():
    weather_service.clear_cache()
    weather_service.reset_rate_limit()
    yield
    weather_service.clear_cache()
    weather_service.reset_rate_limit()


# -----------------------------------------------------------------------------
# 1. First Request -> Exactly One Open-Meteo Call
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_first_request_triggers_single_outbound_call():
    service = WeatherService()
    mock_provider = AsyncMock()
    mock_ev = WeatherEvidence(
        provider="open_meteo",
        provider_type="WEATHER_MODEL",
        fetched_at=datetime.now(timezone.utc),
        latitude=16.2415,
        longitude=80.6433,
        temperature_c=30.0,
        precipitation_mm=1.5,
        data_status=WeatherDataStatus.FRESH,
    )
    mock_provider.name = "open_meteo"
    mock_provider.fetch_weather.return_value = mock_ev
    service.set_provider(mock_provider)

    res = await service.get_weather_for_incident(16.2415, 80.6433)
    assert res.data_status == WeatherDataStatus.FRESH
    assert res.temperature_c == 30.0
    assert mock_provider.fetch_weather.call_count == 1


# -----------------------------------------------------------------------------
# 2. Repeated Same-Location Request -> Zero Additional Calls (Cache Hit)
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_repeated_same_location_request_uses_cache():
    service = WeatherService()
    mock_provider = AsyncMock()
    mock_ev = WeatherEvidence(
        provider="open_meteo",
        provider_type="WEATHER_MODEL",
        fetched_at=datetime.now(timezone.utc),
        latitude=16.2415,
        longitude=80.6433,
        temperature_c=30.0,
        precipitation_mm=1.5,
        data_status=WeatherDataStatus.FRESH,
    )
    mock_provider.name = "open_meteo"
    mock_provider.fetch_weather.return_value = mock_ev
    service.set_provider(mock_provider)

    # First call
    res1 = await service.get_weather_for_incident(16.2415, 80.6433)
    # Repeated calls within TTL
    res2 = await service.get_weather_for_incident(16.2415, 80.6433)
    res3 = await service.get_weather_for_incident(16.2415, 80.6433)

    assert mock_provider.fetch_weather.call_count == 1
    assert res2.cached is True
    assert res3.cached is True
    assert res2.temperature_c == 30.0


# -----------------------------------------------------------------------------
# 3. 10 Concurrent Requests -> Exactly One Outbound Call (Single-Flight)
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_concurrent_requests_coalesced_single_flight():
    service = WeatherService()
    mock_provider = AsyncMock()

    async def delayed_fetch(lat, lon):
        await asyncio.sleep(0.05)
        return WeatherEvidence(
            provider="open_meteo",
            provider_type="WEATHER_MODEL",
            fetched_at=datetime.now(timezone.utc),
            latitude=lat,
            longitude=lon,
            temperature_c=29.0,
            precipitation_mm=4.0,
            data_status=WeatherDataStatus.FRESH,
        )

    mock_provider.name = "open_meteo"
    mock_provider.fetch_weather.side_effect = delayed_fetch
    service.set_provider(mock_provider)

    # Launch 10 simultaneous requests for identical location
    tasks = [service.get_weather_for_incident(16.2415, 80.6433) for _ in range(10)]
    results = await asyncio.gather(*tasks)

    # Exactly 1 outbound call should have been made
    assert mock_provider.fetch_weather.call_count == 1
    assert len(results) == 10
    for r in results:
        assert r.data_status == WeatherDataStatus.FRESH
        assert r.temperature_c == 29.0


# -----------------------------------------------------------------------------
# 4. Multi-Horizon Extraction from Single Fetch
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_multi_horizon_extracted_from_single_weather_fetch():
    provider = OpenMeteoWeatherProvider()
    now = datetime.now(timezone.utc)
    mock_payload = {
        "current": {
            "time": now.strftime("%Y-%m-%dT%H:%M"),
            "temperature_2m": 31.0,
            "relative_humidity_2m": 75,
            "precipitation": 0.5,
            "weather_code": 0,
            "wind_speed_10m": 12.0,
        },
        "minutely_15": {
            "time": [
                (now + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M"),
                (now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M"),
                (now + timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M"),
            ],
            "precipitation": [1.0, 2.5, 4.0],
            "temperature_2m": [30.5, 30.0, 29.0],
            "wind_speed_10m": [14.0, 16.0, 18.0],
        },
        "hourly": {
            "time": [(now + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(3)],
            "precipitation_probability": [40, 60, 80],
            "precipitation": [0.5, 2.0, 4.0],
            "temperature_2m": [31.0, 30.0, 29.0],
            "wind_speed_10m": [12.0, 16.0, 18.0],
            "weather_code": [0, 61, 63],
        },
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await provider.fetch_weather(16.2415, 80.6433)

        assert mock_get.call_count == 1
        assert len(res.forecast_periods) == 3
        horizons = {fp.horizon_minutes: fp for fp in res.forecast_periods}
        assert 15 in horizons
        assert 30 in horizons
        assert 60 in horizons
        assert horizons[15].precipitation_mm == 1.0
        assert horizons[30].precipitation_mm == 2.5
        assert horizons[60].precipitation_mm == 4.0


# -----------------------------------------------------------------------------
# 5. Cache Expiry (TTL) triggers fresh fetch
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_cache_expiry_triggers_fresh_fetch():
    service = WeatherService()
    mock_provider = AsyncMock()
    mock_provider.name = "open_meteo"

    now = datetime.now(timezone.utc)
    ev1 = WeatherEvidence(
        provider="open_meteo",
        provider_type="WEATHER_MODEL",
        fetched_at=now - timedelta(seconds=700),  # older than 600s TTL
        observation_timestamp=now - timedelta(seconds=700),
        latitude=16.2415,
        longitude=80.6433,
        temperature_c=25.0,
        data_status=WeatherDataStatus.FRESH,
    )
    ev2 = WeatherEvidence(
        provider="open_meteo",
        provider_type="WEATHER_MODEL",
        fetched_at=now,
        observation_timestamp=now,
        latitude=16.2415,
        longitude=80.6433,
        temperature_c=27.0,
        data_status=WeatherDataStatus.FRESH,
    )
    mock_provider.fetch_weather.side_effect = [ev1, ev2]
    service.set_provider(mock_provider)

    # Initial fetch
    res1 = await service.get_weather_for_incident(16.2415, 80.6433)
    # Manually age the cache entry
    canon_lat, canon_lon, canon_loc = service._get_canonical_location(16.2415, 80.6433)
    cache_key = service._make_cache_key(canon_loc)
    service._cache[cache_key] = (now - timedelta(seconds=650), ev1)

    # Second fetch after TTL expiration
    res2 = await service.get_weather_for_incident(16.2415, 80.6433)
    assert mock_provider.fetch_weather.call_count == 2
    assert res2.temperature_c == 27.0


# -----------------------------------------------------------------------------
# 6. HTTP 429 Bounded Exponential Backoff Retry
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_open_meteo_429_bounded_backoff_and_exhaustion():
    provider = OpenMeteoWeatherProvider()
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("app.services.weather.open_meteo_provider.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_get.return_value = mock_resp_429

        res = await provider.fetch_weather(16.2415, 80.6433)

        # Retries: initial attempt + 2 retries = 3 calls total
        assert mock_get.call_count == 3
        assert mock_sleep.call_count == 2
        assert res.data_status == WeatherDataStatus.RATE_LIMITED
        assert res.rate_limited is True
        assert "429" in (res.error_detail or "")


# -----------------------------------------------------------------------------
# 7. HTTP 429 Circuit Breaker Cooldown blocks subsequent calls
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_rate_limit_circuit_breaker_cooldown():
    service = WeatherService()
    mock_provider = AsyncMock()
    mock_provider.name = "open_meteo"
    mock_provider.fetch_weather.return_value = WeatherEvidence(
        provider="open_meteo",
        provider_type="WEATHER_MODEL",
        fetched_at=datetime.now(timezone.utc),
        latitude=16.2415,
        longitude=80.6433,
        data_status=WeatherDataStatus.RATE_LIMITED,
        rate_limited=True,
        error_detail="Rate limited (429)",
    )
    service.set_provider(mock_provider)

    # Request 1 -> hits provider and encounters 429
    res1 = await service.get_weather_for_incident(16.2415, 80.6433)
    assert service.is_rate_limited() is True
    assert mock_provider.fetch_weather.call_count == 1

    # Request 2 & 3 during cooldown -> blocked by circuit breaker, 0 new calls to provider
    res2 = await service.get_weather_for_incident(16.2415, 80.6433)
    res3 = await service.get_weather_for_incident(16.5000, 80.7000)

    assert mock_provider.fetch_weather.call_count == 1
    assert res2.data_status == WeatherDataStatus.RATE_LIMITED
    assert res3.data_status == WeatherDataStatus.RATE_LIMITED
    assert res2.rate_limited is True


# -----------------------------------------------------------------------------
# 8. Stale-While-Revalidate: Valid Cached Snapshot Served During 429
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_stale_cache_served_during_429():
    service = WeatherService()
    mock_provider = AsyncMock()
    mock_provider.name = "open_meteo"

    now = datetime.now(timezone.utc)
    fresh_snapshot = WeatherEvidence(
        provider="open_meteo",
        provider_type="WEATHER_MODEL",
        fetched_at=now - timedelta(minutes=15),
        observation_timestamp=now - timedelta(minutes=15),
        latitude=16.2415,
        longitude=80.6433,
        temperature_c=28.5,
        precipitation_mm=3.0,
        data_status=WeatherDataStatus.FRESH,
    )
    # Seed cache
    canon_lat, canon_lon, canon_loc = service._get_canonical_location(16.2415, 80.6433)
    cache_key = service._make_cache_key(canon_loc)
    service._cache[cache_key] = (now - timedelta(minutes=15), fresh_snapshot)

    # Provider is now rate limited
    mock_provider.fetch_weather.return_value = WeatherEvidence(
        provider="open_meteo",
        provider_type="WEATHER_MODEL",
        fetched_at=now,
        latitude=16.2415,
        longitude=80.6433,
        data_status=WeatherDataStatus.RATE_LIMITED,
        rate_limited=True,
        error_detail="Rate limited (HTTP 429)",
    )
    service.set_provider(mock_provider)

    # Force cache expiration to trigger fetch attempt
    service._cache[cache_key] = (now - timedelta(seconds=700), fresh_snapshot)

    res = await service.get_weather_for_incident(16.2415, 80.6433)
    # Should serve the cached snapshot as STALE with rate limit notice
    assert res.data_status == WeatherDataStatus.STALE
    assert res.temperature_c == 28.5
    assert res.cached is True
    assert res.rate_limited is True
    assert "429" in (res.error_detail or "")


# -----------------------------------------------------------------------------
# 9. Multiple Nearby Incidents (~100m) Reuse Same Weather Cache
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_nearby_incidents_spatial_clustering_reuse_cache():
    service = WeatherService()
    mock_provider = AsyncMock()
    mock_provider.name = "open_meteo"
    mock_provider.fetch_weather.return_value = WeatherEvidence(
        provider="open_meteo",
        provider_type="WEATHER_MODEL",
        fetched_at=datetime.now(timezone.utc),
        latitude=16.227,
        longitude=80.538,
        temperature_c=32.0,
        precipitation_mm=0.0,
        data_status=WeatherDataStatus.FRESH,
    )
    service.set_provider(mock_provider)

    # Incident A: 16.227379, 80.537606
    resA = await service.get_weather_for_incident(16.227379, 80.537606)
    # Incident B: 16.227400, 80.537620 (~2 meters away)
    resB = await service.get_weather_for_incident(16.227400, 80.537620)

    # Only 1 fetch call to provider
    assert mock_provider.fetch_weather.call_count == 1
    # Original incident coordinates are preserved for each report
    assert resA.latitude == 16.227379
    assert resB.latitude == 16.227400
    assert resB.cached is True
    assert resA.canonical_location == resB.canonical_location


# -----------------------------------------------------------------------------
# 10. Provider Timeout and HTTP 500 Handling
# -----------------------------------------------------------------------------
@pytest.mark.anyio
async def test_provider_timeout_and_500_handling():
    provider = OpenMeteoWeatherProvider()

    # Timeout
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=Exception("Connection timed out")):
        res_to = await provider.fetch_weather(16.2415, 80.6433)
        assert res_to.data_status == WeatherDataStatus.ERROR
        assert res_to.temperature_c is None
        assert res_to.precipitation_mm is None

    # HTTP 500
    mock_500 = MagicMock()
    mock_500.status_code = 500
    mock_500.text = "Internal Server Error"
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_500):
        res_500 = await provider.fetch_weather(16.2415, 80.6433)
        assert res_500.data_status == WeatherDataStatus.ERROR
        assert "500" in (res_500.error_detail or "")
