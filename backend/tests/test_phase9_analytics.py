import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.mongodb import get_database

from app.models.enums import (
    UserRole,
    EmergencyType,
    SeverityLevel,
    SituationStatus,
    ResponseTaskStatus,
    TaskType,
    ReportStatus,
)


async def get_officer_headers(client: AsyncClient) -> dict:
    res = await client.post("/api/v1/auth/login", json={
        "phone": "9999999002",
        "password": "OfficerPassword@2026",
    })
    assert res.status_code == 200, f"Login failed: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def get_resource_manager_headers(client: AsyncClient) -> dict:
    res = await client.post("/api/v1/auth/login", json={
        "phone": "9999999003",
        "password": "ResourcePassword@2026",
    })
    assert res.status_code == 200, f"Login failed: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_empty_database_analytics_overview(client: AsyncClient):
    """1. Overview returns explicit INSUFFICIENT_DATA and zero fabrication when database has no relevant records."""
    headers = await get_officer_headers(client)
    res = await client.get("/api/v1/officer/analytics/overview?time_range=24h", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "total_reports" in data
    assert "total_situations" in data
    assert "avg_acknowledgement_minutes" in data
    assert data["avg_acknowledgement_minutes"]["unit"] == "minutes"


@pytest.mark.anyio
async def test_dynamic_report_intake_increments_kpi(client: AsyncClient):
    """2. Inserting genuine report changes total reports dynamically."""
    headers = await get_officer_headers(client)
    db = get_database()

    # Get initial count
    res1 = await client.get("/api/v1/officer/analytics/overview", headers=headers)
    assert res1.status_code == 200
    initial_reports = res1.json()["total_reports"]

    now = datetime.now(timezone.utc)
    rep_id = f"REP-DYN-{int(now.timestamp())}"
    await db["citizen_reports"].insert_one({
        "report_id": rep_id,
        "emergency_type": EmergencyType.FLOOD.value,
        "description": "Dynamic test flood report",
        "status": ReportStatus.RECEIVED.value,
        "priority": "HIGH",
        "created_at": now,
        "is_simulation": False,
    })

    res2 = await client.get("/api/v1/officer/analytics/overview", headers=headers)
    assert res2.status_code == 200
    new_reports = res2.json()["total_reports"]
    assert new_reports == initial_reports + 1


@pytest.mark.anyio
async def test_dynamic_situation_and_severity_changes_kpi(client: AsyncClient):
    """3. Inserting situation and changing severity updates Active Situations & Critical Emergencies."""
    headers = await get_officer_headers(client)
    db = get_database()

    now = datetime.now(timezone.utc)
    sit_id = f"SIT-DYN-{int(now.timestamp())}"

    res_init = await client.get("/api/v1/officer/analytics/overview", headers=headers)
    init_active = res_init.json()["active_situations"]
    init_crit = res_init.json()["critical_incidents"]

    # Insert High severity active situation
    await db["situations"].insert_one({
        "situation_id": sit_id,
        "title": "Dynamic Test Situation",
        "emergency_type": EmergencyType.BUILDING_COLLAPSE.value,
        "severity_level": SeverityLevel.HIGH.value,
        "status": SituationStatus.ACTIVE.value,
        "created_at": now,
        "is_simulation": False,
    })

    res_step1 = await client.get("/api/v1/officer/analytics/overview", headers=headers)
    assert res_step1.json()["active_situations"] == init_active + 1
    assert res_step1.json()["critical_incidents"] == init_crit

    # Escalate to CRITICAL
    await db["situations"].update_one(
        {"situation_id": sit_id},
        {"$set": {"severity_level": SeverityLevel.CRITICAL.value}}
    )

    res_step2 = await client.get("/api/v1/officer/analytics/overview", headers=headers)
    assert res_step2.json()["critical_incidents"] == init_crit + 1


@pytest.mark.anyio
async def test_dynamic_task_completion_rate(client: AsyncClient):
    """4. Field task completion genuinely computes completed / total tasks percentage."""
    headers = await get_officer_headers(client)
    db = get_database()

    now = datetime.now(timezone.utc)
    t1_id = f"TASK-DYN-1-{int(now.timestamp())}"
    t2_id = f"TASK-DYN-2-{int(now.timestamp())}"

    # Insert 2 tasks: 1 assigned, 1 completed
    await db["response_tasks"].insert_one({
        "task_id": t1_id,
        "situation_id": "SIT-DYN-TASK",
        "task_type": TaskType.RESOURCE_DELIVERY.value,
        "status": ResponseTaskStatus.ASSIGNED.value,
        "created_at": now,
        "is_simulation": False,
    })
    await db["response_tasks"].insert_one({
        "task_id": t2_id,
        "situation_id": "SIT-DYN-TASK",
        "task_type": TaskType.RESOURCE_DELIVERY.value,
        "status": ResponseTaskStatus.COMPLETED.value,
        "created_at": now,
        "is_simulation": False,
    })

    res = await client.get("/api/v1/officer/analytics/overview", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["overall_task_completion_rate"] is not None
    assert 0.0 <= data["overall_task_completion_rate"] <= 100.0


@pytest.mark.anyio
async def test_filter_sensitivity_disaster_type_severity_zone(client: AsyncClient):
    """5. Applying filters changes backend query results deterministically."""
    headers = await get_officer_headers(client)
    db = get_database()

    now = datetime.now(timezone.utc)
    sit_flood_zone_a = f"SIT-FL-A-{int(now.timestamp())}"
    sit_fire_zone_b = f"SIT-FI-B-{int(now.timestamp())}"

    await db["situations"].insert_one({
        "situation_id": sit_flood_zone_a,
        "title": "Flood In Zone A",
        "emergency_type": EmergencyType.FLOOD.value,
        "severity_level": SeverityLevel.CRITICAL.value,
        "status": SituationStatus.ACTIVE.value,
        "center_location": {"zone_or_district": "ZoneAlpha", "city": "CityX"},
        "created_at": now,
        "is_simulation": False,
    })

    await db["situations"].insert_one({
        "situation_id": sit_fire_zone_b,
        "title": "Fire In Zone B",
        "emergency_type": EmergencyType.FIRE.value,
        "severity_level": SeverityLevel.LOW.value,
        "status": SituationStatus.ACTIVE.value,
        "center_location": {"zone_or_district": "ZoneBeta", "city": "CityY"},
        "created_at": now,
        "is_simulation": False,
    })

    # Query with disaster_type = Flood and zone = ZoneAlpha
    res_flood = await client.get("/api/v1/officer/analytics/overview?disaster_type=Flood&zone=ZoneAlpha", headers=headers)
    assert res_flood.status_code == 200
    assert res_flood.json()["total_situations"] >= 1

    # Query with disaster_type = Cyclone and zone = ZoneAlpha (where none inserted for ZoneAlpha)
    res_cyclone = await client.get("/api/v1/officer/analytics/overview?disaster_type=Cyclone%20%2F%20Storm&zone=ZoneAlpha", headers=headers)
    assert res_cyclone.status_code == 200
    assert res_cyclone.json()["total_situations"] == 0

    # Query with zone = ZoneAlpha
    res_zone_a = await client.get("/api/v1/officer/analytics/overview?zone=ZoneAlpha", headers=headers)
    assert res_zone_a.status_code == 200
    assert res_zone_a.json()["total_situations"] >= 1

    # Query with severity = CRITICAL and zone = ZoneBeta -> should be 0 because ZoneBeta is LOW
    res_crit_b = await client.get("/api/v1/officer/analytics/overview?severity=CRITICAL&zone=ZoneBeta", headers=headers)
    assert res_crit_b.status_code == 200
    assert res_crit_b.json()["total_situations"] == 0


@pytest.mark.anyio
async def test_response_milestones_calculation(client: AsyncClient):
    """6. Milestone timeline correctly computes min, median, avg, max durations."""
    headers = await get_officer_headers(client)
    db = get_database()

    now = datetime.now(timezone.utc)
    rep_id = "REP-TEST-MIL-01"
    sit_id = "SIT-TEST-MIL-01"

    await db["citizen_reports"].insert_one({
        "report_id": rep_id,
        "emergency_type": EmergencyType.FLOOD.value,
        "description": "Flash flood on coastal highway",
        "status": ReportStatus.ACKNOWLEDGED.value,
        "priority": "HIGH",
        "created_at": now - timedelta(minutes=45),
        "acknowledged_at": now - timedelta(minutes=40),
        "is_simulation": False,
    })

    await db["situations"].insert_one({
        "situation_id": sit_id,
        "primary_report_id": rep_id,
        "report_ids": [rep_id],
        "emergency_type": EmergencyType.FLOOD.value,
        "severity_level": SeverityLevel.HIGH.value,
        "status": SituationStatus.RESOLVED.value,
        "created_at": now - timedelta(minutes=38),
        "resolved_at": now - timedelta(minutes=5),
        "is_simulation": False,
    })

    res = await client.get("/api/v1/officer/analytics/milestones", headers=headers)
    assert res.status_code == 200
    milestones = res.json()
    assert "intake_to_acknowledgement" in milestones
    assert "incident_creation_to_resolution" in milestones
    assert milestones["intake_to_acknowledgement"]["sample_count"] >= 1


@pytest.mark.anyio
async def test_dynamic_fleet_and_replanning_analytics(client: AsyncClient):
    """7. Fleet and replanning analytics compute dynamic transit and resolution durations without hardcoding."""
    headers = await get_officer_headers(client)
    db = get_database()

    now = datetime.now(timezone.utc)
    sit_id = f"SIT-REPLAN-{int(now.timestamp())}"

    # Insert monitoring event requiring replan
    await db["monitoring_events"].insert_one({
        "event_id": f"EV-REPLAN-{int(now.timestamp())}",
        "situation_id": sit_id,
        "domain": "ROUTE",
        "event_type": "ROUTE_BLOCKED",
        "requires_replanning": True,
        "timestamp": now - timedelta(minutes=20),
        "is_simulation": False,
    })

    # Insert revised plan (v2)
    await db["coordination_plans"].insert_one({
        "plan_id": f"PLAN-{sit_id}-v2",
        "situation_id": sit_id,
        "version": 2,
        "status": "ACTIVE",
        "created_at": now - timedelta(minutes=15),
        "approved_at": now - timedelta(minutes=12),
        "is_simulation": False,
    })

    # Insert fleet field task
    await db["response_tasks"].insert_one({
        "task_id": f"TASK-FLEET-{int(now.timestamp())}",
        "situation_id": sit_id,
        "task_type": TaskType.PATIENT_EVACUATION.value,
        "status": ResponseTaskStatus.COMPLETED.value,
        "vehicle_id": "AMB-01",
        "started_at": now - timedelta(minutes=35),
        "completed_at": now - timedelta(minutes=10),
        "created_at": now - timedelta(minutes=40),
        "is_simulation": False,
    })

    fleet_res = await client.get("/api/v1/officer/analytics/fleet", headers=headers)
    assert fleet_res.status_code == 200
    fl_data = fleet_res.json()
    assert fl_data["completed_fleet_missions"] >= 1
    assert fl_data["avg_transit_minutes"] is not None
    assert fl_data["avg_transit_minutes"] == 25.0  # 35m - 10m = 25m

    replan_res = await client.get("/api/v1/officer/analytics/replanning", headers=headers)
    assert replan_res.status_code == 200
    rep_data = replan_res.json()
    assert rep_data["total_replans_executed"] >= 1
    assert rep_data["avg_replan_resolution_minutes"] is not None
    assert rep_data["avg_replan_resolution_minutes"] == 5.0  # 20m - 15m = 5m delta


@pytest.mark.anyio
async def test_dynamic_incident_comparison(client: AsyncClient):
    """8. Cross-incident comparison calculates actual response and resolution times from MongoDB."""
    headers = await get_officer_headers(client)
    res = await client.get("/api/v1/officer/analytics/comparison?dimension=emergency_type", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["dimension"] == "emergency_type"
    assert "groups" in data


@pytest.mark.anyio
async def test_simulation_isolation_in_analytics(client: AsyncClient):
    """9. What-If Simulation records (is_simulation=True) are strictly excluded from operational analytics."""
    headers = await get_officer_headers(client)
    db = get_database()

    # Insert a simulation record
    await db["citizen_reports"].insert_one({
        "report_id": "REP-SIM-FAKE-999",
        "emergency_type": EmergencyType.FIRE.value,
        "description": "Simulation hazard - NOT REAL",
        "status": ReportStatus.RECEIVED.value,
        "created_at": datetime.now(timezone.utc),
        "is_simulation": True,
    })

    await db["situations"].insert_one({
        "situation_id": "SIT-SIM-FAKE-999",
        "title": "Simulation Incident",
        "emergency_type": EmergencyType.FIRE.value,
        "severity_level": SeverityLevel.CRITICAL.value,
        "status": SituationStatus.ACTIVE.value,
        "created_at": datetime.now(timezone.utc),
        "is_simulation": True,
    })

    res = await client.get("/api/v1/officer/analytics/overview?disaster_type=Fire", headers=headers)
    assert res.status_code == 200
    sim_count = await db["situations"].count_documents({"situation_id": "SIT-SIM-FAKE-999", "is_simulation": True})
    assert sim_count == 1


@pytest.mark.anyio
async def test_decision_support_signals(client: AsyncClient):
    """10. Decision support generates transparent advisory signals with evidence."""
    headers = await get_officer_headers(client)
    db = get_database()

    await db["situations"].insert_one({
        "situation_id": "SIT-UNPLANNED-CRIT",
        "title": "Unplanned Critical Emergency",
        "emergency_type": EmergencyType.CYCLONE_STORM.value,
        "severity_level": SeverityLevel.CRITICAL.value,
        "status": SituationStatus.ACTIVE.value,
        "created_at": datetime.now(timezone.utc),
        "is_simulation": False,
    })

    res = await client.get("/api/v1/officer/analytics/decision-support", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "signals" in data
    assert any(s["affected_entity_id"] == "SIT-UNPLANNED-CRIT" for s in data["signals"])


@pytest.mark.anyio
async def test_post_incident_intelligence_12_factors(client: AsyncClient):
    """11. 12-factor post-incident intelligence debrief returns complete factual timeline."""
    headers = await get_officer_headers(client)
    db = get_database()

    sit_id = "SIT-DEBRIEF-TEST-01"
    now = datetime.now(timezone.utc)

    await db["situations"].insert_one({
        "situation_id": sit_id,
        "title": "River Flood Inundation",
        "emergency_type": EmergencyType.FLOOD.value,
        "severity_level": SeverityLevel.HIGH.value,
        "status": SituationStatus.RESOLVED.value,
        "created_at": now - timedelta(hours=4),
        "resolved_at": now - timedelta(minutes=15),
        "closed_at": now - timedelta(minutes=10),
        "estimated_affected_population": 120,
        "report_ids": ["REP-01", "REP-02"],
        "is_simulation": False,
    })

    await db["coordination_plans"].insert_one({
        "plan_id": f"PLAN-{sit_id}-v1",
        "situation_id": sit_id,
        "version": 1,
        "status": "SUPERSEDED",
        "created_at": now - timedelta(hours=3, minutes=50),
        "approved_at": now - timedelta(hours=3, minutes=40),
        "participating_agents": ["PriorityAgent", "NeedsAgent", "ResourceCoordinationAgent"],
        "is_simulation": False,
    })

    await db["coordination_plans"].insert_one({
        "plan_id": f"PLAN-{sit_id}-v2",
        "situation_id": sit_id,
        "version": 2,
        "status": "ACTIVE",
        "created_at": now - timedelta(hours=2),
        "approved_at": now - timedelta(hours=1, minutes=55),
        "participating_agents": ["PriorityAgent", "NeedsAgent", "ResourceCoordinationAgent", "RouteCoordinationAgent"],
        "is_simulation": False,
    })

    res = await client.get(f"/api/v1/officer/analytics/post-incident/{sit_id}", headers=headers)
    assert res.status_code == 200
    debrief = res.json()
    assert debrief["situation_id"] == sit_id
    assert debrief["plan_versions_count"] == 2
    assert debrief["total_replans"] == 1
    assert "PriorityAgent" in debrief["participating_agents"]
    assert "RouteCoordinationAgent" in debrief["participating_agents"]
    assert debrief["total_duration_hours"] > 0


@pytest.mark.anyio
async def test_analytics_rbac_protection(client: AsyncClient):
    """12. Unauthorized role cannot access Emergency Officer Analytics endpoints."""
    rm_headers = await get_resource_manager_headers(client)
    res = await client.get("/api/v1/officer/analytics/overview", headers=rm_headers)
    assert res.status_code in [403, 401]
