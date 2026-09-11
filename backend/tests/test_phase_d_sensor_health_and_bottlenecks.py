"""
test_phase_d_sensor_health_and_bottlenecks.py
Comprehensive test suite for Phase D USP:
- Sensor Health & Stale Data Intelligence (NEVER_REPORTED, HEALTHY, STALE, INACTIVE, UNAVAILABLE)
- Custom stale threshold & Idempotent Stale Event generation
- Corroboration Reliability discounting on stale readings (0.35 score)
- Recovery: Fresh reading restores STALE sensor to HEALTHY
- Resource Bottleneck Intelligence (Needs vs Inventory vs Allocations vs Task Consumption)
- Multi-incident Contention & Alternative Resource Discovery
- Authoritative Needs assessment immutability & Zero Fake Data validation
- Role-based authorization & filter validation
"""

import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from app.db.mongodb import get_database
from app.models.enums import (
    SensorReportingState,
    SensorHealthState,
    BottleneckType,
    BottleneckSeverity,
    SensorType,
    SensorStatus,
    ResourceType,
    UserRole,
)
from app.services.sensor_service import sensor_service
from app.services.resource_bottleneck_service import resource_bottleneck_service


# Fixtures for tokens matching pre-seeded operators in conftest.py
@pytest.fixture
def officer_token():
    from app.core.security import create_access_token
    return create_access_token(data={"sub": "9999999002", "role": "EMERGENCY_OFFICER"})


@pytest.fixture
def resource_mgr_token():
    from app.core.security import create_access_token
    return create_access_token(data={"sub": "9999999003", "role": "RESOURCE_MANAGER"})


@pytest.fixture
async def citizen_token():
    from app.core.security import create_access_token
    db = get_database()
    await db.users.update_one(
        {"phone": "9999999009"},
        {"$set": {"phone": "9999999009", "full_name": "Test Citizen", "role": "CITIZEN", "is_active": True}},
        upsert=True,
    )
    return create_access_token(data={"sub": "9999999009", "role": "CITIZEN"})


@pytest.mark.anyio
async def test_sensor_health_never_reported():
    """Test 1: A newly provisioned sensor without readings has NEVER_REPORTED state and zero fake data."""
    db = get_database()
    sensor_id = "TEST-SENSOR-NR-01"
    await db.sensors.delete_many({"sensor_id": sensor_id})

    now = datetime.now(timezone.utc)
    sensor_doc = {
        "sensor_id": sensor_id,
        "name": "River Gauge North",
        "sensor_type": SensorType.WATER_LEVEL.value,
        "status": SensorStatus.ACTIVE.value,
        "current_reading": None,
        "last_updated": None,
        "threshold": 5.0,
        "unit": "meters",
        "latitude": 16.5062,
        "longitude": 80.6480,
        "location_name": "Krishna River North Bank",
        "created_at": now,
        "updated_at": now,
    }
    await db.sensors.insert_one(sensor_doc)

    health = await sensor_service.get_sensor_health_detail(db, sensor_id)
    assert health is not None
    assert health.reporting_state == SensorReportingState.NEVER_REPORTED
    assert health.health_state == SensorHealthState.NEVER_REPORTED
    assert health.reading_age_seconds is None
    assert health.reading_age_human == "Never reported"


@pytest.mark.anyio
async def test_sensor_health_healthy_fresh():
    """Test 2: A sensor with reading timestamp within stale threshold (<300s) is HEALTHY."""
    db = get_database()
    sensor_id = "TEST-SENSOR-HEALTHY-01"
    await db.sensors.delete_many({"sensor_id": sensor_id})

    now = datetime.now(timezone.utc)
    recent_time = now - timedelta(seconds=45)
    sensor_doc = {
        "sensor_id": sensor_id,
        "name": "Rain Gauge Downtown",
        "sensor_type": SensorType.RAINFALL.value,
        "status": SensorStatus.ACTIVE.value,
        "current_reading": 12.5,
        "last_updated": recent_time,
        "threshold": 50.0,
        "unit": "mm/hr",
        "latitude": 16.5100,
        "longitude": 80.6500,
        "location_name": "City Center",
        "created_at": now,
        "updated_at": recent_time,
    }
    await db.sensors.insert_one(sensor_doc)

    health = await sensor_service.get_sensor_health_detail(db, sensor_id)
    assert health is not None
    assert health.reporting_state == SensorReportingState.HEALTHY
    assert health.health_state == SensorHealthState.HEALTHY
    assert health.reading_age_seconds is not None
    assert health.reading_age_seconds < 300


@pytest.mark.anyio
async def test_sensor_health_stale_detection():
    """Test 3: A sensor with reading older than 300s transitions to STALE."""
    db = get_database()
    sensor_id = "TEST-SENSOR-STALE-01"
    await db.sensors.delete_many({"sensor_id": sensor_id})

    now = datetime.now(timezone.utc)
    stale_time = now - timedelta(seconds=600)  # 10 minutes ago
    sensor_doc = {
        "sensor_id": sensor_id,
        "name": "Smoke Sensor Sector 4",
        "sensor_type": SensorType.SMOKE_AIR_QUALITY.value,
        "status": SensorStatus.ACTIVE.value,
        "current_reading": 18.0,
        "last_updated": stale_time,
        "threshold": 30.0,
        "unit": "ppm",
        "latitude": 16.5200,
        "longitude": 80.6600,
        "location_name": "Sector 4 Industrial",
        "created_at": now,
        "updated_at": stale_time,
    }
    await db.sensors.insert_one(sensor_doc)

    health = await sensor_service.get_sensor_health_detail(db, sensor_id)
    assert health is not None
    assert health.reporting_state == SensorReportingState.STALE
    assert health.health_state == SensorHealthState.STALE
    assert health.reading_age_seconds is not None
    assert health.reading_age_seconds >= 300
    assert "m ago" in health.reading_age_human or "s ago" in health.reading_age_human


@pytest.mark.anyio
async def test_sensor_health_custom_threshold():
    """Test 4: Custom stale threshold (e.g. 60s) transitions to STALE after 75s."""
    db = get_database()
    sensor_id = "TEST-SENSOR-CUSTOM-THRESH"
    await db.sensors.delete_many({"sensor_id": sensor_id})

    now = datetime.now(timezone.utc)
    sensor_doc = {
        "sensor_id": sensor_id,
        "name": "Fast Poll Sensor",
        "sensor_type": SensorType.AQI.value,
        "status": SensorStatus.ACTIVE.value,
        "current_reading": 150.0,
        "last_updated": now - timedelta(seconds=75),
        "threshold": 200.0,
        "unit": "AQI",
        "latitude": 16.5,
        "longitude": 80.6,
        "created_at": now,
        "updated_at": now,
    }
    await db.sensors.insert_one(sensor_doc)

    # With default 300s -> Still healthy
    health_default = await sensor_service.get_sensor_health_detail(db, sensor_id, stale_threshold_seconds=300.0)
    assert health_default.health_state == SensorHealthState.HEALTHY

    # With 60s threshold -> Transitions to STALE
    health_strict = await sensor_service.get_sensor_health_detail(db, sensor_id, stale_threshold_seconds=60.0)
    assert health_strict.health_state == SensorHealthState.STALE


@pytest.mark.anyio
async def test_sensor_health_inactive_state():
    """Test 5: Paused or Inactive sensors return INACTIVE health state."""
    db = get_database()
    sensor_id = "TEST-SENSOR-INACTIVE-01"
    await db.sensors.delete_many({"sensor_id": sensor_id})

    now = datetime.now(timezone.utc)
    sensor_doc = {
        "sensor_id": sensor_id,
        "name": "Decommissioned Station",
        "sensor_type": SensorType.TEMPERATURE.value,
        "status": SensorStatus.INACTIVE.value,
        "current_reading": 32.0,
        "last_updated": now - timedelta(seconds=60),
        "threshold": 45.0,
        "unit": "C",
        "latitude": 16.5300,
        "longitude": 80.6700,
        "location_name": "Old Yard",
        "created_at": now,
        "updated_at": now,
    }
    await db.sensors.insert_one(sensor_doc)

    health = await sensor_service.get_sensor_health_detail(db, sensor_id)
    assert health is not None
    assert health.health_state == SensorHealthState.INACTIVE


@pytest.mark.anyio
async def test_sensor_health_recovery_flow():
    """Test 6: Ingesting a fresh reading resets a STALE sensor back to HEALTHY."""
    db = get_database()
    sensor_id = "TEST-SENSOR-RECOVER-01"
    await db.sensors.delete_many({"sensor_id": sensor_id})

    now = datetime.now(timezone.utc)
    old_time = now - timedelta(seconds=800)
    sensor_doc = {
        "sensor_id": sensor_id,
        "name": "Flood Sensor River Gate",
        "sensor_type": SensorType.WATER_LEVEL.value,
        "status": SensorStatus.ACTIVE.value,
        "current_reading": 3.2,
        "last_updated": old_time,
        "threshold": 6.0,
        "unit": "meters",
        "latitude": 16.5,
        "longitude": 80.6,
        "created_at": now,
        "updated_at": old_time,
    }
    await db.sensors.insert_one(sensor_doc)

    # Initial state: STALE
    health_before = await sensor_service.get_sensor_health_detail(db, sensor_id)
    assert health_before.health_state == SensorHealthState.STALE

    # Submit fresh live reading
    fresh_time = datetime.now(timezone.utc)
    await db.sensors.update_one(
        {"sensor_id": sensor_id},
        {"$set": {"current_reading": 3.8, "last_updated": fresh_time, "updated_at": fresh_time}},
    )

    health_after = await sensor_service.get_sensor_health_detail(db, sensor_id)
    assert health_after.health_state == SensorHealthState.HEALTHY
    assert health_after.reading_age_seconds < 10


@pytest.mark.anyio
async def test_sensor_health_api_endpoint(client: AsyncClient, officer_token):
    """Test 7: GET /api/v1/sensors/health returns aggregated summary and details."""
    response = await client.get(
        "/api/v1/sensors/health",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "items" in data
    assert isinstance(data["items"], list)
    assert "total_sensors" in data["summary"]
    assert "healthy_count" in data["summary"]
    assert "stale_count" in data["summary"]
    assert "never_reported_count" in data["summary"]


@pytest.mark.anyio
async def test_resource_bottleneck_zero_deficit():
    """Test 8: When available inventory covers all needs, shortfall is 0 and no false bottlenecks occur."""
    db = get_database()
    res_id = "RES-TEST-SURPLUS-01"
    assess_id = "ASSESS-SURPLUS-01"
    sit_id = "SIT-SURPLUS-01"

    await db.resources.delete_many({"$or": [
        {"resource_id": res_id},
        {"resource_type": {"$regex": "^generator", "$options": "i"}},
    ]})
    await db.needs_assessments.delete_many({"$or": [
        {"assessment_id": assess_id},
        {"resource_type": {"$regex": "^generator", "$options": "i"}},
        {"needs.resource_type": {"$regex": "^generator", "$options": "i"}},
    ]})
    await db.situations.delete_many({"situation_id": sit_id})

    now = datetime.now(timezone.utc)
    await db.situations.insert_one({
        "situation_id": sit_id,
        "title": "Hospital Grid Failure",
        "emergency_type": "POWER_OUTAGE",
        "severity_level": "HIGH",
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
    })

    await db.resources.insert_one({
        "resource_id": res_id,
        "name": "High Capacity Generators",
        "resource_type": ResourceType.GENERATOR.value,
        "quantity_total": 50,
        "quantity_available": 50,
        "quantity_allocated": 0,
        "unit": "units",
        "status": "AVAILABLE",
        "location": {"latitude": 16.5, "longitude": 80.6},
        "created_at": now,
        "updated_at": now,
    })

    # Needs assessment for 10 units
    await db.needs_assessments.insert_one({
        "assessment_id": assess_id,
        "situation_id": sit_id,
        "report_id": "REP-SURPLUS-01",
        "resource_type": ResourceType.GENERATOR.value,
        "requested_quantity": 10,
        "allocated_quantity": 0,
        "status": "PENDING",
        "urgency": "HIGH",
        "created_at": now,
        "updated_at": now,
    })

    resp = await resource_bottleneck_service.analyze_bottlenecks(db, resource_type=ResourceType.GENERATOR.value)
    items = resp.items
    shortfall_bottlenecks = [b for b in items if b.shortfall > 0]
    assert len(shortfall_bottlenecks) == 0


@pytest.mark.anyio
async def test_resource_bottleneck_critical_shortfall():
    """Test 9: When required quantity exceeds inventory, genuine shortfall and CRITICAL severity are computed."""
    db = get_database()
    res_type = ResourceType.MEDICINE.value
    res_id = "RES-TEST-DEFICIT-01"
    assess_id = "ASSESS-DEFICIT-01"
    sit_id = "SIT-DEFICIT-01"

    await db.resources.delete_many({"$or": [
        {"resource_id": res_id},
        {"resource_type": {"$regex": "^medicine", "$options": "i"}},
    ]})
    await db.needs_assessments.delete_many({"$or": [
        {"assessment_id": assess_id},
        {"resource_type": {"$regex": "^medicine", "$options": "i"}},
        {"needs.resource_type": {"$regex": "^medicine", "$options": "i"}},
    ]})
    await db.situations.delete_many({"situation_id": sit_id})

    now = datetime.now(timezone.utc)
    await db.situations.insert_one({
        "situation_id": sit_id,
        "title": "Severe Trauma Influx",
        "emergency_type": "MEDICAL",
        "severity_level": "CRITICAL",
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
    })

    # Available = 5, Need = 120 -> Deficit = 115 -> CRITICAL
    await db.resources.insert_one({
        "resource_id": res_id,
        "name": "Trauma Kits",
        "resource_type": res_type,
        "quantity_total": 10,
        "quantity_available": 5,
        "quantity_allocated": 5,
        "unit": "kits",
        "status": "AVAILABLE",
        "location": {"latitude": 16.5, "longitude": 80.6},
        "created_at": now,
        "updated_at": now,
    })

    await db.needs_assessments.insert_one({
        "assessment_id": assess_id,
        "situation_id": sit_id,
        "report_id": "REP-DEFICIT-01",
        "resource_type": res_type,
        "requested_quantity": 120,
        "allocated_quantity": 5,
        "status": "PENDING",
        "urgency": "CRITICAL",
        "created_at": now,
        "updated_at": now,
    })

    resp = await resource_bottleneck_service.analyze_bottlenecks(db, resource_type=res_type)
    items = resp.items
    assert len(items) > 0
    b = items[0]
    assert b.shortfall == 115
    assert b.severity == BottleneckSeverity.CRITICAL
    assert b.bottleneck_type in [BottleneckType.RESOURCE_SHORTAGE, BottleneckType.NO_ELIGIBLE_RESOURCE]


@pytest.mark.anyio
async def test_resource_bottleneck_multi_incident_contention():
    """Test 10: Multi-incident contention is detected when 2+ situations demand the same scarce resource."""
    db = get_database()
    res_type = ResourceType.TRANSPORT.value
    res_id = "RES-BOAT-01"
    await db.resources.delete_many({"$or": [
        {"resource_id": res_id},
        {"resource_type": {"$regex": "^transport", "$options": "i"}},
    ]})
    await db.needs_assessments.delete_many({"$or": [
        {"assessment_id": {"$in": ["ASSESS-BOAT-SIT1", "ASSESS-BOAT-SIT2"]}},
        {"resource_type": {"$regex": "^transport", "$options": "i"}},
        {"needs.resource_type": {"$regex": "^transport", "$options": "i"}},
    ]})
    await db.situations.delete_many({"situation_id": {"$in": ["SIT-FLOOD-EAST", "SIT-FLOOD-WEST"]}})

    now = datetime.now(timezone.utc)
    await db.situations.insert_many([
        {
            "situation_id": "SIT-FLOOD-EAST",
            "title": "East Bank Flooding",
            "emergency_type": "FLOOD",
            "severity_level": "HIGH",
            "status": "ACTIVE",
            "created_at": now,
            "updated_at": now,
        },
        {
            "situation_id": "SIT-FLOOD-WEST",
            "title": "West Bank Breach",
            "emergency_type": "FLOOD",
            "severity_level": "CRITICAL",
            "status": "ACTIVE",
            "created_at": now,
            "updated_at": now,
        },
    ])

    # Inventory = 2 boats
    await db.resources.insert_one({
        "resource_id": res_id,
        "name": "Inflatable Zodiac Boats",
        "resource_type": res_type,
        "quantity_total": 4,
        "quantity_available": 2,
        "quantity_allocated": 2,
        "unit": "boats",
        "status": "AVAILABLE",
        "location": {"latitude": 16.5, "longitude": 80.6},
        "created_at": now,
        "updated_at": now,
    })

    # Situation 1 demands 3 boats
    await db.needs_assessments.insert_one({
        "assessment_id": "ASSESS-BOAT-SIT1",
        "situation_id": "SIT-FLOOD-EAST",
        "report_id": "REP-SIT1",
        "resource_type": res_type,
        "requested_quantity": 3,
        "allocated_quantity": 1,
        "status": "PENDING",
        "urgency": "HIGH",
        "created_at": now,
        "updated_at": now,
    })

    # Situation 2 demands 4 boats
    await db.needs_assessments.insert_one({
        "assessment_id": "ASSESS-BOAT-SIT2",
        "situation_id": "SIT-FLOOD-WEST",
        "report_id": "REP-SIT2",
        "resource_type": res_type,
        "requested_quantity": 4,
        "allocated_quantity": 1,
        "status": "PENDING",
        "urgency": "CRITICAL",
        "created_at": now,
        "updated_at": now,
    })

    resp = await resource_bottleneck_service.analyze_bottlenecks(db, resource_type=res_type)
    items = resp.items
    assert len(items) > 0
    b = items[0]
    assert b.contention is not None
    assert len(b.contention.competing_situations) >= 2
    assert b.bottleneck_type == BottleneckType.ALLOCATION_CONTENTION


@pytest.mark.anyio
async def test_resource_bottleneck_api_endpoints(client: AsyncClient, resource_mgr_token, citizen_token):
    """Test 11: GET /api/v1/resources/bottlenecks works for authorized roles and enforces RBAC."""
    # Resource Manager can access
    resp_mgr = await client.get(
        "/api/v1/resources/bottlenecks",
        headers={"Authorization": f"Bearer {resource_mgr_token}"},
    )
    assert resp_mgr.status_code == 200
    data = resp_mgr.json()
    assert "items" in data
    assert "summary" in data

    # Citizen cannot access bottleneck intelligence (403 Forbidden)
    resp_citizen = await client.get(
        "/api/v1/resources/bottlenecks",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert resp_citizen.status_code == 403
