import pytest
import os
import re
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, Response
from unittest.mock import patch, MagicMock

from app.models.weather import (
    WeatherEvidence,
    WeatherForecastPeriod,
    WeatherDataStatus,
)
from app.models.predictive import (
    PredictiveDataSufficiency,
    EscalationRiskLevel,
    TrendDirection,
)
from app.models.enums import EmergencyType, SeverityLevel, SituationStatus
from app.services.weather.open_meteo_provider import OpenMeteoWeatherProvider
from app.services.weather.google_weather_provider import GoogleWeatherProvider
from app.services.weather.weather_service import WeatherService
from app.services.predictive.interfaces import RawIncidentData, ExtractedFeatureSet
from app.services.predictive.feature_engine import DeterministicFeatureProvider
from app.services.predictive.deterministic_escalation_engine import DeterministicEscalationModel
from app.services.predictive.predictive_service import predictive_service
from app.db.mongodb import get_database


# -----------------------------------------------------------------------------
# 1. Real Weather Provider Normalization Tests
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_open_meteo_provider_normalization_success():
    """1 & 3: Verify real weather provider normalization from mock HTTP transport."""
    provider = OpenMeteoWeatherProvider()
    mock_payload = {
        "current": {
            "time": "2026-09-13T10:30",
            "temperature_2m": 31.5,
            "relative_humidity_2m": 78,
            "precipitation": 2.4,
            "weather_code": 61,
            "wind_speed_10m": 18.0,
            "wind_gusts_10m": 36.0,
        },
        "minutely_15": {
            "time": ["2026-09-13T10:30", "2026-09-13T10:45", "2026-09-13T11:00", "2026-09-13T11:30"],
            "precipitation": [2.4, 3.8, 5.2, 7.0],
            "temperature_2m": [31.5, 31.2, 30.8, 30.0],
            "wind_speed_10m": [18.0, 20.0, 22.0, 25.0],
        },
        "hourly": {
            "time": ["2026-09-13T10:00", "2026-09-13T11:00", "2026-09-13T12:00"],
            "precipitation_probability": [85, 90, 95],
            "precipitation": [2.4, 5.2, 8.0],
            "temperature_2m": [31.5, 30.8, 29.5],
            "wind_speed_10m": [18.0, 22.0, 28.0],
            "wind_gusts_10m": [36.0, 42.0, 50.0],
            "weather_code": [61, 63, 65],
        },
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_get.return_value = mock_resp

        res = await provider.fetch_weather(16.2415, 80.6433)
        assert res.provider == "open_meteo"
        assert res.data_status == WeatherDataStatus.FRESH
        assert res.temperature_c == 31.5
        assert res.precipitation_mm == 2.4
        assert res.humidity_percent == 78
        assert res.wind_speed_mps == 5.0  # 18.0 km/h -> 5.0 m/s
        assert res.wind_gust_mps == 10.0  # 36.0 km/h -> 10.0 m/s
        assert res.condition == "Slight rain"
        assert len(res.forecast_periods) == 3
        assert res.forecast_periods[0].horizon_minutes == 15
        assert res.forecast_periods[1].horizon_minutes == 30
        assert res.forecast_periods[2].horizon_minutes == 60


def test_missing_google_api_key():
    """2: Verify missing API key sets UNAVAILABLE without crashing."""
    import asyncio
    provider = GoogleWeatherProvider()
    with patch("app.services.weather.google_weather_provider.settings") as mock_settings:
        mock_settings.WEATHER_API_KEY = None
        mock_settings.GOOGLE_MAPS_API_KEY = None
        res = asyncio.run(provider.fetch_weather(16.2415, 80.6433))
        assert res.data_status == WeatherDataStatus.UNAVAILABLE
        assert "API key is not configured" in (res.error_detail or "")
        assert res.temperature_c is None
        assert res.precipitation_mm is None


@pytest.mark.anyio
async def test_weather_api_timeout():
    """4: Verify weather provider handles timeout gracefully."""
    import httpx
    provider = OpenMeteoWeatherProvider()
    with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Request timed out")):
        res = await provider.fetch_weather(16.2415, 80.6433)
        assert res.data_status == WeatherDataStatus.ERROR
        assert "timed out" in (res.error_detail or "")
        assert res.precipitation_mm is None


@pytest.mark.anyio
async def test_weather_api_429_rate_limit():
    """5: Verify weather provider handles HTTP 429 rate limit."""
    provider = OpenMeteoWeatherProvider()
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_get.return_value = mock_resp

        res = await provider.fetch_weather(16.2415, 80.6433)
        assert res.data_status == WeatherDataStatus.ERROR
        assert "429" in (res.error_detail or "")


@pytest.mark.anyio
async def test_invalid_weather_response():
    """6: Verify weather provider handles HTTP 500 server error."""
    provider = OpenMeteoWeatherProvider()
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_get.return_value = mock_resp

        res = await provider.fetch_weather(16.2415, 80.6433)
        assert res.data_status == WeatherDataStatus.ERROR
        assert "HTTP 500" in (res.error_detail or "")


# -----------------------------------------------------------------------------
# 2. Freshness & Coordinate Selection Tests
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_fresh_vs_stale_weather_freshness():
    """7 & 8: Verify fresh (<=1h) vs stale (>1h) weather states and weighting discount."""
    provider = DeterministicFeatureProvider()
    now = datetime.now(timezone.utc)

    # 1. Fresh Weather (<1h)
    fresh_w = WeatherEvidence(
        provider="open_meteo",
        fetched_at=now,
        observation_timestamp=now - timedelta(minutes=15),
        latitude=16.2415,
        longitude=80.6433,
        temperature_c=30.0,
        precipitation_mm=5.0,
        data_status=WeatherDataStatus.FRESH,
        freshness_seconds=900,
    )
    raw_fresh = RawIncidentData(
        incident_id="SIT-FRESH-W",
        is_situation=True,
        situation_doc={"severity_score": 5.0, "emergency_type": "FLOOD"},
        weather_evidence=fresh_w,
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )
    feat_fresh = await provider.extract_features(raw_fresh)
    assert not any("Weather intelligence" in lim and "stale" in lim for lim in feat_fresh.limitations)
    assert feat_fresh.external_context_sources_count == 1

    # 2. Stale Weather (>1h old)
    stale_w = WeatherEvidence(
        provider="open_meteo",
        fetched_at=now,
        observation_timestamp=now - timedelta(hours=3),
        latitude=16.2415,
        longitude=80.6433,
        temperature_c=30.0,
        precipitation_mm=5.0,
        data_status=WeatherDataStatus.STALE,
        freshness_seconds=10800,
    )
    raw_stale = RawIncidentData(
        incident_id="SIT-STALE-W",
        is_situation=True,
        situation_doc={"severity_score": 5.0, "emergency_type": "FLOOD"},
        weather_evidence=stale_w,
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )
    feat_stale = await provider.extract_features(raw_stale)
    assert any("stale" in lim.lower() for lim in feat_stale.limitations)


@pytest.mark.anyio
async def test_missing_incident_location_handling():
    """9 & 10: Verify missing coordinates produce UNAVAILABLE weather without crash."""
    service = WeatherService()
    res = await service.get_weather_for_incident(None, None)
    assert res.data_status == WeatherDataStatus.UNAVAILABLE
    assert "location is missing" in (res.error_detail or "")


# -----------------------------------------------------------------------------
# 3. Hazard-Aware Weather Signal & Multi-Horizon Differentiation Tests
# -----------------------------------------------------------------------------

def test_hazard_aware_flood_weather_features():
    """11: Verify flood incidents extract precipitation and rainfall trends."""
    model = DeterministicEscalationModel()
    now = datetime.now(timezone.utc)

    weather = WeatherEvidence(
        provider="open_meteo",
        fetched_at=now,
        observation_timestamp=now,
        latitude=16.2415,
        longitude=80.6433,
        temperature_c=28.0,
        precipitation_mm=12.0,
        precipitation_probability=90.0,
        forecast_periods=[
            WeatherForecastPeriod(horizon_minutes=15, forecast_timestamp=now + timedelta(minutes=15), precipitation_mm=14.0, precipitation_probability=95.0),
            WeatherForecastPeriod(horizon_minutes=30, forecast_timestamp=now + timedelta(minutes=30), precipitation_mm=18.0, precipitation_probability=95.0),
            WeatherForecastPeriod(horizon_minutes=60, forecast_timestamp=now + timedelta(minutes=60), precipitation_mm=25.0, precipitation_probability=100.0),
        ],
        data_status=WeatherDataStatus.FRESH,
    )

    raw_flood = RawIncidentData(
        incident_id="SIT-FLOOD-W",
        is_situation=True,
        situation_doc={"severity_score": 6.0, "emergency_type": "FLOOD"},
        weather_evidence=weather,
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )

    feat_flood = ExtractedFeatureSet(
        feature_dict={"weather_precipitation_mm": 12.0, "weather_precipitation_probability": 90.0},
        total_data_points=2,
        independent_sources_count=1,
        independent_physical_sources_count=1,
        external_context_sources_count=1,
        weather_evidence=weather,
        data_status=PredictiveDataSufficiency.SUFFICIENT_DATA,
    )

    res30 = model.predict_horizon(30, feat_flood, raw_flood)
    assert res30.weather_contribution is not None
    assert res30.weather_contribution > 0.0
    assert any("precipitation" in f.lower() for f in res30.contributing_factors)


def test_hazard_aware_cyclone_weather_features():
    """12: Verify cyclone incidents extract wind speeds and gusts."""
    model = DeterministicEscalationModel()
    now = datetime.now(timezone.utc)

    weather = WeatherEvidence(
        provider="open_meteo",
        fetched_at=now,
        observation_timestamp=now,
        latitude=16.2415,
        longitude=80.6433,
        wind_speed_mps=28.0,
        wind_gust_mps=40.0,
        forecast_periods=[
            WeatherForecastPeriod(horizon_minutes=30, forecast_timestamp=now + timedelta(minutes=30), wind_speed_mps=32.0, wind_gust_mps=45.0),
        ],
        data_status=WeatherDataStatus.FRESH,
    )

    raw_cyclone = RawIncidentData(
        incident_id="SIT-CYC-W",
        is_situation=True,
        situation_doc={"severity_score": 6.0, "emergency_type": "CYCLONE"},
        weather_evidence=weather,
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )

    feat_cyc = ExtractedFeatureSet(
        feature_dict={"weather_wind_speed_mps": 28.0},
        total_data_points=2,
        independent_physical_sources_count=1,
        external_context_sources_count=1,
        weather_evidence=weather,
        data_status=PredictiveDataSufficiency.SUFFICIENT_DATA,
    )

    res30 = model.predict_horizon(30, feat_cyc, raw_cyclone)
    assert res30.weather_contribution is not None
    assert res30.weather_contribution > 0.0
    assert any("wind" in f.lower() for f in res30.contributing_factors)


def test_hazard_aware_heatwave_weather_features():
    """13: Verify heatwave incidents extract temperature."""
    model = DeterministicEscalationModel()
    now = datetime.now(timezone.utc)

    weather = WeatherEvidence(
        provider="open_meteo",
        fetched_at=now,
        observation_timestamp=now,
        latitude=16.2415,
        longitude=80.6433,
        temperature_c=43.5,
        forecast_periods=[
            WeatherForecastPeriod(horizon_minutes=30, forecast_timestamp=now + timedelta(minutes=30), temperature_c=45.0),
        ],
        data_status=WeatherDataStatus.FRESH,
    )

    raw_heat = RawIncidentData(
        incident_id="SIT-HEAT-W",
        is_situation=True,
        situation_doc={"severity_score": 5.0, "emergency_type": "HEATWAVE"},
        weather_evidence=weather,
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )

    feat_heat = ExtractedFeatureSet(
        feature_dict={"weather_temperature_c": 43.5},
        total_data_points=2,
        independent_physical_sources_count=1,
        external_context_sources_count=1,
        weather_evidence=weather,
        data_status=PredictiveDataSufficiency.SUFFICIENT_DATA,
    )

    res30 = model.predict_horizon(30, feat_heat, raw_heat)
    assert res30.weather_contribution is not None
    assert res30.weather_contribution > 0.0
    assert any("heat" in f.lower() or "temperature" in f.lower() for f in res30.contributing_factors)


def test_weather_irrelevant_for_road_accident():
    """14: Verify normal weather has minimal/zero contribution for road accidents."""
    model = DeterministicEscalationModel()
    now = datetime.now(timezone.utc)

    weather = WeatherEvidence(
        provider="open_meteo",
        fetched_at=now,
        observation_timestamp=now,
        latitude=16.2415,
        longitude=80.6433,
        temperature_c=25.0,
        precipitation_mm=0.0,
        wind_speed_mps=3.0,
        data_status=WeatherDataStatus.FRESH,
    )

    raw_acc = RawIncidentData(
        incident_id="SIT-ACC-W",
        is_situation=True,
        situation_doc={"severity_score": 4.0, "emergency_type": "ROAD_ACCIDENT"},
        weather_evidence=weather,
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )

    feat_acc = ExtractedFeatureSet(
        feature_dict={},
        total_data_points=2,
        independent_physical_sources_count=1,
        external_context_sources_count=1,
        weather_evidence=weather,
        data_status=PredictiveDataSufficiency.SUFFICIENT_DATA,
    )

    res30 = model.predict_horizon(30, feat_acc, raw_acc)
    # Weather contribution should be near 0.0 for benign weather in road accident
    assert res30.weather_contribution == 0.0


# -----------------------------------------------------------------------------
# 4. Fusion, Source Independence & Non-Mutation Tests
# -----------------------------------------------------------------------------

def test_sensor_plus_weather_fusion():
    """15: Verify sensor + weather multi-source fusion operates deterministically."""
    model = DeterministicEscalationModel()
    now = datetime.now(timezone.utc)

    weather = WeatherEvidence(
        provider="open_meteo",
        fetched_at=now,
        observation_timestamp=now,
        latitude=16.2415,
        longitude=80.6433,
        precipitation_mm=8.0,
        forecast_periods=[
            WeatherForecastPeriod(horizon_minutes=15, forecast_timestamp=now + timedelta(minutes=15), precipitation_mm=10.0),
            WeatherForecastPeriod(horizon_minutes=30, forecast_timestamp=now + timedelta(minutes=30), precipitation_mm=12.0),
            WeatherForecastPeriod(horizon_minutes=60, forecast_timestamp=now + timedelta(minutes=60), precipitation_mm=15.0),
        ],
        data_status=WeatherDataStatus.FRESH,
    )

    raw_data = RawIncidentData(
        incident_id="SIT-FUSION-W",
        is_situation=True,
        situation_doc={"severity_score": 7.0, "emergency_type": "FLOOD"},
        weather_evidence=weather,
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )

    feat_set = ExtractedFeatureSet(
        feature_dict={
            "sensor_usable_count": 1.0,
            "sensor_breach_ratio": 1.0,
            "sensor_reading_trend": 0.20,
            "weather_precipitation_mm": 8.0,
        },
        total_data_points=10,
        independent_physical_sources_count=2,
        external_context_sources_count=1,
        weather_evidence=weather,
        data_status=PredictiveDataSufficiency.SUFFICIENT_DATA,
    )

    res15 = model.predict_horizon(15, feat_set, raw_data)
    res30 = model.predict_horizon(30, feat_set, raw_data)
    res60 = model.predict_horizon(60, feat_set, raw_data)

    # 19: 15/30/60 differentiation & factor contributions
    assert res15.sensor_contribution is not None
    assert res15.weather_contribution is not None
    assert res30.weather_contribution is not None
    assert res60.weather_contribution is not None
    assert res15.risk_score <= res30.risk_score <= res60.risk_score or res30.is_capped


def test_weather_only_limited_data_behavior():
    """17 & 18: Weather only (0 physical DB records) results in LIMITED_DATA."""
    import asyncio
    provider = DeterministicFeatureProvider()
    now = datetime.now(timezone.utc)

    weather = WeatherEvidence(
        provider="open_meteo",
        fetched_at=now,
        observation_timestamp=now,
        latitude=16.2415,
        longitude=80.6433,
        temperature_c=28.0,
        precipitation_mm=2.0,
        data_status=WeatherDataStatus.FRESH,
    )

    raw_wx_only = RawIncidentData(
        incident_id="SIT-WX-ONLY",
        is_situation=True,
        situation_doc={"severity_score": 5.0, "emergency_type": "FLOOD"},
        weather_evidence=weather,
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )

    feat_res = asyncio.run(provider.extract_features(raw_wx_only))
    assert feat_res.data_status == PredictiveDataSufficiency.LIMITED_DATA
    assert feat_res.independent_physical_sources_count == 0
    assert feat_res.external_context_sources_count == 1


# -----------------------------------------------------------------------------
# 5. Integration API Test & Strict Non-Mutation Audit
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_predictive_api_with_weather_and_non_mutation(client: AsyncClient):
    """20, 21, 22, 23, 24: Integration test verifying weather response and DB immutability."""
    db = get_database()

    # Login as Officer
    officer_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999002", "password": "OfficerPassword@2026"},
    )
    assert officer_res.status_code == 200
    token = officer_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    test_sit_id = "SIT-WX-E2E-01"
    now = datetime.now(timezone.utc)
    await db["situations"].delete_many({"situation_id": test_sit_id})

    test_sit = {
        "situation_id": test_sit_id,
        "cluster_id": "CLS-WX-01",
        "title": "Vadlamudi Barrage Surge",
        "emergency_type": EmergencyType.FLOOD.value,
        "primary_report_id": "REP-WX-1",
        "report_ids": [],
        "report_count": 0,
        "center_location": {"latitude": 16.2415, "longitude": 80.6433, "address": "Vadlamudi Barrage"},
        "impact_zone": {"center_latitude": 16.2415, "center_longitude": 80.6433, "radius_km": 3.0},
        "status": SituationStatus.ACTIVE.value,
        "severity_score": 8.0,
        "severity_level": SeverityLevel.HIGH.value,
        "computed_severity_score": 8.0,
        "computed_severity_level": SeverityLevel.HIGH.value,
        "created_at": now - timedelta(minutes=45),
        "updated_at": now - timedelta(minutes=45),
    }
    await db["situations"].insert_one(test_sit)

    # Document counts before
    sit_cnt_before = await db["situations"].count_documents({})
    rep_cnt_before = await db["citizen_reports"].count_documents({})
    alloc_cnt_before = await db["resource_allocations"].count_documents({})

    res = await client.get(
        f"/api/v1/officer/predictive/incidents/{test_sit_id}?window_minutes=60&horizon_minutes=30",
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()

    # Verify weather structure
    assert "weather" in data
    if data["weather"]:
        w = data["weather"]
        assert w["provider"] in ["open_meteo", "google"]
        assert w["latitude"] == 16.2415
        assert w["longitude"] == 80.6433
        assert w["data_status"] in ["FRESH", "STALE", "UNAVAILABLE", "ERROR"]

    # Verify Forecast contains component contributions
    forecast = data["forecast"]
    assert "weather_contribution" in forecast
    assert "sensor_contribution" in forecast
    assert "incident_contribution" in forecast

    # Strict non-mutation check
    sit_cnt_after = await db["situations"].count_documents({})
    rep_cnt_after = await db["citizen_reports"].count_documents({})
    alloc_cnt_after = await db["resource_allocations"].count_documents({})

    assert sit_cnt_before == sit_cnt_after
    assert rep_cnt_before == rep_cnt_after
    assert alloc_cnt_before == alloc_cnt_after

    # Verify authoritative situation severity unchanged
    sit_doc = await db["situations"].find_one({"situation_id": test_sit_id})
    assert sit_doc["severity_score"] == 8.0
    assert sit_doc["severity_level"] == SeverityLevel.HIGH.value

    # Cleanup
    await db["situations"].delete_many({"situation_id": test_sit_id})


# -----------------------------------------------------------------------------
# 6. Zero Dummy Data Audit
# -----------------------------------------------------------------------------

def test_zero_dummy_data_in_weather_services():
    """25: Scans weather service files for forbidden hardcoded/dummy operational patterns."""
    files = [
        r"c:\Users\Nitesh Kumar\OneDrive\Desktop\resilience ai\backend\app\models\weather.py",
        r"c:\Users\Nitesh Kumar\OneDrive\Desktop\resilience ai\backend\app\services\weather\open_meteo_provider.py",
        r"c:\Users\Nitesh Kumar\OneDrive\Desktop\resilience ai\backend\app\services\weather\google_weather_provider.py",
        r"c:\Users\Nitesh Kumar\OneDrive\Desktop\resilience ai\backend\app\services\weather\weather_service.py",
    ]

    forbidden_patterns = [
        r"generate_dummy",
        r"fake_weather",
        r"mock_rainfall",
        r"sample_weather",
        r"hardcoded_weather",
    ]

    for fp in files:
        if os.path.exists(fp):
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
                for pat in forbidden_patterns:
                    assert not re.findall(pat, content, re.IGNORECASE), f"Forbidden pattern '{pat}' found in {fp}"
