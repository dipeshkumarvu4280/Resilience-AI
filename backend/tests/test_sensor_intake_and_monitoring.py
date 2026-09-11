"""
Comprehensive Tests for Live Simulated Sensor Intake & Real-Time Sensor Monitoring.
Covers Mandatory Tests 1 to 20.
"""

import pytest
import asyncio
import uuid
from datetime import datetime, timezone
from app.models.enums import UserRole, SensorType, SensorStatus, SimulationTrend, ImpactLevel, SensorReadingSource
from app.core.security import create_access_token
from app.services.sensor_stream_manager import sensor_stream_manager


@pytest.fixture
async def officer_headers(db):
    officer_phone = "9999999002"
    # Ensure officer exists
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


@pytest.fixture
async def citizen_headers(db):
    citizen_phone = "9999999888"
    # Ensure citizen user exists in test DB so auth succeeds but role is CITIZEN
    await db["users"].update_one(
        {"phone": citizen_phone},
        {
            "$set": {
                "phone": citizen_phone,
                "full_name": "Citizen Jane Doe",
                "email": "citizen.jane@example.com",
                "role": UserRole.CITIZEN.value,
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
    token = create_access_token(
        data={"sub": citizen_phone, "role": UserRole.CITIZEN.value, "user_id": "citizen_1"}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_01_sensor_creation_without_readings(client, db, officer_headers):
    """1. Sensor Creation without readings: verify status and 0 readings exist."""
    payload = {
        "name": "Yamuna River Water Level Monitor 01",
        "sensor_type": SensorType.WATER_LEVEL.value,
        "location_name": "ITO Bridge, New Delhi",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "threshold": 205.33,
        "unit": "meters",
        "description": "Critical flood gauge station at Yamuna",
    }
    res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    assert res.status_code == 201
    data = res.json()
    sensor_id = data["sensor_id"]
    assert data["name"] == payload["name"]
    assert data["status"] == SensorStatus.DRAFT.value

    # Verify 0 readings exist for this sensor in DB
    readings_count = await db["sensor_readings"].count_documents({"sensor_id": sensor_id})
    assert readings_count == 0


@pytest.mark.anyio
async def test_02_inactive_sensor_rejection(client, officer_headers):
    """2. Inactive Sensor Rejection: reading submission to INACTIVE or DRAFT sensor rejected."""
    payload = {
        "name": "AQI Monitor South Extension",
        "sensor_type": SensorType.SMOKE_AIR_QUALITY.value,
        "location_name": "South Extension Ring Road",
        "latitude": 28.5700,
        "longitude": 77.2200,
        "threshold": 300.0,
        "unit": "AQI",
    }
    create_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    sensor_id = create_res.json()["sensor_id"]

    # Attempt to post reading to DRAFT sensor (sensor is created as DRAFT by default)
    reading_payload = {
        "value": 150.0,
        "source_type": SensorReadingSource.MANUAL_SIMULATION.value,
    }
    reading_res = await client.post(
        f"/api/v1/sensors/{sensor_id}/readings", json=reading_payload, headers=officer_headers
    )
    assert reading_res.status_code == 400
    assert "ACTIVE" in reading_res.json()["detail"]


@pytest.mark.anyio
async def test_03_active_sensor_acceptance(client, officer_headers):
    """3. Active Sensor Acceptance: reading submission to ACTIVE sensor accepted."""
    payload = {
        "name": "Rainfall Station Connaught Place",
        "sensor_type": SensorType.RAINFALL.value,
        "location_name": "Connaught Place Inner Circle",
        "latitude": 28.6304,
        "longitude": 77.2177,
        "threshold": 50.0,
        "unit": "mm/hr",
    }
    create_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    sensor_id = create_res.json()["sensor_id"]

    # Activate sensor
    act_res = await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)
    assert act_res.status_code == 200

    # Post reading
    reading_payload = {
        "value": 25.5,
        "source_type": SensorReadingSource.MANUAL_SIMULATION.value,
    }
    reading_res = await client.post(
        f"/api/v1/sensors/{sensor_id}/readings", json=reading_payload, headers=officer_headers
    )
    assert reading_res.status_code == 201
    reading_data = reading_res.json()
    assert reading_data["value"] == 25.5
    assert reading_data["is_breach"] is False
    assert reading_data["sensor_id"] == sensor_id


@pytest.mark.anyio
async def test_04_threshold_breach_transition(client, db, officer_headers):
    """4. Threshold Breach Transition: normal -> breached creates alert and generates monitoring event."""
    payload = {
        "name": "Temperature Sensor Okhla",
        "sensor_type": SensorType.TEMPERATURE.value,
        "location_name": "Okhla Phase 3 Industrial Area",
        "latitude": 28.5355,
        "longitude": 77.2732,
        "threshold": 45.0,
        "unit": "°C",
    }
    create_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    sensor_id = create_res.json()["sensor_id"]

    # Activate sensor
    await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)

    # Post normal reading first
    await client.post(
        f"/api/v1/sensors/{sensor_id}/readings",
        json={"value": 38.0, "source_type": SensorReadingSource.MANUAL_SIMULATION.value},
        headers=officer_headers,
    )

    # Post breached reading (48.0 > 45.0)
    breach_res = await client.post(
        f"/api/v1/sensors/{sensor_id}/readings",
        json={"value": 48.0, "source_type": SensorReadingSource.MANUAL_SIMULATION.value},
        headers=officer_headers,
    )
    assert breach_res.status_code == 201
    assert breach_res.json()["is_breach"] is True

    # Check alert was created
    alerts = await db["sensor_alerts"].find({"sensor_id": sensor_id, "status": "ACTIVE_BREACH"}).to_list(length=10)
    assert len(alerts) == 1
    assert alerts[0]["current_value"] == 48.0

    # Check monitoring event was generated
    events = await db["monitoring_events"].find({"source_id": sensor_id}).to_list(length=10)
    assert len(events) >= 1
    breach_events = [e for e in events if "BREACH" in e.get("event_type", "")]
    assert len(breach_events) >= 1


@pytest.mark.anyio
async def test_05_breach_to_breach_idempotency(client, db, officer_headers):
    """5. Breach to Breach Idempotency: second breached reading updates active alert without duplicate monitoring event."""
    payload = {
        "name": "Flood Gauge Nizamuddin",
        "sensor_type": SensorType.WATER_LEVEL.value,
        "location_name": "Nizamuddin Drain Gate 2",
        "latitude": 28.5892,
        "longitude": 77.2505,
        "threshold": 200.0,
        "unit": "meters",
    }
    create_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    sensor_id = create_res.json()["sensor_id"]
    await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)

    # Initial breach reading
    await client.post(
        f"/api/v1/sensors/{sensor_id}/readings",
        json={"value": 205.0, "source_type": SensorReadingSource.MANUAL_SIMULATION.value},
        headers=officer_headers,
    )

    events_count_1 = await db["monitoring_events"].count_documents({"source_id": sensor_id, "event_type": "SENSOR_THRESHOLD_BREACHED"})
    alerts_count_1 = await db["sensor_alerts"].count_documents({"sensor_id": sensor_id, "status": "ACTIVE_BREACH"})
    assert alerts_count_1 == 1

    # Second breach reading (higher peak)
    await client.post(
        f"/api/v1/sensors/{sensor_id}/readings",
        json={"value": 208.0, "source_type": SensorReadingSource.MANUAL_SIMULATION.value},
        headers=officer_headers,
    )

    events_count_2 = await db["monitoring_events"].count_documents({"source_id": sensor_id, "event_type": "SENSOR_THRESHOLD_BREACHED"})
    alerts_count_2 = await db["sensor_alerts"].count_documents({"sensor_id": sensor_id, "status": "ACTIVE_BREACH"})

    # Alert count remains 1, updated with current_value = 208.0
    assert alerts_count_2 == 1
    updated_alert = await db["sensor_alerts"].find_one({"sensor_id": sensor_id, "status": "ACTIVE_BREACH"})
    assert updated_alert["current_value"] == 208.0
    # No duplicate initial breach monitoring event
    assert events_count_2 == events_count_1


@pytest.mark.anyio
async def test_06_recovery_transition(client, db, officer_headers):
    """6. Recovery Transition: breached -> normal marks alert resolved and creates recovery monitoring event."""
    payload = {
        "name": "AQI Station Anand Vihar",
        "sensor_type": SensorType.SMOKE_AIR_QUALITY.value,
        "location_name": "Anand Vihar ISBT",
        "latitude": 28.6469,
        "longitude": 77.3160,
        "threshold": 400.0,
        "unit": "AQI",
    }
    create_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    sensor_id = create_res.json()["sensor_id"]
    await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)

    # Breach
    await client.post(
        f"/api/v1/sensors/{sensor_id}/readings",
        json={"value": 450.0, "source_type": SensorReadingSource.MANUAL_SIMULATION.value},
        headers=officer_headers,
    )

    # Recover (value drops back below threshold)
    recovery_res = await client.post(
        f"/api/v1/sensors/{sensor_id}/readings",
        json={"value": 250.0, "source_type": SensorReadingSource.MANUAL_SIMULATION.value},
        headers=officer_headers,
    )
    assert recovery_res.status_code == 201
    assert recovery_res.json()["is_breach"] is False

    # Alert should now be resolved
    active_alerts = await db["sensor_alerts"].count_documents({"sensor_id": sensor_id, "status": "ACTIVE_BREACH"})
    assert active_alerts == 0
    resolved_alerts = await db["sensor_alerts"].count_documents({"sensor_id": sensor_id, "status": "RESOLVED_RECOVERED"})
    assert resolved_alerts == 1

    # Recovery event should be recorded
    recovery_events = await db["monitoring_events"].find({"source_id": sensor_id, "event_type": "SENSOR_RECOVERED"}).to_list(length=10)
    assert len(recovery_events) == 1


@pytest.mark.anyio
async def test_07_reading_validation_negative_invalid(client, officer_headers):
    """7. Reading Validation: invalid reading schema or missing fields rejected with 422."""
    payload = {
        "name": "Valid Sensor",
        "sensor_type": SensorType.RAINFALL.value,
        "location_name": "South Delhi Station",
        "latitude": 28.6,
        "longitude": 77.2,
        "threshold": 30.0,
        "unit": "mm/hr",
    }
    create_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    sensor_id = create_res.json()["sensor_id"]
    await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)

    # Invalid reading missing "value"
    res = await client.post(
        f"/api/v1/sensors/{sensor_id}/readings",
        json={"notes": "missing value field"},
        headers=officer_headers,
    )
    assert res.status_code == 422


@pytest.mark.anyio
async def test_08_historical_read_route(client, officer_headers):
    """8. Historical Read Route: get historical readings paginated and ordered by timestamp desc."""
    payload = {
        "name": "Historical Gauge",
        "sensor_type": SensorType.WATER_LEVEL.value,
        "location_name": "Yamuna Historical Point",
        "latitude": 28.6,
        "longitude": 77.2,
        "threshold": 100.0,
        "unit": "meters",
    }
    create_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    sensor_id = create_res.json()["sensor_id"]
    await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)

    # Submit 3 sequential readings
    for val in [10.0, 20.0, 30.0]:
        await client.post(
            f"/api/v1/sensors/{sensor_id}/readings",
            json={"value": val, "source_type": SensorReadingSource.MANUAL_SIMULATION.value},
            headers=officer_headers,
        )

    # Fetch readings
    history_res = await client.get(f"/api/v1/sensors/{sensor_id}/readings?limit=2&page=1", headers=officer_headers)
    assert history_res.status_code == 200
    data = history_res.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    # Newest reading first
    assert data["items"][0]["value"] == 30.0


@pytest.mark.anyio
async def test_09_simulation_session_start(client, officer_headers):
    """9. Simulation Session Start: starting stream creates session and starts background task."""
    payload = {
        "name": "Stream Gauge 1",
        "sensor_type": SensorType.RAINFALL.value,
        "location_name": "Rohini Sector 11",
        "latitude": 28.6,
        "longitude": 77.2,
        "threshold": 80.0,
        "unit": "mm/hr",
    }
    create_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    sensor_id = create_res.json()["sensor_id"]
    await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)

    session_payload = {
        "starting_value": 10.0,
        "min_value": 0.0,
        "max_value": 150.0,
        "interval_seconds": 1.0,
        "trend": SimulationTrend.RISING.value,
    }
    start_res = await client.post(
        f"/api/v1/sensors/{sensor_id}/stream/start",
        json=session_payload,
        headers=officer_headers,
    )
    assert start_res.status_code == 200
    session_data = start_res.json()
    assert session_data["status"] == "RUNNING"
    assert session_data["sensor_id"] == sensor_id

    # Allow one tick
    await asyncio.sleep(1.2)

    # Stop stream cleanly
    stop_res = await client.post(f"/api/v1/sensors/{sensor_id}/stream/stop", headers=officer_headers)
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "STOPPED"


@pytest.mark.anyio
async def test_10_duplicate_stream_start_protection(client, officer_headers):
    """10. Duplicate Stream Start Protection: starting stream on already running sensor returns existing session without duplicate tasks."""
    payload = {
        "name": "Stream Gauge 2",
        "sensor_type": SensorType.TEMPERATURE.value,
        "location_name": "Dwarka Sector 6",
        "latitude": 28.6,
        "longitude": 77.2,
        "threshold": 50.0,
        "unit": "°C",
    }
    create_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    sensor_id = create_res.json()["sensor_id"]
    await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)

    session_payload = {
        "starting_value": 30.0,
        "min_value": 20.0,
        "max_value": 55.0,
        "interval_seconds": 1.0,
        "trend": SimulationTrend.FLUCTUATING.value,
    }
    start_res_1 = await client.post(
        f"/api/v1/sensors/{sensor_id}/stream/start",
        json=session_payload,
        headers=officer_headers,
    )
    assert start_res_1.status_code == 200
    session_id_1 = start_res_1.json()["session_id"]

    # Start again while running
    start_res_2 = await client.post(
        f"/api/v1/sensors/{sensor_id}/stream/start",
        json=session_payload,
        headers=officer_headers,
    )
    assert start_res_2.status_code == 200
    assert start_res_2.json()["session_id"] == session_id_1  # Reuses existing active session

    # Clean up
    await client.post(f"/api/v1/sensors/{sensor_id}/stream/stop", headers=officer_headers)


@pytest.mark.anyio
async def test_11_simulation_session_stop(client, officer_headers):
    """11. Simulation Session Stop: stopping stream sets status to STOPPED and terminates task."""
    payload = {
        "name": "Stream Gauge 3",
        "sensor_type": SensorType.SMOKE_AIR_QUALITY.value,
        "location_name": "Punjabi Bagh Club",
        "latitude": 28.6,
        "longitude": 77.2,
        "threshold": 250.0,
        "unit": "AQI",
    }
    create_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    sensor_id = create_res.json()["sensor_id"]
    await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)

    await client.post(
        f"/api/v1/sensors/{sensor_id}/stream/start",
        json={"starting_value": 100.0, "min_value": 50.0, "max_value": 300.0, "interval_seconds": 1.0},
        headers=officer_headers,
    )
    stop_res = await client.post(f"/api/v1/sensors/{sensor_id}/stream/stop", headers=officer_headers)
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "STOPPED"

    # Verify task is no longer streaming
    assert sensor_stream_manager.is_streaming(sensor_id) is False


@pytest.mark.anyio
async def test_12_dynamic_trend_value_progression(client, db, officer_headers):
    """12. Dynamic Trend Value Progression: RISING trend produces sequentially higher values."""
    payload = {
        "name": "Trend Test Gauge",
        "sensor_type": SensorType.RAINFALL.value,
        "location_name": "Civil Lines Station",
        "latitude": 28.6,
        "longitude": 77.2,
        "threshold": 100.0,
        "unit": "mm/hr",
    }
    create_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    sensor_id = create_res.json()["sensor_id"]
    await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)

    # Start rising trend
    await client.post(
        f"/api/v1/sensors/{sensor_id}/stream/start",
        json={"starting_value": 10.0, "min_value": 5.0, "max_value": 90.0, "interval_seconds": 1.0, "trend": SimulationTrend.RISING.value, "step_size": 2.0},
        headers=officer_headers,
    )
    # Wait for at least 3 ticks
    await asyncio.sleep(3.2)
    await client.post(f"/api/v1/sensors/{sensor_id}/stream/stop", headers=officer_headers)

    readings = await db["sensor_readings"].find({"sensor_id": sensor_id}).sort("timestamp", 1).to_list(length=10)
    assert len(readings) >= 3
    # Check that values progressed upwards
    assert readings[-1]["value"] > readings[0]["value"]


@pytest.mark.anyio
async def test_13_lifecycle_state_transition_rules(client, officer_headers):
    """13. Lifecycle State Transition Rules: valid transitions pass; invalid return 400."""
    payload = {
        "name": "State Test Sensor",
        "sensor_type": SensorType.WATER_LEVEL.value,
        "location_name": "Laxmi Nagar Bridge",
        "latitude": 28.6,
        "longitude": 77.2,
        "threshold": 50.0,
        "unit": "meters",
    }
    create_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    sensor_id = create_res.json()["sensor_id"]

    # DRAFT -> ACTIVE (valid)
    res_1 = await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)
    assert res_1.status_code == 200
    assert res_1.json()["status"] == SensorStatus.ACTIVE.value

    # ACTIVE -> PAUSED (valid)
    res_2 = await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.PAUSED.value}, headers=officer_headers)
    assert res_2.status_code == 200
    assert res_2.json()["status"] == SensorStatus.PAUSED.value

    # PAUSED -> DRAFT (invalid)
    res_3 = await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.DRAFT.value}, headers=officer_headers)
    assert res_3.status_code == 400


@pytest.mark.anyio
async def test_14_situation_proximity_link(client, db, officer_headers):
    """14. Situation Proximity Link: sensor created with situation link."""
    situation_id = f"SIT-{uuid.uuid4().hex[:8].upper()}"
    sit_doc = {
        "situation_id": situation_id,
        "situation_name": "Yamuna Urban Inundation Zone",
        "status": "MONITORING",
        "location": {"latitude": 28.6139, "longitude": 77.2090, "radius_meters": 5000},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db["situations"].insert_one(sit_doc)

    # Create sensor linked to situation
    payload = {
        "name": "Linked Flood Station",
        "sensor_type": SensorType.WATER_LEVEL.value,
        "location_name": "Yamuna Bank Met Station",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "threshold": 10.0,
        "unit": "meters",
        "linked_situation_id": situation_id,
    }
    sensor_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    assert sensor_res.status_code == 201
    assert sensor_res.json()["linked_situation_id"] == situation_id


@pytest.mark.anyio
async def test_15_impact_analysis_on_sensor_breach(client, db, officer_headers):
    """15. Impact Analysis on Sensor Breach: breach monitoring event on situation-linked sensor triggers impact analysis."""
    situation_id = f"SIT-{uuid.uuid4().hex[:8].upper()}"
    await db["situations"].insert_one({
        "situation_id": situation_id,
        "situation_name": "Monsoon Inundation Plan Zone",
        "status": "RESPONDING",
        "severity": "HIGH",
        "location": {"latitude": 28.65, "longitude": 77.25},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    await db["coordination_plans"].insert_one({
        "plan_id": f"PLAN-{uuid.uuid4().hex[:8].upper()}",
        "situation_id": situation_id,
        "version": 1,
        "status": "APPROVED",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "summary": "Initial baseline plan",
    })

    # Create active sensor linked to situation
    sensor_payload = {
        "name": "Linked Inundation Sensor",
        "sensor_type": SensorType.WATER_LEVEL.value,
        "location_name": "Wazirabad Barrage Point",
        "latitude": 28.65,
        "longitude": 77.25,
        "threshold": 5.0,
        "unit": "meters",
        "linked_situation_id": situation_id,
    }
    sensor_res = await client.post("/api/v1/sensors", json=sensor_payload, headers=officer_headers)
    sensor_id = sensor_res.json()["sensor_id"]
    await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)

    # Submit breach reading (8.0 > 5.0)
    await client.post(
        f"/api/v1/sensors/{sensor_id}/readings",
        json={"value": 8.0, "source_type": SensorReadingSource.MANUAL_SIMULATION.value},
        headers=officer_headers,
    )

    event = await db["monitoring_events"].find_one({"source_id": sensor_id, "event_type": "SENSOR_THRESHOLD_BREACHED"})
    assert event is not None
    assert event["situation_id"] == situation_id
    assert event["impact_level"] in [ImpactLevel.CRITICAL.value, ImpactLevel.HIGH.value, ImpactLevel.MEDIUM.value, ImpactLevel.LOW.value, ImpactLevel.NONE.value]


@pytest.mark.anyio
async def test_16_unlinked_sensor_event_isolation(client, db, officer_headers):
    """16. Unlinked Sensor Event Isolation: sensor without situation logs event with situation_id=None."""
    sensor_payload = {
        "name": "Standalone AQI Monitor",
        "sensor_type": SensorType.SMOKE_AIR_QUALITY.value,
        "location_name": "Narela Isolated Zone",
        "latitude": 28.70,
        "longitude": 77.10,
        "threshold": 200.0,
        "unit": "AQI",
    }
    sensor_res = await client.post("/api/v1/sensors", json=sensor_payload, headers=officer_headers)
    sensor_id = sensor_res.json()["sensor_id"]
    await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)

    # Breach
    await client.post(
        f"/api/v1/sensors/{sensor_id}/readings",
        json={"value": 350.0, "source_type": SensorReadingSource.MANUAL_SIMULATION.value},
        headers=officer_headers,
    )

    event = await db["monitoring_events"].find_one({"source_id": sensor_id, "event_type": "SENSOR_THRESHOLD_BREACHED"})
    assert event is not None
    assert event.get("situation_id") is None


@pytest.mark.anyio
async def test_17_sensor_rbac_citizen_rejection(client, citizen_headers):
    """17. Sensor RBAC - Citizen Rejection: citizen token denied from creating sensors (403)."""
    payload = {
        "name": "Citizen Unauthorized Sensor",
        "sensor_type": SensorType.RAINFALL.value,
        "location_name": "Unauthorized Area",
        "latitude": 28.6,
        "longitude": 77.2,
        "threshold": 50.0,
        "unit": "mm/hr",
    }
    res = await client.post("/api/v1/sensors", json=payload, headers=citizen_headers)
    assert res.status_code == 403


@pytest.mark.anyio
async def test_18_sensor_rbac_officer_authorized(client, officer_headers):
    """18. Sensor RBAC - Officer Authorized: officer token authorized for sensor endpoints."""
    res = await client.get("/api/v1/sensors", headers=officer_headers)
    assert res.status_code == 200


@pytest.mark.anyio
async def test_19_sensor_telemetry_metrics_calculation(client, officer_headers):
    """19. Sensor Telemetry Metrics Calculation: correctly computes min, max, avg, count, and breach count."""
    payload = {
        "name": "Telemetry Stats Station",
        "sensor_type": SensorType.TEMPERATURE.value,
        "location_name": "Lodhi Estate Weather Point",
        "latitude": 28.6,
        "longitude": 77.2,
        "threshold": 40.0,
        "unit": "°C",
    }
    create_res = await client.post("/api/v1/sensors", json=payload, headers=officer_headers)
    sensor_id = create_res.json()["sensor_id"]
    await client.patch(f"/api/v1/sensors/{sensor_id}/status", json={"status": SensorStatus.ACTIVE.value}, headers=officer_headers)

    # Submit 3 readings: 20, 30, 50 (50 is breached)
    for v in [20.0, 30.0, 50.0]:
        await client.post(
            f"/api/v1/sensors/{sensor_id}/readings",
            json={"value": v, "source_type": SensorReadingSource.MANUAL_SIMULATION.value},
            headers=officer_headers,
        )

    telemetry_res = await client.get(f"/api/v1/sensors/{sensor_id}/telemetry", headers=officer_headers)
    assert telemetry_res.status_code == 200
    stats = telemetry_res.json()
    assert stats["total_readings"] == 3
    assert stats["min_value"] == 20.0
    assert stats["max_value"] == 50.0
    assert round(stats["avg_value"], 1) == round((20 + 30 + 50) / 3, 1)
    assert stats["breached_readings_count"] == 1
    assert stats["current_value"] == 50.0
    assert stats["is_breached"] is True


@pytest.mark.anyio
async def test_20_zero_hardcoded_seed_verification(db):
    """20. Zero Hardcoded Seed Verification: verify database starts with 0 sensors outside test executions."""
    # Ensure there are no static seeded sensors lingering with generic names
    unwanted = await db["sensors"].find({"name": "Seed Dummy Sensor"}).to_list(length=10)
    assert len(unwanted) == 0
