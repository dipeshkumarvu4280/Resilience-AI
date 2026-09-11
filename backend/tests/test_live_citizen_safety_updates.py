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
    MonitoringEventType,
    EventSourceType,
    SafetyNotificationType,
)
from app.models.safety_guidance import (
    PushSubscriptionCreate,
    SafetyGuidanceReviewRequest,
)
from app.services.agents.adapters.safety_guidance_agent import SafetyGuidanceAgent
from app.services.monitoring.monitoring_service import MonitoringService
from app.services.routing_service import RoutingService
from app.services.notification.web_push_service import WebPushService


from unittest.mock import patch, AsyncMock
from app.services.places_service import PlacesService


@pytest.fixture(autouse=True)
async def clean_safety_guidance_collections():
    test_db = db_manager.db
    if test_db is not None:
        await test_db["citizen_safety_guidance"].delete_many({})
        await test_db["push_subscriptions"].delete_many({})
        await test_db["push_deliveries"].delete_many({})
        await test_db["citizen_reports"].delete_many({})
        await test_db["resources"].delete_many({})
        await test_db["situations"].delete_many({})
        await test_db["monitoring_events"].delete_many({})
        await test_db["change_impacts"].delete_many({})

    async def mock_updates_router(o_lat, o_lng, d_lat, d_lng):
        mid_lat = (o_lat + d_lat) / 2.0
        mid_lng = (o_lng + d_lng) / 2.0
        return [
            [o_lat, o_lng],
            [mid_lat, mid_lng],
            [d_lat, d_lng],
        ], 3.5, 7.0, "Google Directions API"

    RoutingService.set_custom_router(mock_updates_router)
    with patch.object(PlacesService, "discover_nearby_facilities", new_callable=AsyncMock) as mock_places:
        mock_places.return_value = []
        try:
            yield
        finally:
            RoutingService.set_custom_router(None)



@pytest.mark.anyio
async def test_dynamic_unaffected_event_produces_zero_guidance_mutation():
    """Verify that an operational event far away from the citizen corridor causes NO guidance mutations or notifications."""
    test_db = db_manager.db
    now = datetime.now(timezone.utc)

    # 1. Setup Shelter & Report at Amaravati (16.24, 80.64)
    await test_db["resources"].insert_one({
        "resource_id": "RES-SHL-001",
        "name": "Amaravati Central High School",
        "type": ResourceType.SHELTER.value,
        "status": ResourceStatus.AVAILABLE.value,
        "location": {"latitude": 16.2600, "longitude": 80.6600, "address": "Civic Center"},
        "capacity": {"total": 400, "available": 250, "allocated": 150, "unit": "PERSONS"},
        "created_at": now,
        "updated_at": now,
    })

    await test_db["citizen_reports"].insert_one({
        "report_id": "CR-FLOOD-001",
        "citizen_name": "Lakshmi Rao",
        "citizen_phone": "9876543210",
        "emergency_type": "Flood",
        "citizen_impact_level": "MEDIUM",
        "description": "Street water level 1 foot.",
        "location": {"latitude": 16.2400, "longitude": 80.6400, "address": "Station Road"},
        "status": "SUBMITTED",
        "created_at": now,
        "updated_at": now,
    })

    guidance_v1 = await SafetyGuidanceAgent.generate_safety_guidance(report_id="CR-FLOOD-001", db=test_db)
    assert guidance_v1.version == 1
    assert guidance_v1.status == "ACTIVE"

    # 2. Trigger an operational change 35km away in Guntur South (15.95, 80.45)
    far_event = await MonitoringService.record_change_event(
        event_type=MonitoringEventType.RESOURCE_STATUS_CHANGED,
        source_type=EventSourceType.RESOURCE_INVENTORY,
        source_id="RES-FAR-999",
        previous_state={"status": "AVAILABLE"},
        new_state={"status": "UNAVAILABLE", "location": {"latitude": 15.9500, "longitude": 80.4500}},
        location={"latitude": 15.9500, "longitude": 80.4500},
        db=test_db,
    )
    assert far_event is not None

    # Verify guidance was NOT mutated
    all_guidances = await test_db["citizen_safety_guidance"].find({"report_id": "CR-FLOOD-001"}).to_list(10)
    assert len(all_guidances) == 1
    assert all_guidances[0]["version"] == 1
    assert all_guidances[0]["status"] == "ACTIVE"

    # Verify zero push notifications sent
    deliveries_count = await test_db["push_deliveries"].count_documents({})
    assert deliveries_count == 0


@pytest.mark.anyio
async def test_dynamic_route_corridor_reevaluation_on_road_block():
    """Verify that a road block intersecting the citizen transit corridor automatically triggers route recalculation & Guidance V2."""
    test_db = db_manager.db
    now = datetime.now(timezone.utc)

    # 1. Setup Shelter & Report
    await test_db["resources"].insert_one({
        "resource_id": "RES-SHL-001",
        "name": "Amaravati Central Shelter",
        "type": ResourceType.SHELTER.value,
        "status": ResourceStatus.AVAILABLE.value,
        "location": {"latitude": 16.2600, "longitude": 80.6600, "address": "Civic Center"},
        "capacity": {"total": 400, "available": 250, "allocated": 150, "unit": "PERSONS"},
        "created_at": now,
        "updated_at": now,
    })

    await test_db["citizen_reports"].insert_one({
        "report_id": "CR-FLOOD-002",
        "citizen_name": "Ravi Teja",
        "citizen_phone": "9876543211",
        "emergency_type": "Flood",
        "citizen_impact_level": "HIGH",
        "description": "Water entering porch.",
        "location": {"latitude": 16.2400, "longitude": 80.6400, "address": "South Ring"},
        "status": "SUBMITTED",
        "created_at": now,
        "updated_at": now,
    })

    # Subscribe push endpoint
    await test_db["push_subscriptions"].insert_one({
        "subscription_id": "SUB-TEST-ROAD-BLOCK",
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-block-token",
        "keys": {
            "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9AcUbVJaBoeWOMXwhpyCnE",
            "auth": "tBHItJI5svbpez7KI4CCXg",
        },
        "status": "ACTIVE",
        "report_ids": ["CR-FLOOD-002"],
        "created_at": now,
        "updated_at": now,
    })

    guidance_v1 = await SafetyGuidanceAgent.generate_safety_guidance(report_id="CR-FLOOD-002", db=test_db)
    assert guidance_v1.version == 1

    # 2. Field verification event: ROUTE_OBSTRUCTION_CHANGED near corridor midpoint (16.2500, 80.6500)
    from unittest.mock import patch
    with patch("app.services.notification.web_push_service.WebPushService.send_web_push", return_value=True):
        block_event = await MonitoringService.record_change_event(
            event_type=MonitoringEventType.ROUTE_OBSTRUCTION_CHANGED,
            source_type=EventSourceType.ROUTE_NETWORK,
            source_id="ROAD-MIDPOINT-SURGE",
            previous_state={"status": "PASSABLE"},
            new_state={"status": "BLOCKED", "hazard": "Culvert collapse", "location": {"latitude": 16.2500, "longitude": 80.6500}},
            location={"latitude": 16.2500, "longitude": 80.6500},
            db=test_db,
        )
    assert block_event is not None

    # 3. Verify V1 is now SUPERSEDED and V2 is created
    v1_doc = await test_db["citizen_safety_guidance"].find_one({"guidance_id": guidance_v1.guidance_id})
    assert v1_doc["status"] == "SUPERSEDED"
    assert v1_doc["superseded_by_guidance_id"] is not None

    v2_doc = await test_db["citizen_safety_guidance"].find_one({"status": "ACTIVE", "report_id": "CR-FLOOD-002"})
    assert v2_doc is not None
    assert v2_doc["version"] == 2
    assert v2_doc["supersedes_guidance_id"] == guidance_v1.guidance_id
    assert "road blockage" in v2_doc["change_reason"].lower() or "compromised" in v2_doc["change_reason"].lower()
    assert len(v2_doc["history"]) == 1
    assert v2_doc["history"][0]["guidance_id"] == guidance_v1.guidance_id

    # 4. Verify push delivery record was created idempotently
    deliveries = await test_db["push_deliveries"].find({"event_id": block_event.event_id}).to_list(10)
    assert len(deliveries) == 1
    assert deliveries[0]["notification_type"] == SafetyNotificationType.ROUTE_UPDATED.value
    assert deliveries[0]["guidance_version"] == 2


@pytest.mark.anyio
async def test_dynamic_destination_reevaluation_on_shelter_closure():
    """Verify that when a designated shelter becomes unavailable, the agent selects the next closest operational facility."""
    test_db = db_manager.db
    now = datetime.now(timezone.utc)

    # Insert two shelters: Primary (closer) and Secondary (further)
    await test_db["resources"].insert_one({
        "resource_id": "RES-SHL-PRIMARY",
        "name": "Primary Community Hall",
        "type": ResourceType.SHELTER.value,
        "status": ResourceStatus.AVAILABLE.value,
        "location": {"latitude": 16.2500, "longitude": 80.6500, "address": "Hall 1"},
        "capacity": {"total": 200, "available": 100, "allocated": 100, "unit": "PERSONS"},
        "created_at": now,
        "updated_at": now,
    })

    await test_db["resources"].insert_one({
        "resource_id": "RES-SHL-SECONDARY",
        "name": "Secondary College Campus",
        "type": ResourceType.SHELTER.value,
        "status": ResourceStatus.AVAILABLE.value,
        "location": {"latitude": 16.2700, "longitude": 80.6700, "address": "College Block A"},
        "capacity": {"total": 500, "available": 350, "allocated": 150, "unit": "PERSONS"},
        "created_at": now,
        "updated_at": now,
    })

    await test_db["citizen_reports"].insert_one({
        "report_id": "CR-FLOOD-003",
        "citizen_name": "Anita Roy",
        "citizen_phone": "9876543212",
        "emergency_type": "Flood",
        "citizen_impact_level": "MEDIUM",
        "description": "Ground floor flooded.",
        "location": {"latitude": 16.2400, "longitude": 80.6400, "address": "Ward 8"},
        "status": "SUBMITTED",
        "created_at": now,
        "updated_at": now,
    })

    guidance_v1 = await SafetyGuidanceAgent.generate_safety_guidance(report_id="CR-FLOOD-003", db=test_db)
    assert guidance_v1.recommended_destination.destination_id == "RES-SHL-PRIMARY"

    # Primary shelter becomes UNAVAILABLE (e.g. structural damage or capacity full)
    await test_db["resources"].update_one(
        {"resource_id": "RES-SHL-PRIMARY"},
        {"$set": {"status": "UNAVAILABLE", "quantity_available": 0}}
    )

    shelter_event = await MonitoringService.record_change_event(
        event_type=MonitoringEventType.SHELTER_CAPACITY_CHANGED,
        source_type=EventSourceType.RESOURCE_INVENTORY,
        source_id="RES-SHL-PRIMARY",
        previous_state={"status": "AVAILABLE", "quantity_available": 100},
        new_state={"status": "UNAVAILABLE", "quantity_available": 0, "location": {"latitude": 16.2500, "longitude": 80.6500}},
        location={"latitude": 16.2500, "longitude": 80.6500},
        db=test_db,
    )
    assert shelter_event is not None

    # Guidance V2 must now point to Secondary College Campus
    v2_doc = await test_db["citizen_safety_guidance"].find_one({"status": "ACTIVE", "report_id": "CR-FLOOD-003"})
    assert v2_doc is not None
    assert v2_doc["version"] == 2
    assert v2_doc["recommended_destination"]["destination_id"] == "RES-SHL-SECONDARY"
    assert v2_doc["recommended_destination"]["destination_name"] == "Secondary College Campus"


@pytest.mark.anyio
async def test_superseded_token_redirects_to_latest_active_guidance():
    """Verify GET /api/v1/citizen/safety-guidance/{old_token} automatically returns the latest active version."""
    test_db = db_manager.db
    now = datetime.now(timezone.utc)

    await test_db["resources"].insert_one({
        "resource_id": "RES-SHL-001",
        "name": "Civic Shelter",
        "type": ResourceType.SHELTER.value,
        "status": ResourceStatus.AVAILABLE.value,
        "location": {"latitude": 16.2600, "longitude": 80.6600},
        "capacity": {"total": 300, "available": 200, "allocated": 100, "unit": "PERSONS"},
        "created_at": now,
        "updated_at": now,
    })

    await test_db["citizen_reports"].insert_one({
        "report_id": "CR-SUPER-001",
        "citizen_name": "Manoj Kumar",
        "citizen_phone": "9876543213",
        "emergency_type": "Flood",
        "citizen_impact_level": "HIGH",
        "description": "Flood water entering warehouse rapidly.",
        "location": {"latitude": 16.2400, "longitude": 80.6400},
        "status": "SUBMITTED",
        "created_at": now,
        "updated_at": now,
    })

    guidance_v1 = await SafetyGuidanceAgent.generate_safety_guidance(report_id="CR-SUPER-001", db=test_db)
    old_token = guidance_v1.secure_access_token

    # Trigger update
    await MonitoringService.record_change_event(
        event_type=MonitoringEventType.ROUTE_OBSTRUCTION_CHANGED,
        source_type=EventSourceType.ROUTE_NETWORK,
        source_id="ROAD-BLK-001",
        previous_state={"status": "OPEN"},
        new_state={"status": "BLOCKED", "location": {"latitude": 16.2450, "longitude": 80.6450}},
        location={"latitude": 16.2450, "longitude": 80.6450},
        db=test_db,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Request with old V1 token
        res = await client.get(f"/api/v1/citizen/safety-guidance/{old_token}")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["guidance"]["version"] == 2
        assert data["latest_active_token"] is not None
        assert "Version 2" in data["message"]


@pytest.mark.anyio
async def test_guidance_history_endpoint():
    """Verify GET /api/v1/citizen/safety-guidance/{token}/history returns complete immutable audit trail."""
    test_db = db_manager.db
    now = datetime.now(timezone.utc)

    await test_db["resources"].insert_one({
        "resource_id": "RES-SHL-HIST",
        "name": "Shelter A",
        "type": ResourceType.SHELTER.value,
        "status": ResourceStatus.AVAILABLE.value,
        "location": {"latitude": 16.2600, "longitude": 80.6600},
        "capacity": {"total": 300, "available": 200, "allocated": 100, "unit": "PERSONS"},
        "created_at": now,
        "updated_at": now,
    })

    await test_db["citizen_reports"].insert_one({
        "report_id": "CR-HIST-001",
        "citizen_name": "Sunita Verma",
        "citizen_phone": "9876543214",
        "emergency_type": "Flood",
        "citizen_impact_level": "MEDIUM",
        "description": "Water logging in colony.",
        "location": {"latitude": 16.2400, "longitude": 80.6400},
        "status": "SUBMITTED",
        "created_at": now,
        "updated_at": now,
    })

    guidance_v1 = await SafetyGuidanceAgent.generate_safety_guidance(report_id="CR-HIST-001", db=test_db)

    # Trigger update to create V2
    await MonitoringService.record_change_event(
        event_type=MonitoringEventType.ROUTE_OBSTRUCTION_CHANGED,
        source_type=EventSourceType.ROUTE_NETWORK,
        source_id="ROAD-HIST-001",
        previous_state={"status": "OPEN"},
        new_state={"status": "BLOCKED", "location": {"latitude": 16.2450, "longitude": 80.6450}},
        location={"latitude": 16.2450, "longitude": 80.6450},
        db=test_db,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"/api/v1/citizen/safety-guidance/{guidance_v1.secure_access_token}/history")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["total_versions"] == 2
        assert data["versions"][0]["version"] == 1
        assert data["versions"][0]["status"] == "SUPERSEDED"
        assert data["versions"][1]["version"] == 2
        assert data["versions"][1]["status"] == "ACTIVE"


@pytest.mark.anyio
async def test_push_notification_idempotency_prevents_duplicate_deliveries():
    """Verify that re-evaluating or duplicate events do not send duplicate push notifications."""
    test_db = db_manager.db
    now = datetime.now(timezone.utc)

    # Insert Guidance
    guidance = await SafetyGuidanceAgent.generate_safety_guidance_for_test(
        report_id="CR-IDEM-001",
        emergency_type="Flood",
        db=test_db,
    ) if hasattr(SafetyGuidanceAgent, "generate_safety_guidance_for_test") else None

    if guidance is None:
        await test_db["resources"].insert_one({
            "resource_id": "RES-SHL-IDEM",
            "name": "Idem Shelter",
            "type": ResourceType.SHELTER.value,
            "status": ResourceStatus.AVAILABLE.value,
            "location": {"latitude": 16.2600, "longitude": 80.6600},
            "capacity": {"total": 300, "available": 200, "allocated": 100, "unit": "PERSONS"},
            "created_at": now,
            "updated_at": now,
        })
        await test_db["citizen_reports"].insert_one({
            "report_id": "CR-IDEM-001",
            "citizen_name": "Test User",
            "citizen_phone": "9876543215",
            "emergency_type": "Flood",
            "citizen_impact_level": "LOW",
            "description": "Testing idempotency.",
            "location": {"latitude": 16.2400, "longitude": 80.6400},
            "status": "SUBMITTED",
            "created_at": now,
            "updated_at": now,
        })
        guidance = await SafetyGuidanceAgent.generate_safety_guidance(report_id="CR-IDEM-001", db=test_db)

    # Add push subscription
    await test_db["push_subscriptions"].insert_one({
        "subscription_id": "SUB-IDEM-TEST",
        "endpoint": "https://fcm.googleapis.com/fcm/send/idem-token-999",
        "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9AcUbVJaBoeWOMXwhpyCnE",
        "auth": "tBHItJI5svbpez7KI4CCXg",
        "status": "ACTIVE",
        "report_ids": ["CR-IDEM-001"],
        "created_at": now,
        "updated_at": now,
    })

    from unittest.mock import patch
    with patch("app.services.notification.web_push_service.WebPushService.send_web_push", return_value=True):
        # Dispatch 1
        sent_1 = await WebPushService.notify_citizen_guidance_update(
            guidance,
            notification_type=SafetyNotificationType.ROUTE_UPDATED,
            event_id="EVT-IDEM-001",
            db=test_db,
        )
        assert sent_1 == 1

        # Dispatch 2 with same event_id, recipient, type, version -> Should be suppressed (0 sent)
        sent_2 = await WebPushService.notify_citizen_guidance_update(
            guidance,
            notification_type=SafetyNotificationType.ROUTE_UPDATED,
            event_id="EVT-IDEM-001",
            db=test_db,
        )
        assert sent_2 == 0

    # Total in push_deliveries collection must remain 1
    deliveries_count = await test_db["push_deliveries"].count_documents({"event_id": "EVT-IDEM-001"})
    assert deliveries_count == 1
