import pytest
import uuid
import math
from datetime import datetime, timezone
from httpx import AsyncClient

from app.models.enums import SensorType, EmergencyType, SeverityLevel, SensorStatus, UserRole
from app.core.security import create_access_token
from app.services.resource_matching import haversine_distance_km


@pytest.fixture
async def officer_headers(db):
    officer_phone = "9999999003"
    await db["users"].update_one(
        {"phone": officer_phone},
        {
            "$set": {
                "phone": officer_phone,
                "full_name": "Officer Sarah Connor",
                "email": "officer.connor@resilience.gov",
                "role": UserRole.EMERGENCY_OFFICER.value,
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
    token = create_access_token(
        data={"sub": officer_phone, "role": UserRole.EMERGENCY_OFFICER.value, "user_id": "officer_connor"}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_01_create_sensor_without_type_rejected(client: AsyncClient, officer_headers: dict):
    """Create sensor without type is rejected (422 Unprocessable Content)."""
    payload = {
        "name": "Missing Type Sensor",
        "location_name": "Test Location",
        "latitude": 16.5062,
        "longitude": 80.6480,
        "threshold": 100.0,
    }
    res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    assert res.status_code == 422


@pytest.mark.anyio
async def test_02_create_sensor_invalid_type_rejected(client: AsyncClient, officer_headers: dict):
    """Invalid sensor type string is rejected."""
    payload = {
        "name": "Invalid Type Sensor",
        "sensor_type": "NUCLEAR_RADIATION",
        "location_name": "Test Location",
        "latitude": 16.5062,
        "longitude": 80.6480,
        "threshold": 100.0,
    }
    res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    assert res.status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize("stype,expected_unit,default_thresh", [
    (SensorType.WATER_LEVEL.value, "meters", 2.5),
    (SensorType.RAINFALL.value, "mm/hr", 50.0),
    (SensorType.TEMPERATURE.value, "°C", 45.0),
    (SensorType.SMOKE_AIR_QUALITY.value, "AQI", 300.0),
    (SensorType.AQI.value, "AQI", 250.0),
])
async def test_03_create_all_supported_sensor_types(client: AsyncClient, officer_headers: dict, stype: str, expected_unit: str, default_thresh: float):
    """Verify all 5 supported sensor types can be created and persist the canonical enum value."""
    payload = {
        "name": f"Test Sensor {stype}",
        "sensor_type": stype,
        "location_name": f"Station for {stype}",
        "latitude": 16.5000,
        "longitude": 80.6400,
        "threshold": default_thresh,
    }
    res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["sensor_type"] == stype
    assert data["unit"] == expected_unit
    assert data["threshold"] == default_thresh


@pytest.mark.anyio
async def test_04_sensor_type_persisted_in_catalog_detail_and_edit(client: AsyncClient, officer_headers: dict):
    """Verify sensor type is persisted in catalog, retrieve detail, and can be edited."""
    # 1. Create AQI sensor
    payload = {
        "name": "River Air Quality Station",
        "sensor_type": SensorType.AQI.value,
        "location_name": "River Bank",
        "latitude": 16.5100,
        "longitude": 80.6500,
        "threshold": 200.0,
    }
    create_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    assert create_res.status_code == 201
    sensor_id = create_res.json()["sensor_id"]
    assert create_res.json()["sensor_type"] == "AQI"

    # 2. Get Detail
    detail_res = await client.get(f"/api/v1/sensors/{sensor_id}", headers=officer_headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["sensor_type"] == "AQI"

    # 3. Filter by type
    list_res = await client.get("/api/v1/sensors?sensor_type=AQI", headers=officer_headers)
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert any(s["sensor_id"] == sensor_id for s in items)

    # 4. Edit Sensor Type
    edit_res = await client.put(f"/api/v1/sensors/{sensor_id}", json={"sensor_type": SensorType.SMOKE_AIR_QUALITY.value}, headers=officer_headers)
    assert edit_res.status_code == 200
    assert edit_res.json()["sensor_type"] == "SMOKE_AIR_QUALITY"


@pytest.mark.anyio
async def test_05_aqi_sensor_reading_event_monitoring_and_cyclone_correlation(client: AsyncClient, officer_headers: dict, db):
    """
    AQI + CYCLONE END-TO-END VERIFICATION:
    1. Create AQI sensor with explicit AQI type near Cyclone situation.
    2. Activate sensor.
    3. Send real simulated reading exceeding threshold.
    4. Reading generates Sensor Alert and Live Monitoring event with sensor_type="AQI" and source_type="SIMULATED_SENSOR".
    5. Situation Inspect displays sensor in Evidence Sources with sensor_type="AQI".
    """
    # 1. Seed Cyclone situation
    sit_lat, sit_lon = 16.5150, 80.6350
    situation_id = f"SIT-{uuid.uuid4().hex[:8].upper()}"
    report_id = f"REP-CYC-{uuid.uuid4().hex[:6].upper()}"
    
    await db["citizen_reports"].insert_one({
        "report_id": report_id,
        "emergency_type": EmergencyType.CYCLONE_STORM.value,
        "description": "High wind velocity and debris from cyclone landfall.",
        "citizen_name": "Test Citizen",
        "citizen_phone": "9876543210",
        "location": {"latitude": sit_lat, "longitude": sit_lon, "address": "Vijayawada Riverbank"},
        "status": "VERIFIED",
        "priority": "CRITICAL",
        "created_at": datetime.now(timezone.utc),
    })

    await db["situations"].insert_one({
        "situation_id": situation_id,
        "cluster_id": f"CLS-{uuid.uuid4().hex[:8].upper()}",
        "title": "Severe Cyclone Storm Phailin",
        "emergency_type": EmergencyType.CYCLONE_STORM.value,
        "primary_emergency_type": EmergencyType.CYCLONE_STORM.value,
        "primary_report_id": report_id,
        "report_ids": [report_id],
        "report_count": 1,
        "center_location": {"latitude": sit_lat, "longitude": sit_lon, "city": "Vijayawada"},
        "impact_zone": {"center_latitude": sit_lat, "center_longitude": sit_lon, "radius_km": 10.0, "is_estimated": True},
        "status": "ACTIVE",
        "severity_level": SeverityLevel.CRITICAL.value,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    # 2. Create AQI Sensor 1.5 km away with 3.0 km coverage
    sensor_payload = {
        "name": "Vijayawada Urban AQI Station",
        "sensor_type": SensorType.AQI.value,
        "location_name": "Urban Station #1",
        "latitude": sit_lat + 0.010,
        "longitude": sit_lon + 0.008,
        "coverage_radius_value": 3.0,
        "coverage_radius_unit": "km",
        "threshold": 200.0,
        "unit": "AQI",
    }
    create_res = await client.post("/api/v1/sensors", json=sensor_payload, headers=officer_headers)
    assert create_res.status_code == 201
    sensor = create_res.json()
    sensor_id = sensor["sensor_id"]
    assert sensor["sensor_type"] == "AQI"

    # 3. Activate sensor
    act_res = await client.post(f"/api/v1/sensors/{sensor_id}/activate", headers=officer_headers)
    assert act_res.status_code == 200

    # 4. Ingest high AQI reading (320.0 AQI > 200.0 threshold)
    reading_res = await client.post(
        f"/api/v1/sensors/{sensor_id}/readings",
        json={"value": 320.0},
        headers=officer_headers,
    )
    assert reading_res.status_code == 201
    reading_data = reading_res.json()
    assert reading_data["is_breach"] is True
    assert reading_data["value"] == 320.0

    # 5. Check Live Monitoring Events generated
    events = await db["monitoring_events"].find({"source_id": sensor_id}).to_list(length=10)
    assert len(events) >= 1
    latest_event = events[0]
    assert latest_event["source_type"] == "SIMULATED_SENSOR"
    assert latest_event.get("metadata", {}).get("sensor_type") == "AQI" or latest_event.get("sensor_type") == "AQI"

    # 6. Inspect Cyclone Situation Evidence
    inspect_res = await client.get(f"/api/v1/officer/situations/{situation_id}", headers=officer_headers)
    assert inspect_res.status_code == 200
    sit_detail = inspect_res.json()

    evidence_list = sit_detail.get("sensor_evidence", [])
    aqi_ev = next((e for e in evidence_list if e["sensor_id"] == sensor_id), None)
    assert aqi_ev is not None, "AQI Sensor evidence must be present in Cyclone situation inspect"
    assert aqi_ev["sensor_type"] == "AQI"
    assert aqi_ev["source_type"] == "SIMULATED_SENSOR"
    assert aqi_ev["current_value"] == 320.0
    assert aqi_ev["threshold"] == 200.0
    assert aqi_ev["threshold_state"] == "BREACHED"
    assert aqi_ev["distance_to_center_km"] < 3.0
    assert "WITHIN_SENSOR_COVERAGE" in aqi_ev["correlation_reason"]
