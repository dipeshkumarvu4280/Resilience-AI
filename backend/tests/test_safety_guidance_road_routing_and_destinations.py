import pytest
from datetime import datetime, timezone

from app.db.mongodb import db_manager
from app.models.enums import (
    DestinationType,
    RouteStatus,
    ResourceStatus,
    SeverityLevel,
)
from app.models.safety_guidance import VerifiedDestination, RouteDetails
from app.services.routing_service import RoutingService, decode_google_polyline
from app.services.agents.adapters.safety_guidance_agent import SafetyGuidanceAgent


@pytest.fixture(autouse=True)
async def clean_safety_guidance_collections():
    test_db = db_manager.db
    if test_db is not None:
        await test_db["citizen_safety_guidance"].delete_many({})
        await test_db["push_subscriptions"].delete_many({})
        await test_db["citizen_reports"].delete_many({})
        await test_db["resources"].delete_many({})
        await test_db["healthcare_facilities"].delete_many({})
        await test_db["situations"].delete_many({})
    yield


def test_google_polyline_decoder():
    """Test standard Google encoded polyline decoding."""
    # Polyline for points: (38.5, -120.2), (40.7, -120.95), (43.252, -126.453)
    encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
    decoded = decode_google_polyline(encoded)
    assert len(decoded) == 3
    assert pytest.approx(decoded[0][0], 0.0001) == 38.5
    assert pytest.approx(decoded[0][1], 0.0001) == -120.2
    assert pytest.approx(decoded[1][0], 0.0001) == 40.7
    assert pytest.approx(decoded[1][1], 0.0001) == -120.95
    assert pytest.approx(decoded[2][0], 0.0001) == 43.252
    assert pytest.approx(decoded[2][1], 0.0001) == -126.453


def test_routing_service_has_zero_synthetic_corridor_interpolation():
    """Verify mathematical straight-line coordinate interpolation was completely eliminated."""
    assert not hasattr(RoutingService, "_generate_corridor_waypoints")


@pytest.mark.anyio
async def test_routing_service_road_routing_with_custom_router():
    """Verify RoutingService executes road-network routing and handles unavailable route without straight lines."""
    db = db_manager.db

    # 1. Successful Road Routing fixture
    async def mock_road_router(o_lat, o_lng, d_lat, d_lng):
        return [
            (o_lat, o_lng),
            (16.5100, 80.6500), # Road waypoint 1
            (16.5120, 80.6530), # Road waypoint 2
            (d_lat, d_lng),
        ], 3.8, 8.5, "Google Directions API"

    RoutingService.set_custom_router(mock_road_router)
    try:
        route = await RoutingService.calculate_hazard_aware_route(
            origin_lat=16.5062,
            origin_lng=80.6480,
            dest_lat=16.5150,
            dest_lng=80.6550,
            db=db,
        )
        assert route.route_status == RouteStatus.CALCULATED
        assert len(route.polyline_points) == 4
        assert route.distance_km == 3.8
        assert route.estimated_duration_minutes == 8.5
        assert "Google" in route.provider
    finally:
        RoutingService.set_custom_router(None)

    # 2. Unroutable / Road Unavailable fixture
    async def mock_unroutable_router(o_lat, o_lng, d_lat, d_lng):
        return None, 0.0, 0.0, "Google Routes (Unavailable)"

    RoutingService.set_custom_router(mock_unroutable_router)
    try:
        route_unavail = await RoutingService.calculate_hazard_aware_route(
            origin_lat=16.5062,
            origin_lng=80.6480,
            dest_lat=16.5150,
            dest_lng=80.6550,
            db=db,
        )
        assert route_unavail.route_status == RouteStatus.ROUTE_UNAVAILABLE
        assert route_unavail.polyline_points == [] # Must NOT have fake straight-line points
        assert any("unavailable" in w.lower() for w in route_unavail.route_warnings)
    finally:
        RoutingService.set_custom_router(None)


@pytest.mark.anyio
async def test_safety_guidance_situation_aware_destination_selection():
    """Verify situation-aware destination selection routes medical to healthcare, fire to fire station, etc."""
    db = db_manager.db
    if db is None:
        pytest.skip("Database not connected")

    # Seed genuine operational resources
    await db["healthcare_facilities"].insert_one({
        "facility_id": "HOSP-001",
        "name": "Vijayawada Government General Hospital",
        "status": "OPERATIONAL",
        "location": {"latitude": 16.5100, "longitude": 80.6500, "address": "Hospital Road"},
        "capacity": {"total_beds": 500, "available_beds": 42},
        "phone_number": "+91-866-2570000",
    })

    await db["resources"].insert_one({
        "resource_id": "POL-001",
        "name": "Central Sector Police Station",
        "resource_type": "POLICE",
        "status": "AVAILABLE",
        "location": {"latitude": 16.5080, "longitude": 80.6490, "address": "Police Line Road"},
        "capacity": {"total": 50, "available": 20},
        "contact_info": {"phone": "+91-866-2571111"},
    })

    await db["resources"].insert_one({
        "resource_id": "FIRE-001",
        "name": "District Fire Station",
        "resource_type": "FIRE_STATION",
        "status": "AVAILABLE",
        "location": {"latitude": 16.5120, "longitude": 80.6520, "address": "Fire Station Road"},
        "capacity": {"total": 30, "available": 15},
        "contact_info": {"phone": "+91-866-2572222"},
    })

    await db["resources"].insert_one({
        "resource_id": "SHELTER-001",
        "name": "Community Cyclone Relief Shelter",
        "resource_type": "SHELTER",
        "status": "AVAILABLE",
        "location": {"latitude": 16.5150, "longitude": 80.6550, "address": "High Ground School"},
        "capacity": {"total": 200, "available": 120},
        "contact_info": {"phone": "+91-866-2573333"},
    })

    origin_lat, origin_lng = 16.5062, 80.6480

    from unittest.mock import patch, AsyncMock
    from app.services.places_service import PlacesService

    with patch.object(PlacesService, "discover_nearby_facilities", new_callable=AsyncMock) as mock_places:
        mock_places.return_value = []

        # 1. Medical Emergency -> Healthcare
        med_dest, _, _ = await SafetyGuidanceAgent._find_verified_destination(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            emergency_type="Medical Emergency",
            description="Patient has severe fracture and bleeding from head injury",
            db=db,
        )
        assert med_dest is not None
        assert med_dest.destination_type == DestinationType.HEALTHCARE
        assert len(med_dest.destination_name) > 0

        # 2. Security Threat -> Police
        pol_dest, _, _ = await SafetyGuidanceAgent._find_verified_destination(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            emergency_type="Civil / Security Threat",
            description="Armed robbery and threat in progress",
            db=db,
        )
        assert pol_dest is not None
        assert pol_dest.destination_type == DestinationType.POLICE
        assert len(pol_dest.destination_name) > 0

        # 3. Fire Outbreak -> Fire Station
        fire_dest, _, _ = await SafetyGuidanceAgent._find_verified_destination(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            emergency_type="Fire",
            description="Massive smoke and fire outbreak in commercial building",
            db=db,
        )
        assert fire_dest is not None
        assert fire_dest.destination_type == DestinationType.FIRE_STATION
        assert len(fire_dest.destination_name) > 0

        # 4. Flood / Evacuation -> Shelter
        flood_dest, _, _ = await SafetyGuidanceAgent._find_verified_destination(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            emergency_type="Flood",
            description="Rising water entering homes, need evacuation",
            db=db,
        )
        assert flood_dest is not None
        assert flood_dest.destination_type == DestinationType.SHELTER
        assert len(flood_dest.destination_name) > 0


@pytest.mark.anyio
async def test_safety_guidance_no_destination_available_fallback():
    """Verify that if no matching genuine facility exists, returns NO_VERIFIED_DESTINATION_AVAILABLE without fake data."""
    db = db_manager.db
    if db is None:
        pytest.skip("Database not connected")

    # Pass (0.0, 0.0) so PlacesService doesn't query live places
    dest, reason, alts = await SafetyGuidanceAgent._find_verified_destination(
        origin_lat=0.0,
        origin_lng=0.0,
        emergency_type="Medical Emergency",
        description="Severe injury",
        db=db,
    )
    assert dest is None
    assert reason == "NO_VERIFIED_DESTINATION_AVAILABLE"
    assert alts == []
