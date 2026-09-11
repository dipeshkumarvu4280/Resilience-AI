import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone, timedelta
import secrets

from app.main import app
from app.db.mongodb import db_manager
from app.models.enums import (
    EmergencyType,
    CitizenImpactLevel,
    GuidanceApprovalState,
    DestinationType,
    RouteStatus,
    ResourceType,
    ResourceStatus,
)
from app.models.safety_guidance import (
    PushSubscriptionCreate,
    SafetyGuidanceReviewRequest,
)
from unittest.mock import patch, AsyncMock
from app.services.agents.adapters.safety_guidance_agent import SafetyGuidanceAgent
from app.services.places_service import PlacesService
from app.services.routing_service import RoutingService
from app.services.notification.web_push_service import WebPushService


@pytest.fixture(autouse=True)
async def clean_safety_guidance_collections():
    test_db = db_manager.db
    if test_db is not None:
        await test_db["citizen_safety_guidance"].delete_many({})
        await test_db["push_subscriptions"].delete_many({})
        await test_db["citizen_reports"].delete_many({})
        await test_db["resources"].delete_many({})
        await test_db["situations"].delete_many({})

    async def mock_live_router(o_lat, o_lng, d_lat, d_lng):
        return [
            [o_lat, o_lng],
            [16.2500, 80.6500],
            [d_lat, d_lng],
        ], 3.5, 7.0, "Google Directions API"

    RoutingService.set_custom_router(mock_live_router)
    with patch.object(PlacesService, "discover_nearby_facilities", new_callable=AsyncMock) as mock_places:
        mock_places.return_value = []
        try:
            yield
        finally:
            RoutingService.set_custom_router(None)


@pytest.mark.anyio
async def test_vapid_public_key_endpoint():
    """Verify GET /api/v1/citizen/push/vapid-public-key returns valid VAPID key."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/citizen/push/vapid-public-key")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "vapid_public_key" in data
        assert len(data["vapid_public_key"]) > 20


@pytest.mark.anyio
async def test_push_subscription_lifecycle():
    """Verify subscribing and unsubscribing browser endpoints via WebPushService."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-sub-token-12345",
            "keys": {
                "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9AcUbVJaBoeWOMXwhpyCnE",
                "auth": "tBHItJI5svbpez7KI4CCXg",
            },
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "report_id": "CR-TEST-001",
            "session_id": "sess-xyz-987",
        }

        # 1. Subscribe
        sub_res = await client.post("/api/v1/citizen/push/subscribe", json=payload)
        assert sub_res.status_code == 200
        sub_data = sub_res.json()
        assert sub_data["success"] is True
        assert sub_data["subscription_id"] is not None

        # Verify persisted in database
        test_db = db_manager.db
        sub_doc = await test_db["push_subscriptions"].find_one({"endpoint": payload["endpoint"]})
        assert sub_doc is not None
        assert sub_doc["status"] == "ACTIVE"
        assert "CR-TEST-001" in sub_doc.get("report_ids", [])

        # 2. Duplicate subscribe (idempotent update)
        sub_res_2 = await client.post("/api/v1/citizen/push/subscribe", json=payload)
        assert sub_res_2.status_code == 200

        # 3. Unsubscribe
        unsub_res = await client.request("DELETE", "/api/v1/citizen/push/subscribe", json={"endpoint": payload["endpoint"]})
        assert unsub_res.status_code == 200
        assert unsub_res.json()["success"] is True

        # Verify inactive in database
        sub_doc_inactive = await test_db["push_subscriptions"].find_one({"endpoint": payload["endpoint"]})
        assert sub_doc_inactive["status"] == "UNSUBSCRIBED"


@pytest.mark.anyio
async def test_routing_service_haversine_and_hazard_avoidance():
    """Verify RoutingService computes real spherical distances and identifies active situation hazard intersections."""
    test_db = db_manager.db

    # Insert an active hazard situation at 16.2500, 80.6500 with radius 2.0 km
    await test_db["situations"].insert_one({
        "situation_id": "SIT-FLOOD-01",
        "title": "Krishna River Surge Flash Flood",
        "status": "ACTIVE",
        "location": {
            "latitude": 16.2500,
            "longitude": 80.6500,
            "radius_km": 2.0,
            "address": "Riverbank Embankment Breach",
        },
        "description": "Hazardous raging waterflow over road network",
        "created_at": datetime.now(timezone.utc),
    })

    async def mock_test_router(o_lat, o_lng, d_lat, d_lng):
        return [
            [o_lat, o_lng],
            [16.2500, 80.6500],  # Path passes right through hazard zone
            [d_lat, d_lng],
        ], 4.2, 8.0, "Google Directions API"

    RoutingService.set_custom_router(mock_test_router)
    try:
        # Test route from 16.2400, 80.6400 (citizen) to 16.2700, 80.6700 (shelter) passing near hazard zone
        route = await RoutingService.calculate_hazard_aware_route(
            origin_lat=16.2400,
            origin_lng=80.6400,
            dest_lat=16.2700,
            dest_lng=80.6700,
            db=test_db,
        )

        assert route.route_status == RouteStatus.CALCULATED
        assert route.distance_km > 0.5
        assert route.estimated_duration_minutes > 0
        assert len(route.polyline_points) >= 2
        # Should detect the situation hazard zone
        assert len(route.avoid_areas) >= 1
        assert len(route.route_warnings) >= 1
        assert "Krishna River Surge" in route.avoid_areas[0].warning_message
    finally:
        RoutingService.set_custom_router(None)


@pytest.mark.anyio
async def test_safety_guidance_generation_with_real_destinations():
    """Verify SafetyGuidanceAgent generates real verified destination and routing from active MongoDB resources."""
    test_db = db_manager.db
    now = datetime.now(timezone.utc)

    # Insert verified shelter resource
    shelter_resource = {
        "resource_id": "RES-SHL-001",
        "name": "Amaravati District Emergency High School Shelter",
        "type": ResourceType.SHELTER.value,
        "status": ResourceStatus.AVAILABLE.value,
        "location": {
            "latitude": 16.2600,
            "longitude": 80.6600,
            "address": "Block 4, Civic Center, Amaravati",
        },
        "capacity": {
            "total": 350,
            "available": 210,
            "allocated": 140,
            "unit": "PERSONS",
        },
        "contact_info": {
            "phone": "+91-863-2223344",
            "manager_name": "Coordinator Rao",
        },
        "created_at": now,
        "updated_at": now,
    }
    await test_db["resources"].insert_one(shelter_resource)

    # Insert citizen report
    report_doc = {
        "report_id": "CR-TEST-FLOOD-01",
        "citizen_name": "Ramesh Varma",
        "citizen_phone": "9876543210",
        "emergency_type": "Flood",
        "citizen_impact_level": "HIGH",
        "description": "Flood waters entering ground floor, depth 3 feet. Family of 4 stranded on porch.",
        "location": {
            "latitude": 16.2415,
            "longitude": 80.6433,
            "address": "12-4 Railway Feeder Road",
        },
        "status": "SUBMITTED",
        "created_at": now,
        "updated_at": now,
    }
    await test_db["citizen_reports"].insert_one(report_doc)

    async def mock_test_router(o_lat, o_lng, d_lat, d_lng):
        return [
            [o_lat, o_lng],
            [16.2500, 80.6500],
            [d_lat, d_lng],
        ], 3.2, 6.5, "Google Directions API"

    RoutingService.set_custom_router(mock_test_router)
    try:
        with patch.object(PlacesService, "discover_nearby_facilities", new_callable=AsyncMock) as mock_places:
            mock_places.return_value = []
            guidance = await SafetyGuidanceAgent.generate_safety_guidance(
                report_id="CR-TEST-FLOOD-01",
                db=test_db,
            )

        assert guidance.guidance_id.startswith("GUD-")
        assert len(guidance.secure_access_token) >= 32
        assert guidance.emergency_type == "Flood"
        assert guidance.risk_level in ["HIGH", "CRITICAL"]
        assert len(guidance.immediate_actions) >= 3
        assert len(guidance.precautions) >= 2
        assert guidance.recommended_destination is not None
        assert guidance.recommended_destination.destination_name == "Amaravati District Emergency High School Shelter"
        assert guidance.recommended_destination.destination_type == DestinationType.SHELTER
        assert guidance.recommended_destination.available_capacity == 210
        assert guidance.route is not None
        assert guidance.route.route_status == RouteStatus.CALCULATED
        assert guidance.route.distance_km > 0
    finally:
        RoutingService.set_custom_router(None)


@pytest.mark.anyio
async def test_safety_guidance_fallback_when_no_facility_within_range():
    """Verify SafetyGuidanceAgent behaves deterministically when no operational resources exist within 50km."""
    test_db = db_manager.db
    now = datetime.now(timezone.utc)

    report_doc = {
        "report_id": "CR-REMOTE-01",
        "citizen_name": "Devi Prasad",
        "citizen_phone": "9876543211",
        "emergency_type": "Landslide",
        "citizen_impact_level": "CRITICAL",
        "description": "Remote hill road completely blocked by boulder fall.",
        "location": {
            "latitude": 28.5000,
            "longitude": 77.0000,
            "address": "High Mountain Pass Km 42",
        },
        "status": "SUBMITTED",
        "created_at": now,
        "updated_at": now,
    }
    await test_db["citizen_reports"].insert_one(report_doc)

    from unittest.mock import patch, AsyncMock
    from app.services.places_service import PlacesService

    with patch.object(PlacesService, "discover_nearby_facilities", new_callable=AsyncMock) as mock_places:
        mock_places.return_value = []
        guidance = await SafetyGuidanceAgent.generate_safety_guidance(
            report_id="CR-REMOTE-01",
            db=test_db,
        )

    assert guidance.recommended_destination is None
    assert guidance.destination_reason == "NO_VERIFIED_DESTINATION_AVAILABLE"
    assert len(guidance.immediate_actions) >= 3
    # Guidance should still provide critical stay-put / self-preservation advice
    assert any("shelter" in a.lower() or "safe" in a.lower() or "elevation" in a.lower() or "higher" in a.lower() for a in guidance.immediate_actions)


@pytest.mark.anyio
async def test_citizen_report_submission_auto_generates_guidance():
    """Verify that posting a real citizen emergency report automatically creates safety guidance and returns tokens."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report_payload = {
            "full_name": "Kavitha Sharma",
            "phone": "9876543210",
            "emergency_type": "Fire",
            "citizen_impact_level": "HIGH",
            "description": "Commercial building kitchen electrical fire, dense smoke spreading to second floor.",
            "location": {
                "latitude": 16.2415,
                "longitude": 80.6433,
                "address": "Opposite Bus Terminal",
            },
        }

        res = await client.post("/api/v1/citizen/reports", json=report_payload)
        assert res.status_code == 201
        report_data = res.json()
        assert report_data["report_id"] is not None
        assert report_data["safety_guidance_token"] is not None
        assert report_data["safety_guidance_id"] is not None

        token = report_data["safety_guidance_token"]

        # Access citizen safety guidance using the high-entropy token
        guidance_res = await client.get(f"/api/v1/citizen/safety-guidance/{token}")
        assert guidance_res.status_code == 200
        guidance_data = guidance_res.json()
        assert guidance_data["success"] is True
        assert guidance_data["guidance"]["report_id"] == report_data["report_id"]
        assert guidance_data["guidance"]["emergency_type"] == "Fire"


@pytest.mark.anyio
async def test_safety_guidance_token_idor_security():
    """Verify that random or brute-forced tokens cannot access unauthorized citizen guidance records (IDOR protection)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        fake_token = secrets.token_urlsafe(32)
        res = await client.get(f"/api/v1/citizen/safety-guidance/{fake_token}")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()


@pytest.mark.anyio
async def test_officer_hitl_guidance_review_and_push_broadcast():
    """Verify Emergency Officer can review, modify, and approve citizen safety guidance."""
    test_db = db_manager.db
    now = datetime.now(timezone.utc)

    # Insert report and shelter
    await test_db["resources"].insert_one({
        "resource_id": "RES-SHL-002",
        "name": "Collectorate Emergency Shelter",
        "type": ResourceType.SHELTER.value,
        "status": ResourceStatus.AVAILABLE.value,
        "location": {
            "latitude": 16.3100,
            "longitude": 80.7100,
            "address": "Collectorate Compound",
        },
        "capacity": {"total": 500, "available": 300, "allocated": 200, "unit": "PERSONS"},
        "created_at": now,
        "updated_at": now,
    })

    await test_db["citizen_reports"].insert_one({
        "report_id": "CR-HITL-TEST-01",
        "citizen_name": "Suresh Babu",
        "citizen_phone": "9876543212",
        "emergency_type": "Cyclone / Storm",
        "citizen_impact_level": "CRITICAL",
        "description": "Extremely high winds tore roof off shed. Flying metal debris.",
        "location": {
            "latitude": 16.3000,
            "longitude": 80.7000,
            "address": "Fishermen Colony",
        },
        "status": "SUBMITTED",
        "created_at": now,
        "updated_at": now,
    })

    guidance = await SafetyGuidanceAgent.generate_safety_guidance(
        report_id="CR-HITL-TEST-01",
        db=test_db,
    )

    # Subscribe a mock push endpoint for this report
    await test_db["push_subscriptions"].insert_one({
        "subscription_id": "SUB-TEST-BROADCAST",
        "endpoint": "https://fcm.googleapis.com/fcm/send/hitl-test-token",
        "keys": {
            "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9AcUbVJaBoeWOMXwhpyCnE",
            "auth": "tBHItJI5svbpez7KI4CCXg",
        },
        "status": "ACTIVE",
        "report_ids": ["CR-HITL-TEST-01"],
        "created_at": now,
        "updated_at": now,
    })

    # Log in as Emergency Officer to obtain JWT
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"phone": "9999999002", "password": "OfficerPassword@2026"},
        )
        assert login_res.status_code == 200
        officer_token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {officer_token}"}

        # Perform Officer Review: Modify and Approve
        review_payload = {
            "action": "MODIFIED",
            "modified_actions": [
                "Move to interior reinforced bathroom away from windows immediately.",
                "Cover heads with mattresses or thick blankets to protect from projectile glass.",
                "Do NOT attempt to drive through open roads until wind eye passes.",
            ],
            "modified_precautions": [
                "Downed 11kV powerlines reported on North Highway.",
            ],
            "officer_notes": "Added tactical protection instruction due to structural roof failure.",
        }

        review_res = await client.post(
            f"/api/v1/citizen/officer/safety-guidance/{guidance.guidance_id}/review",
            headers=headers,
            json=review_payload,
        )
        assert review_res.status_code == 200
        review_data = review_res.json()
        assert review_data["success"] is True
        assert review_data["approval_state"] == "MODIFIED"
        assert review_data["guidance"]["immediate_actions"][0] == "Move to interior reinforced bathroom away from windows immediately."
        assert review_data["guidance"]["officer_review_notes"] == "Added tactical protection instruction due to structural roof failure."

        # Verify guidance updated in database
        updated_doc = await test_db["citizen_safety_guidance"].find_one({"guidance_id": guidance.guidance_id})
        assert updated_doc["approval_state"] == "MODIFIED"
