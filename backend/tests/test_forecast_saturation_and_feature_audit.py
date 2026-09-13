import pytest
from datetime import datetime, timezone, timedelta
from app.models.predictive import (
    PredictiveDataSufficiency,
    EscalationRiskLevel,
    TrendDirection,
)
from app.services.predictive.deterministic_escalation_engine import (
    DeterministicEscalationModel,
)
from app.services.predictive.feature_engine import DeterministicFeatureProvider
from app.services.predictive.interfaces import RawIncidentData, ExtractedFeatureSet


@pytest.mark.anyio
async def test_stable_above_threshold_sensor_is_stable_not_rising():
    """
    Requirement 1: Stable above-threshold sensor readings = BREACH but STABLE trend (not automatically RISING).
    """
    now = datetime.now(timezone.utc)
    provider = DeterministicFeatureProvider()
    model = DeterministicEscalationModel()

    # 111 constant readings at 3.96m above 2.5m threshold (0% change)
    readings = [
        {
            "reading_id": f"RD-{i}",
            "sensor_id": "SNS-HDRCM6GT",
            "value": 3.96,
            "threshold": 2.5,
            "is_breach": True,
            "timestamp": now - timedelta(minutes=55) + timedelta(seconds=i * 30),
        }
        for i in range(111)
    ]

    raw_data = RawIncidentData(
        incident_id="SIT-FLOOD-STABLE",
        is_situation=True,
        situation_doc={
            "situation_id": "SIT-FLOOD-STABLE",
            "severity_score": 9.3,
            "severity_level": "CRITICAL",
        },
        sensor_docs=[
            {
                "sensor_id": "SNS-HDRCM6GT",
                "name": "Vadlamudi gate",
                "status": "ACTIVE",
                "health_state": "HEALTHY",
                "threshold": 2.5,
            }
        ],
        sensor_readings=readings,
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )

    feature_set = await provider.extract_features(raw_data)
    assert feature_set.feature_dict.get("sensor_breach_ratio") == 1.0
    assert abs(feature_set.feature_dict.get("sensor_reading_trend", 0.0)) < 0.01  # Zero slope

    res_15 = model.predict_horizon(15, feature_set, raw_data)
    res_30 = model.predict_horizon(30, feature_set, raw_data)
    res_60 = model.predict_horizon(60, feature_set, raw_data)

    # Trend must be STABLE because rate of change is zero despite 100% breach ratio
    assert res_15.trend == TrendDirection.STABLE
    assert res_30.trend == TrendDirection.STABLE
    assert res_60.trend == TrendDirection.STABLE

    # Scores should remain at baseline anchor (0.93), not saturated at 0.98
    assert res_30.risk_score == 0.93
    assert res_30.is_capped is False


@pytest.mark.anyio
async def test_increasing_sensor_trajectory_is_rising():
    """
    Requirement 2: Genuinely increasing sensor readings = RISING trend.
    """
    now = datetime.now(timezone.utc)
    provider = DeterministicFeatureProvider()
    model = DeterministicEscalationModel()

    # Increasing water level from 2.6m to 3.96m
    readings = [
        {
            "reading_id": f"RD-INC-{i}",
            "sensor_id": "SNS-HDRCM6GT",
            "value": 2.6 + (i * 0.015),
            "threshold": 2.5,
            "is_breach": True,
            "timestamp": now - timedelta(minutes=55) + timedelta(seconds=i * 30),
        }
        for i in range(100)
    ]

    raw_data = RawIncidentData(
        incident_id="SIT-FLOOD-RISING",
        is_situation=True,
        situation_doc={
            "situation_id": "SIT-FLOOD-RISING",
            "severity_score": 9.3,
            "severity_level": "CRITICAL",
        },
        sensor_docs=[
            {
                "sensor_id": "SNS-HDRCM6GT",
                "name": "Vadlamudi gate",
                "status": "ACTIVE",
                "health_state": "HEALTHY",
                "threshold": 2.5,
            }
        ],
        sensor_readings=readings,
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )

    feature_set = await provider.extract_features(raw_data)
    assert feature_set.feature_dict.get("sensor_reading_trend", 0.0) > 0.05

    res_30 = model.predict_horizon(30, feature_set, raw_data)
    assert res_30.trend == TrendDirection.RISING
    assert res_30.is_capped is True
    assert res_30.risk_score == 0.98
    assert res_30.raw_score > 0.98


@pytest.mark.anyio
async def test_decreasing_sensor_trajectory_is_falling():
    """
    Requirement 3: Decreasing sensor readings = FALLING trend.
    """
    now = datetime.now(timezone.utc)
    provider = DeterministicFeatureProvider()
    model = DeterministicEscalationModel()

    # Decreasing water level from 3.96m to 2.4m
    readings = [
        {
            "reading_id": f"RD-DEC-{i}",
            "sensor_id": "SNS-HDRCM6GT",
            "value": 3.96 - (i * 0.015),
            "threshold": 2.5,
            "is_breach": True,
            "timestamp": now - timedelta(minutes=55) + timedelta(seconds=i * 30),
        }
        for i in range(100)
    ]

    raw_data = RawIncidentData(
        incident_id="SIT-FLOOD-FALLING",
        is_situation=True,
        situation_doc={
            "situation_id": "SIT-FLOOD-FALLING",
            "severity_score": 8.5,
            "severity_level": "CRITICAL",
        },
        sensor_docs=[
            {
                "sensor_id": "SNS-HDRCM6GT",
                "name": "Vadlamudi gate",
                "status": "ACTIVE",
                "health_state": "HEALTHY",
                "threshold": 2.5,
            }
        ],
        sensor_readings=readings,
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )

    feature_set = await provider.extract_features(raw_data)
    assert feature_set.feature_dict.get("sensor_reading_trend", 0.0) < -0.05

    res_30 = model.predict_horizon(30, feature_set, raw_data)
    assert res_30.trend == TrendDirection.FALLING
    assert res_30.risk_score < 0.85


@pytest.mark.anyio
async def test_111_readings_aggregation_and_provenance():
    """
    Requirement 5 & 6: 111 raw readings from 1 sensor are properly aggregated
    and distinct from independent physical sources count.
    """
    now = datetime.now(timezone.utc)
    provider = DeterministicFeatureProvider()

    readings = [
        {
            "reading_id": f"RD-{i}",
            "sensor_id": "SNS-HDRCM6GT",
            "value": 3.79 + (0.17 if i > 50 else 0.0),
            "threshold": 2.5,
            "is_breach": True,
            "timestamp": now - timedelta(minutes=55) + timedelta(seconds=i * 25),
        }
        for i in range(111)
    ]

    raw_data = RawIncidentData(
        incident_id="SIT-PROVENANCE",
        is_situation=True,
        situation_doc={"situation_id": "SIT-PROVENANCE", "severity_score": 9.3},
        sensor_docs=[{"sensor_id": "SNS-HDRCM6GT", "name": "Vadlamudi gate", "status": "ACTIVE", "health_state": "HEALTHY", "threshold": 2.5}],
        sensor_readings=readings,
        window_start=now - timedelta(minutes=60),
        window_end=now,
        window_minutes=60,
    )

    feature_set = await provider.extract_features(raw_data)
    assert feature_set.data_points_used.get("sensor_readings") == 111
    # Independent physical sources count is 1 (the single sensor)
    assert feature_set.independent_sources_count == 1

    # Check rich metadata provenance
    breach_feat = next(f for f in feature_set.features if f.name == "sensor_breach_ratio")
    assert breach_feat.metadata["raw_records"] == 111
    assert breach_feat.metadata["sensor_name"] == "Vadlamudi gate"
    assert breach_feat.metadata["threshold"] == 2.5
    assert breach_feat.metadata["min_value"] == 3.79
    assert breach_feat.metadata["max_value"] == 3.96
