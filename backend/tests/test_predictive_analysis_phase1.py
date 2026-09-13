import re
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient

from app.db.mongodb import get_database
from app.models.enums import (
    EmergencyType,
    SeverityLevel,
    SituationStatus,
    SensorType,
    SensorStatus,
    SensorReportingState,
    SensorHealthState,
)
from app.models.predictive import (
    IncidentPredictionResponse,
    PredictiveTrendResponse,
    PredictiveFeaturesResponse,
    PredictiveHealthResponse,
    PredictiveDataSufficiency,
    EscalationRiskLevel,
    TrendDirection,
)
from app.services.predictive.predictive_service import PredictiveService
from app.services.predictive.deterministic_escalation_engine import (
    DeterministicEscalationModel,
)
from app.services.predictive.feature_engine import DeterministicFeatureProvider
from app.services.predictive.interfaces import RawIncidentData, ExtractedFeatureSet


# -----------------------------------------------------------------------------
# Unit Tests for Mathematical Scoring Engine & Determinism
# -----------------------------------------------------------------------------

def test_deterministic_escalation_model_reproducibility():
    """
    Verify that given the same exact extracted feature set, the model
    produces 100% identical risk score, level, and trend.
    """
    model = DeterministicEscalationModel()
    now = datetime.now(timezone.utc)

    raw_data = RawIncidentData(
        incident_id="SIT-DET-TEST1",
        is_situation=True,
        situation_doc={
            "situation_id": "SIT-DET-TEST1",
            "severity_score": 6.5,
            "severity_level": "HIGH",
            "created_at": now - timedelta(minutes=45),
        },
        report_docs=[
            {"report_id": "REP-1", "created_at": now - timedelta(minutes=40), "citizen_impact_level": "HIGH"},
            {"report_id": "REP-2", "created_at": now - timedelta(minutes=10), "citizen_impact_level": "CRITICAL"},
        ],
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )

    feature_set = ExtractedFeatureSet(
        feature_dict={
            "incident_report_count": 2.0,
            "report_rate_change": 0.5,
            "critical_report_ratio": 1.0,
            "sensor_usable_count": 0.0,
        },
        total_data_points=2,
        data_status=PredictiveDataSufficiency.SUFFICIENT_DATA,
        limitations=[],
    )

    res1 = model.predict_horizon(30, feature_set, raw_data)
    res2 = model.predict_horizon(30, feature_set, raw_data)

    assert res1.risk_score == res2.risk_score
    assert res1.risk_level == res2.risk_level
    assert res1.trend == res2.trend
    assert res1.confidence_score == res2.confidence_score
    assert res1.risk_score >= 0.0 and res1.risk_score <= 1.0


def test_data_sufficiency_states():
    """
    Verify data sufficiency transitions between NO_DATA, INSUFFICIENT_DATA, LIMITED_DATA, and SUFFICIENT_DATA.
    """
    model = DeterministicEscalationModel()
    now = datetime.now(timezone.utc)

    # 1. Zero data
    zero_raw = RawIncidentData(
        incident_id="SIT-ZERO",
        is_situation=True,
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )
    zero_feat = ExtractedFeatureSet(
        feature_dict={},
        total_data_points=0,
        data_status=PredictiveDataSufficiency.NO_DATA,
    )
    res_zero = model.predict_horizon(30, zero_feat, zero_raw)
    assert res_zero.data_status == PredictiveDataSufficiency.NO_DATA
    assert res_zero.risk_score == 0.0
    assert res_zero.trend == TrendDirection.UNKNOWN

    # 2. Single static point (Insufficient history)
    one_raw = RawIncidentData(
        incident_id="SIT-ONE",
        is_situation=True,
        situation_doc={"severity_score": 4.0},
        report_docs=[{"report_id": "REP-1", "created_at": now - timedelta(minutes=50)}],
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )
    one_feat = ExtractedFeatureSet(
        feature_dict={"incident_report_count": 1.0},
        total_data_points=1,
        data_status=PredictiveDataSufficiency.INSUFFICIENT_DATA,
    )
    res_one = model.predict_horizon(30, one_feat, one_raw)
    assert res_one.data_status == PredictiveDataSufficiency.INSUFFICIENT_DATA
    assert res_one.trend == TrendDirection.UNKNOWN


def test_trend_detection_rising_and_falling():
    """
    Verify temporal trend detection for accelerating (rising) vs decelerating (falling) patterns.
    """
    model = DeterministicEscalationModel()
    now = datetime.now(timezone.utc)

    raw_data = RawIncidentData(
        incident_id="SIT-TREND",
        is_situation=True,
        situation_doc={"severity_score": 5.0},
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )

    # Accelerating report intake & active sensor breach -> RISING
    rising_feat = ExtractedFeatureSet(
        feature_dict={
            "report_rate_change": 0.60,
            "critical_report_ratio": 0.80,
            "sensor_usable_count": 1.0,
            "sensor_breach_ratio": 1.0,
            "sensor_reading_trend": 0.35,
        },
        total_data_points=8,
        data_status=PredictiveDataSufficiency.SUFFICIENT_DATA,
    )
    res_rising = model.predict_horizon(30, rising_feat, raw_data)
    assert res_rising.trend == TrendDirection.RISING
    assert res_rising.risk_level in [EscalationRiskLevel.HIGH, EscalationRiskLevel.CRITICAL]

    # Decelerating report intake & zero breaches -> FALLING
    falling_feat = ExtractedFeatureSet(
        feature_dict={
            "report_rate_change": -0.60,
            "critical_report_ratio": 0.0,
            "sensor_usable_count": 1.0,
            "sensor_breach_ratio": 0.0,
            "sensor_reading_trend": -0.20,
        },
        total_data_points=8,
        data_status=PredictiveDataSufficiency.SUFFICIENT_DATA,
    )
    res_falling = model.predict_horizon(30, falling_feat, raw_data)
    assert res_falling.trend == TrendDirection.FALLING


def test_sensor_health_weighting():
    """
    Verify that stale sensors have discounted evidentiary weight,
    and inactive/unavailable sensors are excluded.
    """
    now = datetime.now(timezone.utc)
    provider = DeterministicFeatureProvider()

    # Raw data with 1 healthy sensor and 1 stale sensor
    raw_with_stale = RawIncidentData(
        incident_id="SIT-SNS-HEALTH",
        is_situation=True,
        situation_doc={"situation_id": "SIT-SNS-HEALTH", "severity_score": 5.0},
        sensor_docs=[
            {"sensor_id": "SNS-STALE", "status": "ACTIVE", "health_state": "STALE", "reporting_state": "STALE"},
            {"sensor_id": "SNS-INACTIVE", "status": "INACTIVE", "health_state": "INACTIVE"},
        ],
        sensor_readings=[
            {"reading_id": "RD-1", "sensor_id": "SNS-STALE", "value": 15.0, "is_breach": True, "timestamp": now - timedelta(minutes=20)},
        ],
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )

    import asyncio
    feat_res = asyncio.run(provider.extract_features(raw_with_stale))
    # Stale sensor triggers 50% discount limitation
    assert any("Sensor data is stale" in lim for lim in feat_res.limitations)
    # Inactive sensor excluded
    assert feat_res.feature_dict.get("sensor_usable_count") == 1.0


# -----------------------------------------------------------------------------
# Integration API Tests with Database & Non-Mutation Guarantees
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_predictive_health_endpoint(client: AsyncClient):
    """
    Verify /officer/predictive/health returns engine health and policy flags.
    """
    # Login as Officer
    officer_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999002", "password": "OfficerPassword@2026"},
    )
    assert officer_res.status_code == 200
    token = officer_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.get("/api/v1/officer/predictive/health", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert data["zero_dummy_data_enforced"] is True
    assert data["advisory_mode_enforced"] is True
    assert 15 in data["supported_horizons_minutes"]
    assert 30 in data["supported_horizons_minutes"]
    assert 60 in data["supported_horizons_minutes"]


@pytest.mark.anyio
async def test_predictive_rbac_enforcement(client: AsyncClient):
    """
    Verify unauthenticated users or non-officer roles are rejected from predictive intelligence.
    """
    from app.core.security import create_access_token
    db = get_database()

    # 1. Unauthenticated request
    unauth_res = await client.get("/api/v1/officer/predictive/incidents/SIT-TEST")
    assert unauth_res.status_code == 401

    # 2. Login as Citizen (unauthorized role)
    cit_phone = "9876543210"
    await db["users"].update_one(
        {"phone": cit_phone},
        {
            "$set": {
                "phone": cit_phone,
                "full_name": "Test Citizen",
                "role": "CITIZEN",
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
    cit_token = create_access_token(data={"sub": cit_phone, "role": "CITIZEN", "user_id": "cit_1"})
    cit_headers = {"Authorization": f"Bearer {cit_token}"}
    denied_res = await client.get("/api/v1/officer/predictive/incidents/SIT-TEST", headers=cit_headers)
    assert denied_res.status_code in [401, 403]


@pytest.mark.anyio
async def test_predictive_incident_flow_and_non_mutation(client: AsyncClient):
    """
    Verify predictive endpoint generates explainable prediction without mutating DB records,
    without changing authoritative severity, and preserving zero-dummy-data rules.
    """
    db = get_database()

    # Login as Officer
    officer_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999002", "password": "OfficerPassword@2026"},
    )
    assert officer_res.status_code == 200
    token = officer_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create a genuine test situation in DB for verification
    test_sit_id = "SIT-PRED-TEST-01"
    now = datetime.now(timezone.utc)
    await db["situations"].delete_many({"situation_id": test_sit_id})
    await db["citizen_reports"].delete_many({"situation_id": test_sit_id})

    # Insert test situation
    test_sit = {
        "situation_id": test_sit_id,
        "cluster_id": "CLS-PRED-01",
        "title": "Urban Flood Surge Monitoring",
        "emergency_type": EmergencyType.FLOOD.value,
        "primary_report_id": "REP-PRED-1",
        "report_ids": ["REP-PRED-1", "REP-PRED-2", "REP-PRED-3"],
        "report_count": 3,
        "center_location": {"latitude": 16.2415, "longitude": 80.6433, "address": "Station Road"},
        "impact_zone": {"center_latitude": 16.2415, "center_longitude": 80.6433, "radius_km": 3.5},
        "status": SituationStatus.ACTIVE.value,
        "severity_score": 7.5,
        "severity_level": SeverityLevel.HIGH.value,
        "computed_severity_score": 7.5,
        "computed_severity_level": SeverityLevel.HIGH.value,
        "created_at": now - timedelta(minutes=45),
        "updated_at": now - timedelta(minutes=45),
    }
    await db["situations"].insert_one(test_sit)

    # Insert genuine test reports
    reports = [
        {
            "report_id": "REP-PRED-1",
            "situation_id": test_sit_id,
            "emergency_type": EmergencyType.FLOOD.value,
            "description": "Rising water level near bridge",
            "citizen_impact_level": "HIGH",
            "created_at": now - timedelta(minutes=40),
            "status": "VERIFIED",
        },
        {
            "report_id": "REP-PRED-2",
            "situation_id": test_sit_id,
            "emergency_type": EmergencyType.FLOOD.value,
            "description": "Submerged vehicles reported",
            "citizen_impact_level": "CRITICAL",
            "created_at": now - timedelta(minutes=15),
            "status": "VERIFIED",
        },
        {
            "report_id": "REP-PRED-3",
            "situation_id": test_sit_id,
            "emergency_type": EmergencyType.FLOOD.value,
            "description": "Access road blocked by high current",
            "citizen_impact_level": "CRITICAL",
            "created_at": now - timedelta(minutes=5),
            "status": "VERIFIED",
        },
    ]
    await db["citizen_reports"].insert_many(reports)

    # Count DB documents before prediction request
    sit_count_before = await db["situations"].count_documents({})
    rep_count_before = await db["citizen_reports"].count_documents({})
    alloc_count_before = await db["resource_allocations"].count_documents({})

    # 1. Fetch Prediction API
    pred_res = await client.get(
        f"/api/v1/officer/predictive/incidents/{test_sit_id}?window_minutes=60&horizon_minutes=30",
        headers=headers,
    )
    assert pred_res.status_code == 200
    pred_data = pred_res.json()

    # Validate Response Schema
    assert pred_data["incident_id"] == test_sit_id
    assert pred_data["current_authoritative_severity"] == "HIGH"
    assert pred_data["current_severity_score"] == 7.5
    assert pred_data["prediction_status"] == "AVAILABLE"
    assert pred_data["data_status"] == PredictiveDataSufficiency.SUFFICIENT_DATA

    # Validate Forecast & Multi-horizons
    assert "forecast" in pred_data
    forecast = pred_data["forecast"]
    assert forecast["horizon_minutes"] == 30
    assert forecast["risk_level"] in ["HIGH", "CRITICAL"]
    assert forecast["risk_score"] >= 0.0 and forecast["risk_score"] <= 1.0
    assert forecast["trend"] == TrendDirection.RISING
    assert len(forecast["contributing_factors"]) > 0

    assert "15m" in pred_data["horizons"]
    assert "30m" in pred_data["horizons"]
    assert "60m" in pred_data["horizons"]

    # Validate Features & Provenance
    assert len(pred_data["features"]) > 0
    assert any(f["name"] == "report_rate_change" for f in pred_data["features"])
    assert pred_data["data_points_used"]["citizen_reports"] == 3

    # Validate Advisory Safety Notice
    assert "ADVISORY ONLY" in pred_data["advisory_notice"]

    # 2. Fetch Trend API
    trend_res = await client.get(
        f"/api/v1/officer/predictive/incidents/{test_sit_id}/trend?window_minutes=60",
        headers=headers,
    )
    assert trend_res.status_code == 200
    trend_data = trend_res.json()
    assert len(trend_data["timeline_points"]) == 4  # Current + 15m + 30m + 60m
    assert trend_data["timeline_points"][0]["time_label"] == "Current"

    # 3. Fetch Features API
    feat_res = await client.get(
        f"/api/v1/officer/predictive/incidents/{test_sit_id}/features?window_minutes=60",
        headers=headers,
    )
    assert feat_res.status_code == 200
    feat_data = feat_res.json()
    assert feat_data["total_records_evaluated"] >= 3

    # 4. Strict Non-Mutation Audit: Verify ZERO database records were created or modified
    sit_count_after = await db["situations"].count_documents({})
    rep_count_after = await db["citizen_reports"].count_documents({})
    alloc_count_after = await db["resource_allocations"].count_documents({})

    assert sit_count_before == sit_count_after
    assert rep_count_before == rep_count_after
    assert alloc_count_before == alloc_count_after

    # Verify authoritative situation severity in DB was NOT mutated
    sit_doc_after = await db["situations"].find_one({"situation_id": test_sit_id})
    assert sit_doc_after["severity_score"] == 7.5
    assert sit_doc_after["severity_level"] == SeverityLevel.HIGH.value

    # Cleanup test records
    await db["situations"].delete_many({"situation_id": test_sit_id})
    await db["citizen_reports"].delete_many({"situation_id": test_sit_id})


@pytest.mark.anyio
async def test_data_poor_incident_honest_insufficient_state(client: AsyncClient):
    """
    Verify that a situation with minimal/zero historical evidence returns a truthful
    INSUFFICIENT_DATA or LIMITED_DATA status without fake predictions or fabricated data points.
    """
    db = get_database()

    # Login as Officer
    officer_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999002", "password": "OfficerPassword@2026"},
    )
    assert officer_res.status_code == 200
    token = officer_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    test_poor_id = "SIT-POOR-DATA-01"
    now = datetime.now(timezone.utc)
    await db["situations"].delete_many({"situation_id": test_poor_id})

    # Insert bare situation with 0 reports in historical window
    test_sit = {
        "situation_id": test_poor_id,
        "cluster_id": "CLS-POOR-01",
        "title": "Uncorroborated Smoke Report",
        "emergency_type": EmergencyType.FIRE.value,
        "primary_report_id": "REP-POOR-1",
        "report_ids": [],
        "report_count": 0,
        "center_location": {"latitude": 16.2415, "longitude": 80.6433, "address": "Remote Outpost"},
        "impact_zone": {"center_latitude": 16.2415, "center_longitude": 80.6433, "radius_km": 1.0},
        "status": SituationStatus.ACTIVE.value,
        "severity_score": 3.0,
        "severity_level": SeverityLevel.LOW.value,
        "computed_severity_score": 3.0,
        "computed_severity_level": SeverityLevel.LOW.value,
        "created_at": now - timedelta(days=2),  # Created 2 days ago
        "updated_at": now - timedelta(days=2),
    }
    await db["situations"].insert_one(test_sit)

    res = await client.get(
        f"/api/v1/officer/predictive/incidents/{test_poor_id}?window_minutes=60",
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()

    # Truthful empty/insufficient/limited data state
    assert data["data_status"] in [PredictiveDataSufficiency.NO_DATA, PredictiveDataSufficiency.INSUFFICIENT_DATA, PredictiveDataSufficiency.LIMITED_DATA]
    assert len(data["missing_features"]) > 0
    assert any("citizen_reports" in mf for mf in data["missing_features"])

    # Cleanup
    await db["situations"].delete_many({"situation_id": test_poor_id})


@pytest.mark.anyio
async def test_priority_agent_advisory_prediction_ingestion():
    """
    Verify PriorityAgent consumes advisory predictive signals in structured_output
    while strictly preserving authoritative severity calculation.
    """
    from app.services.agents.adapters.priority_agent import PriorityAgent
    from app.models.agent import AgentContext

    agent = PriorityAgent()
    context = AgentContext(
        situation_id="SIT-ADVISORY-TEST",
        emergency_type="FLOOD",
        description="High water rising near river bank",
        report_count=3,
        parameters={
            "predictive_signal": {
                "forecast": {
                    "risk_level": "CRITICAL",
                    "risk_score": 0.88,
                    "trend": "RISING",
                    "confidence_score": 0.85,
                }
            }
        },
    )

    result = await agent.execute(context)
    assert result.status.value == "COMPLETED"
    structured = result.structured_output

    # Priority Agent structured output contains advisory predictive signals
    assert structured["predicted_escalation_risk"] == "CRITICAL"
    assert structured["prediction_confidence"] == 0.85
    assert structured["prediction_trend"] == "RISING"

    # Current priority remains based on deterministic emergency severity engine (not automatically overwritten to CRITICAL)
    assert structured["current_priority"] in ["HIGH", "MEDIUM"]


# -----------------------------------------------------------------------------
# Explicit Zero Dummy Data Audit Test
# -----------------------------------------------------------------------------

def test_zero_dummy_data_code_audit():
    """
    Scans newly created predictive analysis files for forbidden mock/dummy/seed data generation.
    """
    import os

    files_to_check = [
        r"c:\Users\Nitesh Kumar\OneDrive\Desktop\resilience ai\backend\app\models\predictive.py",
        r"c:\Users\Nitesh Kumar\OneDrive\Desktop\resilience ai\backend\app\services\predictive\predictive_service.py",
        r"c:\Users\Nitesh Kumar\OneDrive\Desktop\resilience ai\backend\app\services\predictive\feature_engine.py",
        r"c:\Users\Nitesh Kumar\OneDrive\Desktop\resilience ai\backend\app\services\predictive\deterministic_escalation_engine.py",
        r"c:\Users\Nitesh Kumar\OneDrive\Desktop\resilience ai\backend\app\api\v1\endpoints\predictive.py",
    ]

    forbidden_patterns = [
        r"generate_dummy",
        r"seed_dummy",
        r"fake_historical",
        r"mock_sensor_readings",
        r"mock_reports",
        r"sample_prediction_chart",
        r"hardcoded_chart",
    ]

    for filepath in files_to_check:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                for pattern in forbidden_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    assert not matches, f"Forbidden dummy data pattern '{pattern}' found in {filepath}"

