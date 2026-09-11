import pytest
import uuid
from datetime import datetime, timezone
from httpx import AsyncClient

from app.models.enums import (
    UserRole,
    MonitoringEventType,
    EventSourceType,
    AgentName,
    HealthcareConflictType,
)
from app.models.agent import AgentContext
from app.services.agents.adapters.healthcare_agent import HealthcareCoordinationAgent
from app.services.monitoring.impact_analyzer import ChangeImpactAnalyzer
from app.services.monitoring.monitoring_service import MonitoringService
from app.services.analytics_service import AnalyticsService
from app.db.mongodb import db_manager


async def get_token(client: AsyncClient, phone: str, password: str, intended_role: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"phone": phone, "password": password, "intended_role": intended_role},
    )
    assert res.status_code == 200, f"Login failed for {phone}: {res.text}"
    return res.json()["access_token"]


@pytest.mark.anyio
async def test_01_create_healthcare_facility(client: AsyncClient):
    """Test 1 & 4: Register genuine healthcare facility and verify derived available capacity."""
    token = await get_token(client, "9999999003", "ResourcePassword@2026", "RESOURCE_MANAGER")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "facility_name": "Manipal Emergency Hospital",
        "facility_type": "Hospital",
        "location": {
            "latitude": 12.9716,
            "longitude": 77.5946,
            "address": "98 HAL Old Airport Rd, Kodihalli",
            "city": "Bangalore",
            "district": "Urban",
            "state": "Karnataka",
            "country": "India",
            "postal_code": "560001",
            "zone": "Central",
        },
        "total_beds": 300,
        "occupied_beds": 200,
        "total_icu_beds": 30,
        "occupied_icu_beds": 20,
        "total_emergency_beds": 40,
        "occupied_emergency_beds": 25,
        "ventilators_total": 15,
        "ventilators_available": 10,
        "oxygen_supported_beds": 100,
        "oxygen_available_capacity": 60,
        "capabilities": {
            "emergency_care": True,
            "trauma_care": True,
            "icu": True,
            "surgery": True,
            "oxygen_support": True,
            "ventilator_support": True,
            "ambulance_support": True,
            "pediatric_care": False,
            "burn_unit": False,
            "other_capabilities": [],
        },
        "status": "ACTIVE",
        "condition": "EXCELLENT",
        "accessibility": "FULLY_ACCESSIBLE",
        "contact_phone": "+91 80 2502 4444",
        "operating_hours": "24/7",
    }

    res = await client.post("/api/v1/healthcare/facilities", json=payload, headers=headers)
    assert res.status_code == 201, f"Facility creation failed: {res.text}"
    data = res.json()
    assert data["facility_name"] == "Manipal Emergency Hospital"
    assert data["facility_id"].startswith("HCF-")
    # Verified derived capacity
    assert data["total_beds"] == 300
    assert data["occupied_beds"] == 200
    assert data["available_beds"] == 100
    assert data["available_icu_beds"] == 10
    assert data["available_emergency_beds"] == 15
    assert data["capabilities"]["trauma_care"] is True


@pytest.mark.anyio
async def test_02_retrieve_healthcare_facility_and_stats(client: AsyncClient):
    """Test 2 & 5: Retrieve healthcare facilities and stats from genuine MongoDB data."""
    token = await get_token(client, "9999999003", "ResourcePassword@2026", "RESOURCE_MANAGER")
    headers = {"Authorization": f"Bearer {token}"}

    # List facilities
    res = await client.get("/api/v1/healthcare/facilities", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_count"] >= 1
    fac = data["items"][0]
    fac_id = fac["facility_id"]

    # Retrieve single
    res_single = await client.get(f"/api/v1/healthcare/facilities/{fac_id}", headers=headers)
    assert res_single.status_code == 200
    assert res_single.json()["facility_id"] == fac_id

    # Retrieve stats
    res_stats = await client.get("/api/v1/healthcare/facilities/stats", headers=headers)
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["total_facilities"] >= 1
    assert stats["total_available_beds"] >= 100
    assert stats["available_icu_beds"] >= 10


@pytest.mark.anyio
async def test_03_update_capacity_and_monitoring_event(client: AsyncClient):
    """Test 3, 4, 8, 17: Update bed occupancy, verify derived calculation and monitoring event."""
    db = db_manager.db
    token = await get_token(client, "9999999003", "ResourcePassword@2026", "RESOURCE_MANAGER")
    headers = {"Authorization": f"Bearer {token}"}

    fac_doc = await db["healthcare_facilities"].find_one({"is_deleted": {"$ne": True}})
    assert fac_doc is not None
    fac_id = fac_doc["facility_id"]

    # Update occupied beds from 200 -> 250 (Total 300 -> Available should become 50)
    # ICU from 20 -> 25 (Total 30 -> Available ICU becomes 5)
    update_payload = {
        "occupied_beds": 250,
        "occupied_icu_beds": 25,
        "occupied_emergency_beds": 30,
        "reason": "Triage intake surge from severe industrial incident",
    }

    res = await client.patch(f"/api/v1/healthcare/facilities/{fac_id}/capacity", json=update_payload, headers=headers)
    assert res.status_code == 200, f"Capacity update failed: {res.text}"
    updated = res.json()
    assert updated["occupied_beds"] == 250
    assert updated["available_beds"] == 50
    assert updated["available_icu_beds"] == 5
    assert updated["available_emergency_beds"] == 10

    # Verify MonitoringEvent was recorded in MongoDB
    event = await db["monitoring_events"].find_one({
        "source_type": EventSourceType.HEALTHCARE_FACILITY.value,
        "event_type": MonitoringEventType.HEALTHCARE_CAPACITY_CHANGED.value,
        "source_id": fac_id,
    })
    assert event is not None, "MonitoringEvent for HEALTHCARE_CAPACITY_CHANGED was not recorded."
    assert event["new_state"]["available_beds"] == 50
    assert event["new_state"]["available_icu_beds"] == 5


@pytest.mark.anyio
async def test_04_reject_invalid_capacity(client: AsyncClient):
    """Test 7 & 8: Reject negative capacity and occupied > total."""
    db = db_manager.db
    token = await get_token(client, "9999999003", "ResourcePassword@2026", "RESOURCE_MANAGER")
    headers = {"Authorization": f"Bearer {token}"}

    fac_doc = await db["healthcare_facilities"].find_one({"is_deleted": {"$ne": True}})
    fac_id = fac_doc["facility_id"]

    # Occupied > Total (Total is 300, occupied is 350)
    res1 = await client.patch(f"/api/v1/healthcare/facilities/{fac_id}/capacity", json={"occupied_beds": 350}, headers=headers)
    assert res1.status_code == 400
    assert "cannot exceed" in res1.json()["detail"].lower() or "must be between" in res1.json()["detail"].lower()

    # Negative capacity
    res2 = await client.patch(f"/api/v1/healthcare/facilities/{fac_id}/capacity", json={"occupied_beds": -10}, headers=headers)
    assert res2.status_code in [400, 422]


@pytest.mark.anyio
async def test_05_healthcare_rbac_protection(client: AsyncClient):
    """Test 9: Verify unauthenticated and unauthorized roles cannot modify facility data."""
    # Unauthenticated
    res1 = await client.post("/api/v1/healthcare/facilities", json={})
    assert res1.status_code in [401, 403]

    # Emergency Officer token (can view but cannot create new facility)
    token_officer = await get_token(client, "9999999002", "OfficerPassword@2026", "EMERGENCY_OFFICER")
    res2 = await client.post(
        "/api/v1/healthcare/facilities",
        json={
            "facility_name": "Unauthorized Clinic",
            "facility_type": "Hospital",
            "location": {
                "latitude": 12.9716,
                "longitude": 77.5946,
                "address": "MG Road",
                "city": "Bangalore",
                "district": "Urban",
                "state": "Karnataka",
                "country": "India",
                "postal_code": "560001",
            },
            "total_beds": 50,
            "occupied_beds": 10,
        },
        headers={"Authorization": f"Bearer {token_officer}"},
    )
    assert res2.status_code == 403


@pytest.mark.anyio
async def test_06_healthcare_agent_reads_genuine_facility_and_allocates():
    """Test 10, 11, 12, 13: Healthcare Agent evaluates real facilities, distance, capabilities, and allocates."""
    agent = HealthcareCoordinationAgent()

    # Create 2 genuine hospital records
    fac_a = {
        "facility_id": "HCF-TEST-A",
        "facility_name": "Metro General Hospital",
        "total_beds": 200,
        "occupied_beds": 120,
        "available_beds": 80,
        "total_icu_beds": 20,
        "occupied_icu_beds": 10,
        "available_icu_beds": 10,
        "total_emergency_beds": 30,
        "occupied_emergency_beds": 15,
        "available_emergency_beds": 15,
        "location": {"latitude": 12.9716, "longitude": 77.5946, "address": "Central District"},
        "capabilities": {"trauma_care": True, "icu": True, "oxygen_support": True, "emergency_care": True},
        "status": "ACTIVE",
        "condition": "EXCELLENT",
    }
    fac_b = {
        "facility_id": "HCF-TEST-B",
        "facility_name": "Apollo Care Center",
        "total_beds": 150,
        "occupied_beds": 80,
        "available_beds": 70,
        "total_icu_beds": 15,
        "occupied_icu_beds": 5,
        "available_icu_beds": 10,
        "total_emergency_beds": 20,
        "occupied_emergency_beds": 10,
        "available_emergency_beds": 10,
        "location": {"latitude": 12.9800, "longitude": 77.6000, "address": "North District"},
        "capabilities": {"trauma_care": True, "icu": True, "oxygen_support": True, "emergency_care": True},
        "status": "ACTIVE",
        "condition": "EXCELLENT",
    }

    # Demand: 120 casualties
    ctx = AgentContext(
        situation_id="SIT-TEST-001",
        situation_title="Commercial Building Collapse",
        description="Structural collapse with multiple casualties reported",
        location_summary="Central District Hub",
        emergency_type="Building Collapse",
        center_latitude=12.9720,
        center_longitude=77.5950,
        parameters={
            "estimated_casualties": 120,
            "available_facilities": [fac_a, fac_b],
        },
    )

    res = await agent.execute(ctx)
    assert res.status.value == "COMPLETED"
    summary = res.structured_output
    assert summary["medical_required"] is True
    assert summary["total_patients_covered"] == 120.0
    assert summary["total_shortfall"] == 0.0
    assert len(summary["facilities_recommended"]) == 2

    # Verify Multi-hospital distribution
    # Total allocated across facilities must equal 120 patients
    rec_a = next((r for r in summary["facilities_recommended"] if r["facility_id"] == "HCF-TEST-A"), None)
    rec_b = next((r for r in summary["facilities_recommended"] if r["facility_id"] == "HCF-TEST-B"), None)
    assert rec_a is not None and rec_b is not None
    assert rec_a["allocated_patients"] + rec_b["allocated_patients"] == 120.0


@pytest.mark.anyio
async def test_07_healthcare_shortage_conflict_generation():
    """Test 14 & 15: Healthcare Agent detects shortage and generates HEALTHCARE_CAPACITY_SHORTAGE."""
    agent = HealthcareCoordinationAgent()

    fac_small = {
        "facility_id": "HCF-SMALL",
        "facility_name": "Rural Emergency Clinic",
        "total_beds": 50,
        "occupied_beds": 30,
        "available_beds": 20,
        "location": {"latitude": 12.9716, "longitude": 77.5946, "address": "Sector 4"},
        "capabilities": {"trauma_care": True, "icu": False, "oxygen_support": True, "emergency_care": True},
        "status": "ACTIVE",
        "condition": "EXCELLENT",
    }

    # Demand: 50 casualties, only 20 beds available -> Shortfall of 30
    ctx = AgentContext(
        situation_id="SIT-TEST-002",
        situation_title="Expressway Multi-Vehicle Accident",
        description="Mass transport accident with trauma injuries",
        location_summary="Outer Highway Sector 4",
        emergency_type="Road Accident",
        center_latitude=12.9716,
        center_longitude=77.5946,
        parameters={
            "estimated_casualties": 50,
            "available_facilities": [fac_small],
        },
    )

    res = await agent.execute(ctx)
    summary = res.structured_output
    assert summary["total_patients_covered"] == 20.0
    assert summary["total_shortfall"] == 30.0
    assert HealthcareConflictType.HEALTHCARE_CAPACITY_SHORTAGE.value in summary["conflicts"]
    assert summary["officer_attention_required"] is True


@pytest.mark.anyio
async def test_08_change_impact_analyzer_healthcare_invalidation():
    """Test 17 & 18: Live Monitoring detects hospital bed decrease and triggers dynamic replanning."""
    db = db_manager.db
    analyzer = ChangeImpactAnalyzer()

    # Active plan had Hospital Alpha with 30 casualty allocation
    from app.models.agent import CoordinationPlan, RecommendedHealthcareFacility
    from app.models.enums import CoordinationPlanStatus, SeverityLevel

    plan = CoordinationPlan(
        plan_id="PLAN-TEST-HLT",
        situation_id="SIT-TEST-003",
        status=CoordinationPlanStatus.ACTIVE,
        version=1,
        assessed_priority=SeverityLevel.HIGH,
        reasoning="Authoritative active plan for situation SIT-TEST-003",
        recommended_facilities=[
            RecommendedHealthcareFacility(
                facility_id="HCF-HOSP-ALPHA",
                facility_name="Hospital Alpha",
                facility_type="Hospital",
                distance_km=2.5,
                total_beds=100,
                available_beds=30,
                allocated_patients=30.0,
                coverage_percentage=100.0,
                icu_available=5,
                oxygen_available=True,
                trauma_capable=True,
                emergency_capable=True,
                suitability_score=95.0,
                ranking_factors={},
                recommendation_reason="Primary triage center",
                location_address="Main St",
                status="ACTIVE",
            )
        ],
    )

    # State transition: Hospital Alpha available beds drops from 30 -> 5
    from app.models.monitoring import MonitoringEvent
    event = MonitoringEvent(
        event_id="EVT-TEST-HLT-01",
        event_type=MonitoringEventType.HEALTHCARE_CAPACITY_CHANGED,
        source_type=EventSourceType.HEALTHCARE_FACILITY,
        source_id="HCF-HOSP-ALPHA",
        situation_id="SIT-TEST-003",
        coordination_plan_id="PLAN-TEST-HLT",
        event_fingerprint="fp-test-01",
        previous_state={"facility_name": "Hospital Alpha", "available_beds": 30},
        new_state={"facility_name": "Hospital Alpha", "available_beds": 5, "status": "ACTIVE"},
    )

    impact = await ChangeImpactAnalyzer.analyze_impact(event, active_plan=plan, db=db)
    assert impact.impact_level.value in ["HIGH", "CRITICAL"]
    assert impact.plan_status.value == "INVALIDATED"
    assert impact.officer_attention_required is True
    assert AgentName.HEALTHCARE_AGENT in impact.affected_agents


@pytest.mark.anyio
async def test_09_analytics_integration_real_data(client: AsyncClient):
    """Test 20, 21, 22: Verify Analytics aggregates real healthcare facilities and isolates simulation."""
    db = db_manager.db
    token = await get_token(client, "9999999001", "AdminPassword@2026", "ADMIN")

    analytics = await AnalyticsService.get_healthcare_analytics(db=db)
    assert analytics.total_facilities >= 1
    assert analytics.total_beds_available >= 0
    assert analytics.bed_utilization_percentage >= 0.0
    assert analytics.status.value == "AVAILABLE"
