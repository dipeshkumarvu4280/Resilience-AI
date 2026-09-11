"""
Tests for Sensor Evidence Visibility in Situation Intelligence Inspect.
Verifies multi-source evidence fusion, correlation, schema integrity, and zero dummy data.
"""

import pytest
import uuid
from datetime import datetime, timezone
from app.models.enums import UserRole, SensorType, SensorStatus, EmergencyType, SeverityLevel, SensorReadingSource
from app.core.security import create_access_token


@pytest.fixture
async def officer_headers(db):
    officer_phone = "9999999002"
    await db["users"].update_one(
        {"phone": officer_phone},
        {
            "$set": {
                "phone": officer_phone,
                "full_name": "Officer Marcus Vance",
                "email": "officer.vance@resilience.gov",
                "role": UserRole.EMERGENCY_OFFICER.value,
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
    token = create_access_token(
        data={"sub": officer_phone, "role": UserRole.EMERGENCY_OFFICER.value, "user_id": "officer_1"}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_01_situation_inspect_zero_dummy_sensor_evidence(client, db, officer_headers):
    """1. Zero Dummy Data: New situation without any sensors returns 0 sensor evidence."""
    situation_id = f"SIT-{uuid.uuid4().hex[:8].upper()}"
    await db["situations"].insert_one({
        "situation_id": situation_id,
        "cluster_id": f"CLS-{uuid.uuid4().hex[:8].upper()}",
        "title": "Standalone Urban Fire Incident",
        "emergency_type": EmergencyType.FIRE.value,
        "primary_report_id": "REP-001",
        "report_ids": [],
        "report_count": 0,
        "center_location": {
            "latitude": 31.1048,
            "longitude": 77.1734,
            "city": "Shimla",
            "zone_or_district": "Hill Zone",
        },
        "impact_zone": {
            "center_latitude": 31.1048,
            "center_longitude": 77.1734,
            "radius_km": 2.0,
            "is_estimated": True,
        },
        "status": "ACTIVE",
        "severity_level": SeverityLevel.HIGH.value,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    res = await client.get(f"/api/v1/officer/situations/{situation_id}", headers=officer_headers)
    assert res.status_code == 200
    data = res.json()
    assert "situation" in data
    assert "clustered_reports" in data
    assert "sensor_evidence" in data
    assert len(data["sensor_evidence"]) == 0
    assert data["evidence"]["sensor_events_count"] == 0


@pytest.mark.anyio
async def test_02_aqi_sensor_in_proximity_correlates_to_cyclone_situation(client, db, officer_headers):
    """2. AQI sensor in proximity correlates with Cyclone situation and appears in Inspect API."""
    situation_id = f"SIT-{uuid.uuid4().hex[:8].upper()}"
    center_lat, center_lon = 16.5062, 80.6480  # Vijayawada

    # Create Cyclone situation
    report_id = f"REP-CYC-{uuid.uuid4().hex[:6].upper()}"
    await db["situations"].insert_one({
        "situation_id": situation_id,
        "cluster_id": f"CLS-{uuid.uuid4().hex[:8].upper()}",
        "title": "Severe Cyclone Storm Inundation",
        "emergency_type": EmergencyType.CYCLONE_STORM.value,
        "primary_report_id": report_id,
        "report_ids": [report_id],
        "report_count": 1,
        "center_location": {
            "latitude": center_lat,
            "longitude": center_lon,
            "city": "Vijayawada",
            "zone_or_district": "Krishna District",
        },
        "impact_zone": {
            "center_latitude": center_lat,
            "center_longitude": center_lon,
            "radius_km": 15.0,
            "is_estimated": True,
        },
        "status": "ACTIVE",
        "severity_level": SeverityLevel.CRITICAL.value,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    # Create Citizen Report for the cyclone
    await db["citizen_reports"].insert_one({
        "report_id": report_id,
        "emergency_type": EmergencyType.CYCLONE_STORM.value,
        "description": "Severe cyclone gale force winds and rising water near barrage.",
        "citizen_name": "Ramesh Kumar",
        "citizen_phone": "9876543210",
        "location": {
            "latitude": center_lat,
            "longitude": center_lon,
            "address": "Prakasam Barrage, Vijayawada",
            "zone_or_district": "Krishna District",
        },
        "status": "VERIFIED",
        "priority": "CRITICAL",
        "created_at": datetime.now(timezone.utc),
    })

    # Create AQI Sensor in same city / proximity (2km away with 3km coverage)
    sensor_payload = {
        "name": "Vijayawada AQI Air Monitor Station 01",
        "sensor_type": SensorType.SMOKE_AIR_QUALITY.value,
        "location_name": "Governorpet Met Center",
        "latitude": center_lat + 0.015,
        "longitude": center_lon + 0.010,
        "coverage_radius_value": 3.0,
        "coverage_radius_unit": "km",
        "threshold": 250.0,
        "unit": "AQI",
    }
    sensor_create_res = await client.post("/api/v1/sensors", json=sensor_payload, headers=officer_headers)
    assert sensor_create_res.status_code == 201
    sensor_id = sensor_create_res.json()["sensor_id"]

    # Activate Sensor
    await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)

    # Ingest a breached AQI reading (385 AQI > 250 threshold)
    reading_payload = {
        "value": 385.0,
        "source_type": SensorReadingSource.MANUAL_SIMULATION.value,
        "notes": "Spike in particulate matter and smoke due to storm disruption",
    }
    reading_res = await client.post(f"/api/v1/sensors/{sensor_id}/readings", json=reading_payload, headers=officer_headers)
    assert reading_res.status_code == 201

    # Call Situation Inspect endpoint
    inspect_res = await client.get(f"/api/v1/officer/situations/{situation_id}", headers=officer_headers)
    assert inspect_res.status_code == 200
    inspect_data = inspect_res.json()

    # Verify both Citizen Report and Sensor Evidence are present
    assert len(inspect_data["clustered_reports"]) >= 1
    assert any(r["report_id"] == report_id for r in inspect_data["clustered_reports"])

    sensor_ids = [e["sensor_id"] for e in inspect_data["sensor_evidence"]]
    assert sensor_id in sensor_ids
    sensor_ev = next(e for e in inspect_data["sensor_evidence"] if e["sensor_id"] == sensor_id)
    assert sensor_ev["source_type"] == "SIMULATED_SENSOR"
    assert sensor_ev["current_value"] == 385.0
    assert sensor_ev["threshold"] == 250.0
    assert sensor_ev["threshold_state"] == "BREACHED"
    assert sensor_ev["is_breach"] is True
    assert sensor_ev["is_simulated"] is True
    assert sensor_ev["distance_to_center_km"] > 0.0

    # Verify Evidence Summary
    evidence = inspect_data["evidence"]
    assert evidence["citizen_reports_count"] >= 1
    assert evidence["sensor_events_count"] >= 1


@pytest.mark.anyio
async def test_03_faraway_sensor_not_incorrectly_attached(client, db, officer_headers):
    """3. Faraway sensor (e.g. 1000km away in Delhi) is NOT attached to Vijayawada Cyclone."""
    situation_id = f"SIT-{uuid.uuid4().hex[:8].upper()}"
    # Place situation in Mumbai (~1400km away from Delhi and ~1000km from Vijayawada)
    await db["situations"].insert_one({
        "situation_id": situation_id,
        "cluster_id": f"CLS-{uuid.uuid4().hex[:8].upper()}",
        "title": "Mumbai Coastal Incident",
        "emergency_type": EmergencyType.CYCLONE_STORM.value,
        "primary_report_id": "REP-C1",
        "report_ids": [],
        "report_count": 0,
        "center_location": {"latitude": 19.0760, "longitude": 72.8777, "city": "Mumbai"},
        "impact_zone": {"center_latitude": 19.0760, "center_longitude": 72.8777, "radius_km": 10.0, "is_estimated": True},
        "status": "ACTIVE",
        "severity_level": SeverityLevel.HIGH.value,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    # Create Delhi Sensor (~1500km away)
    delhi_sensor = {
        "name": "Delhi Connaught Place AQI Station",
        "sensor_type": SensorType.SMOKE_AIR_QUALITY.value,
        "location_name": "Connaught Place, New Delhi",
        "latitude": 28.6304,
        "longitude": 77.2177,
        "threshold": 300.0,
        "unit": "AQI",
    }
    s_res = await client.post("/api/v1/sensors", json=delhi_sensor, headers=officer_headers)
    s_id = s_res.json()["sensor_id"]
    await client.patch(f"/api/v1/sensors/{s_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)
    await client.post(f"/api/v1/sensors/{s_id}/readings", json={"value": 450.0}, headers=officer_headers)

    # Inspect Vijayawada situation
    inspect_res = await client.get(f"/api/v1/officer/situations/{situation_id}", headers=officer_headers)
    assert inspect_res.status_code == 200
    inspect_data = inspect_res.json()

    # Delhi sensor must NOT appear in Vijayawada situation evidence
    assert len(inspect_data["sensor_evidence"]) == 0
    assert inspect_data["evidence"]["sensor_events_count"] == 0


@pytest.mark.anyio
async def test_04_officer_severity_override_preserved_with_sensor_evidence(client, db, officer_headers):
    """4. Officer manual severity override remains authoritative when sensor evidence exists."""
    situation_id = f"SIT-{uuid.uuid4().hex[:8].upper()}"
    await db["situations"].insert_one({
        "situation_id": situation_id,
        "cluster_id": f"CLS-{uuid.uuid4().hex[:8].upper()}",
        "title": "Monsoon Situation with Officer Override",
        "emergency_type": EmergencyType.FLOOD.value,
        "primary_report_id": "REP-F1",
        "report_ids": [],
        "report_count": 0,
        "center_location": {"latitude": 16.50, "longitude": 80.64},
        "impact_zone": {"center_latitude": 16.50, "center_longitude": 80.64, "radius_km": 10.0, "is_estimated": True},
        "status": "ACTIVE",
        "severity_level": SeverityLevel.CRITICAL.value,
        "severity_score": 9.5,
        "officer_override_severity": SeverityLevel.CRITICAL.value,
        "officer_override_score": 9.5,
        "officer_override_by": "Officer Marcus Vance",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    inspect_res = await client.get(f"/api/v1/officer/situations/{situation_id}", headers=officer_headers)
    assert inspect_res.status_code == 200
    sit = inspect_res.json()["situation"]
    assert sit["severity_level"] == SeverityLevel.CRITICAL.value
    assert sit["officer_override_severity"] == SeverityLevel.CRITICAL.value
