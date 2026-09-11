import pytest
import uuid
import math
from datetime import datetime, timezone
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.enums import SensorType, EmergencyType, SeverityLevel, SensorStatus, UserRole
from app.models.sensor import SensorCreate, SensorUpdate, SensorLocation, SensorCoverage
from app.core.security import create_access_token
from app.services.resource_matching import haversine_distance_km


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
async def test_01_create_sensor_with_valid_coordinates_and_coverage(client: AsyncClient, officer_headers: dict):
    """1. Create sensor with valid coordinates and coverage radius."""
    payload = {
        "name": "Krishna Barrage Flood Monitor",
        "sensor_type": SensorType.WATER_LEVEL.value,
        "location_name": "Krishna Barrage Gate 10",
        "latitude": 16.5062,
        "longitude": 80.6480,
        "location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "address": "Krishna Barrage Gate 10",
            "zone": "River Zone",
            "city": "Vijayawada",
            "state": "AP",
        },
        "coverage": {
            "radius_meters": 3500.0,
            "display_value": 3.5,
            "display_unit": "km",
        },
        "threshold": 3.0,
        "unit": "meters",
    }
    res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Krishna Barrage Flood Monitor"
    assert data["latitude"] == 16.5062
    assert data["longitude"] == 80.6480
    assert data["coverage"]["radius_meters"] == 3500.0
    assert data["coverage"]["display_value"] == 3.5
    assert data["coverage"]["display_unit"] == "km"
    assert data["location"]["city"] == "Vijayawada"


@pytest.mark.anyio
async def test_02_create_sensor_with_meters_coverage_unit(client: AsyncClient, officer_headers: dict):
    """2. Create sensor with valid coverage radius in meters."""
    payload = {
        "name": "Industrial Smoke Sensor",
        "sensor_type": SensorType.SMOKE_AIR_QUALITY.value,
        "location_name": "Auto Nagar Sector 5",
        "latitude": 16.4950,
        "longitude": 80.6700,
        "coverage_radius_value": 750,
        "coverage_radius_unit": "meters",
        "threshold": 200.0,
        "unit": "AQI",
    }
    res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["coverage"]["radius_meters"] == 750.0
    assert data["coverage"]["display_value"] == 750.0
    assert data["coverage"]["display_unit"] == "m"


@pytest.mark.anyio
async def test_03_invalid_latitude_rejected(client: AsyncClient, officer_headers: dict):
    """3. Invalid latitude (> 90 or < -90) rejected."""
    payload = {
        "name": "Bad Lat Sensor",
        "sensor_type": SensorType.TEMPERATURE.value,
        "location_name": "Bad Location",
        "latitude": 95.5,
        "longitude": 80.0,
        "coverage_radius_value": 2.0,
        "coverage_radius_unit": "km",
        "threshold": 45.0,
    }
    res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    assert res.status_code in [400, 422]


@pytest.mark.anyio
async def test_04_invalid_longitude_rejected(client: AsyncClient, officer_headers: dict):
    """4. Invalid longitude (> 180 or < -180) rejected."""
    payload = {
        "name": "Bad Long Sensor",
        "sensor_type": SensorType.TEMPERATURE.value,
        "location_name": "Bad Location",
        "latitude": 16.5,
        "longitude": 185.0,
        "coverage_radius_value": 2.0,
        "coverage_radius_unit": "km",
        "threshold": 45.0,
    }
    res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    assert res.status_code in [400, 422]


@pytest.mark.anyio
async def test_05_zero_range_rejected(client: AsyncClient, officer_headers: dict):
    """5. Zero coverage range is rejected."""
    payload = {
        "name": "Zero Range Sensor",
        "sensor_type": SensorType.RAINFALL.value,
        "location_name": "Rain Gauge Station",
        "latitude": 16.5,
        "longitude": 80.6,
        "coverage_radius_value": 0,
        "coverage_radius_unit": "km",
        "threshold": 50.0,
    }
    res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    assert res.status_code in [400, 422]


@pytest.mark.anyio
async def test_06_negative_range_rejected(client: AsyncClient, officer_headers: dict):
    """6. Negative coverage range is rejected."""
    payload = {
        "name": "Negative Range Sensor",
        "sensor_type": SensorType.RAINFALL.value,
        "location_name": "Rain Gauge Station",
        "latitude": 16.5,
        "longitude": 80.6,
        "coverage_radius_value": -5.0,
        "coverage_radius_unit": "km",
        "threshold": 50.0,
    }
    res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    assert res.status_code in [400, 422]


@pytest.mark.anyio
async def test_07_invalid_range_unit_rejected(client: AsyncClient, officer_headers: dict):
    """7. Invalid coverage range unit rejected."""
    payload = {
        "name": "Bad Unit Sensor",
        "sensor_type": SensorType.RAINFALL.value,
        "location_name": "Rain Gauge Station",
        "latitude": 16.5,
        "longitude": 80.6,
        "coverage_radius_value": 5.0,
        "coverage_radius_unit": "miles",  # Unsupported unit
        "threshold": 50.0,
    }
    res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    assert res.status_code in [400, 422]


@pytest.mark.anyio
async def test_08_edit_sensor_location_and_range(client: AsyncClient, officer_headers: dict):
    """8 & 14 & 15. Edit sensor location coordinates and coverage radius persists correctly."""
    # 1. Create sensor
    create_payload = {
        "name": "Original Station Name",
        "sensor_type": SensorType.SMOKE_AIR_QUALITY.value,
        "location_name": "Old Location Area",
        "latitude": 16.5000,
        "longitude": 80.6000,
        "coverage_radius_value": 2.0,
        "coverage_radius_unit": "km",
        "threshold": 250.0,
    }
    res = await client.post("/api/v1/sensors", json=create_payload, headers=officer_headers)
    assert res.status_code == 201
    sensor_id = res.json()["sensor_id"]

    # 2. Update sensor location and range
    update_payload = {
        "name": "Updated Station Name",
        "location_name": "New High Point Tower",
        "latitude": 16.5200,
        "longitude": 80.6300,
        "location": {
            "latitude": 16.5200,
            "longitude": 80.6300,
            "address": "New High Point Tower",
            "zone": "North Sector",
            "city": "Vijayawada",
        },
        "coverage_radius_value": 4.5,
        "coverage_radius_unit": "km",
    }
    update_res = await client.put(f"/api/v1/sensors/{sensor_id}", json=update_payload, headers=officer_headers)
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["name"] == "Updated Station Name"
    assert updated_data["latitude"] == 16.5200
    assert updated_data["longitude"] == 80.6300
    assert updated_data["coverage"]["radius_meters"] == 4500.0
    assert updated_data["coverage"]["display_value"] == 4.5
    assert updated_data["coverage"]["display_unit"] == "km"

    # 3. Verify get by ID returns updated fields
    get_res = await client.get(f"/api/v1/sensors/{sensor_id}", headers=officer_headers)
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["latitude"] == 16.5200
    assert get_data["coverage"]["radius_meters"] == 4500.0


@pytest.mark.anyio
async def test_09_spatial_correlation_within_coverage_vs_outside_coverage(client: AsyncClient, db: AsyncIOMotorDatabase, officer_headers: dict):
    """16 & 17. Situation inside coverage correlates; situation outside sensor coverage does NOT correlate."""
    situation_id = f"SIT-{uuid.uuid4().hex[:8].upper()}"
    sit_lat, sit_lon = 16.5000, 80.6000

    # 1. Create active situation & primary report
    report_id = f"REP-CYC-{uuid.uuid4().hex[:6].upper()}"
    await db["situations"].insert_one({
        "situation_id": situation_id,
        "cluster_id": f"CLS-{uuid.uuid4().hex[:8].upper()}",
        "title": "Cyclone Inundation Cluster",
        "emergency_type": EmergencyType.CYCLONE_STORM.value,
        "primary_report_id": report_id,
        "report_ids": [report_id],
        "report_count": 1,
        "center_location": {"latitude": sit_lat, "longitude": sit_lon, "city": "Vijayawada"},
        "impact_zone": {"center_latitude": sit_lat, "center_longitude": sit_lon, "radius_km": 10.0, "is_estimated": True},
        "status": "ACTIVE",
        "severity_level": SeverityLevel.HIGH.value,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    await db["citizen_reports"].insert_one({
        "report_id": report_id,
        "emergency_type": EmergencyType.CYCLONE_STORM.value,
        "description": "Cyclone wind and rain report near barrage.",
        "citizen_name": "Test Citizen",
        "citizen_phone": "9876543210",
        "location": {"latitude": sit_lat, "longitude": sit_lon, "address": "Vijayawada Barrage"},
        "status": "VERIFIED",
        "priority": "HIGH",
        "created_at": datetime.now(timezone.utc),
    })

    # 2. Sensor A: 1.2 km away, Coverage = 2.0 km (INSIDE COVERAGE -> Should correlate)
    sensor_a_payload = {
        "name": "Inside Range AQI Sensor",
        "sensor_type": SensorType.SMOKE_AIR_QUALITY.value,
        "location_name": "Near Barrage",
        "latitude": sit_lat + 0.008,  # ~0.9 km
        "longitude": sit_lon + 0.008,
        "coverage_radius_value": 2.0,
        "coverage_radius_unit": "km",
        "threshold": 150.0,
    }
    res_a = await client.post("/api/v1/sensors", json=sensor_a_payload, headers=officer_headers)
    assert res_a.status_code == 201
    sensor_a_id = res_a.json()["sensor_id"]

    # Activate Sensor A and record a reading
    await client.post(f"/api/v1/sensors/{sensor_a_id}/activate", headers=officer_headers)
    await client.post(f"/api/v1/sensors/{sensor_a_id}/readings", json={"value": 180.0}, headers=officer_headers)

    # 3. Sensor B: 4.5 km away, Coverage = 1.0 km (OUTSIDE COVERAGE -> Must NOT correlate)
    sensor_b_payload = {
        "name": "Outside Range Rain Sensor",
        "sensor_type": SensorType.RAINFALL.value,
        "location_name": "Far Hilltop",
        "latitude": sit_lat + 0.035,  # ~4.0 km away
        "longitude": sit_lon + 0.020,
        "coverage_radius_value": 1.0,  # Range is only 1km
        "coverage_radius_unit": "km",
        "threshold": 30.0,
    }
    res_b = await client.post("/api/v1/sensors", json=sensor_b_payload, headers=officer_headers)
    assert res_b.status_code == 201
    sensor_b_id = res_b.json()["sensor_id"]

    # Activate Sensor B and record a reading
    await client.post(f"/api/v1/sensors/{sensor_b_id}/activate", headers=officer_headers)
    await client.post(f"/api/v1/sensors/{sensor_b_id}/readings", json={"value": 45.0}, headers=officer_headers)

    # 4. Inspect the situation details
    sit_res = await client.get(f"/api/v1/officer/situations/{situation_id}", headers=officer_headers)
    assert sit_res.status_code == 200
    sit_data = sit_res.json()

    evidence_sensor_ids = [e["sensor_id"] for e in sit_data.get("sensor_evidence", [])]
    # Sensor A MUST be in evidence
    assert sensor_a_id in evidence_sensor_ids
    # Sensor B MUST NOT be in evidence
    assert sensor_b_id not in evidence_sensor_ids

    # Verify sensor A evidence contains coverage & distance
    ev_a = next(e for e in sit_data["sensor_evidence"] if e["sensor_id"] == sensor_a_id)
    assert ev_a["source_type"] == "SIMULATED_SENSOR"
    assert ev_a["coverage_radius_km"] == 2.0
    assert ev_a["distance_to_center_km"] < 2.0
    assert "WITHIN_SENSOR_COVERAGE" in ev_a["correlation_reason"]


@pytest.mark.anyio
async def test_10_unauthorized_user_cannot_update_sensor(client: AsyncClient):
    """24. Unauthorized user without officer/admin role cannot update sensor location/range."""
    # Attempt update without headers
    res = await client.put("/api/v1/sensors/SNS-TEST1234", json={"name": "Hacked Name"})
    assert res.status_code in [401, 403]
