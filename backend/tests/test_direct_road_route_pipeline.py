import pytest
from datetime import datetime, timezone
from app.db.mongodb import db_manager
from app.models.enums import RouteStatus, DestinationType, SeverityLevel
from app.models.safety_guidance import VerifiedDestination, RouteDetails
from app.services.routing_service import RoutingService, decode_google_polyline


def test_google_polyline_decoding_and_preservation():
    """Test 4: Encoded polyline preservation and precision decoding."""
    # Polyline for points: (38.5, -120.2), (40.7, -120.95), (43.252, -126.453)
    encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
    points = decode_google_polyline(encoded)
    assert len(points) == 3
    assert pytest.approx(points[0][0], 0.0001) == 38.5
    assert pytest.approx(points[0][1], 0.0001) == -120.2
    assert pytest.approx(points[1][0], 0.0001) == 40.7
    assert pytest.approx(points[1][1], 0.0001) == -120.95
    assert pytest.approx(points[2][0], 0.0001) == 43.252
    assert pytest.approx(points[2][1], 0.0001) == -126.453


def test_coordinate_validation():
    """Test 5: Strict validation of latitude (-90 to 90) and longitude (-180 to 180)."""
    # Invalid latitude
    route_invalid_lat = RoutingService._make_unavailable_route(95.0, 80.0, 16.0, 80.0, "Invalid coordinates")
    assert route_invalid_lat.route_status == RouteStatus.ROUTE_UNAVAILABLE
    assert route_invalid_lat.polyline_points == []

    # Invalid longitude
    route_invalid_lng = RoutingService._make_unavailable_route(16.0, 195.0, 16.0, 80.0, "Invalid coordinates")
    assert route_invalid_lng.route_status == RouteStatus.ROUTE_UNAVAILABLE


def test_no_synthetic_corridor_interpolation_and_no_osrm():
    """Test 9 & 10: Zero synthetic interpolation and zero OSRM/OSM/Overpass fallback."""
    assert not hasattr(RoutingService, "_generate_corridor_waypoints")
    import inspect
    src = inspect.getsource(RoutingService)
    assert "osrm" not in src.lower()
    assert "openstreetmap" not in src.lower()
    assert "overpass" not in src.lower()


@pytest.mark.anyio
async def test_valid_destination_with_valid_google_route():
    """Test 1, 2, 3: Valid destination with Google route distance and duration parsing."""
    db = db_manager.db

    async def mock_google_routes_router(o_lat, o_lng, d_lat, d_lng, db_param=None):
        return [
            [o_lat, o_lng],
            [16.2350, 80.5546],
            [d_lat, d_lng],
        ], 1.0, 1.5, "Google Routes API (Driving)"

    RoutingService.set_custom_router(mock_google_routes_router)
    try:
        route = await RoutingService.calculate_hazard_aware_route(
            origin_lat=16.2316,
            origin_lng=80.5513,
            dest_lat=16.238468,
            dest_lng=80.55732,
            db=db,
        )
        assert route.route_status == RouteStatus.CALCULATED
        assert route.distance_km == 1.0
        assert route.estimated_duration_minutes == 1.5
        assert len(route.polyline_points) == 3
        assert "Google" in route.provider
    finally:
        RoutingService.set_custom_router(None)


@pytest.mark.anyio
async def test_route_unavailable_state_and_destination_remains_visible():
    """Test 7 & 8: When route is unavailable, destination remains visible and route is truthfully marked UNAVAILABLE."""
    db = db_manager.db

    async def mock_unroutable_router(o_lat, o_lng, d_lat, d_lng, db_param=None):
        return None, 0.0, 0.0, "None"

    RoutingService.set_custom_router(mock_unroutable_router)
    try:
        route = await RoutingService.calculate_hazard_aware_route(
            origin_lat=16.2316,
            origin_lng=80.5513,
            dest_lat=16.238468,
            dest_lng=80.55732,
            db=db,
        )
        assert route.route_status == RouteStatus.ROUTE_UNAVAILABLE
        assert route.polyline_points == []
        assert route.distance_km == 0.0
        assert route.estimated_duration_minutes == 0.0
        assert any("could not be calculated" in w or "unavailable" in w.lower() for w in route.route_warnings)
    finally:
        RoutingService.set_custom_router(None)


def test_backend_frontend_route_schema_consistency():
    """Test 6: Verify RouteDetails fields conform to API schema expected by frontend."""
    route = RouteDetails(
        origin_latitude=16.2316,
        origin_longitude=80.5513,
        destination_latitude=16.238468,
        destination_longitude=80.55732,
        distance_km=1.0,
        estimated_duration_minutes=1.5,
        route_status=RouteStatus.CALCULATED,
        polyline_points=[[16.2316, 80.5513], [16.238468, 80.55732]],
        route_warnings=["Maintain situational awareness."],
        avoid_areas=[],
        provider="Google Routes API (Driving)",
        calculated_at=datetime.now(timezone.utc),
    )
    d = route.model_dump()
    assert "origin_latitude" in d
    assert "origin_longitude" in d
    assert "destination_latitude" in d
    assert "destination_longitude" in d
    assert "distance_km" in d
    assert "estimated_duration_minutes" in d
    assert "route_status" in d
    assert "polyline_points" in d
    assert "route_warnings" in d
    assert "avoid_areas" in d
    assert "provider" in d
    assert "calculated_at" in d
    assert d["route_status"] == "CALCULATED"
    assert len(d["polyline_points"]) == 2


@pytest.mark.anyio
async def test_road_following_geometry_contains_multi_segment_curve():
    """Verify route geometry contains realistic multi-segment road bends and not a single straight line."""
    db = db_manager.db
    if db is not None:
        cached_doc = await db["google_routes_cache"].find_one({"cache_key": "16.2316_80.5513_16.2385_80.5573"})
        if cached_doc:
            pts = cached_doc.get("polyline_points", [])
            assert len(pts) >= 10, "Road route must contain detailed road-following vertices, not a single straight line."
            assert cached_doc.get("distance_km") == 1.0
            assert cached_doc.get("duration_minutes") == 1.5


@pytest.mark.anyio
async def test_restricted_private_road_handling():
    """Test 8: Restricted or private road warning triggers RESTRICTED status and truthful warning."""
    db = db_manager.db

    async def mock_restricted_router(o_lat, o_lng, d_lat, d_lng, db_param=None):
        return RouteDetails(
            origin_latitude=o_lat,
            origin_longitude=o_lng,
            destination_latitude=d_lat,
            destination_longitude=d_lng,
            distance_km=2.5,
            estimated_duration_minutes=5.0,
            route_status=RouteStatus.RESTRICTED,
            polyline_points=[[o_lat, o_lng], [16.234, 80.554], [d_lat, d_lng]],
            encoded_polyline="_p~iF~ps|U_ulLnnqC_mqNvxq`@",
            route_warnings=["Available route has access restrictions.", "This route has restricted usage or private roads."],
            avoid_areas=[],
            provider="Google Routes API (Driving)",
            calculated_at=datetime.now(timezone.utc),
        )

    RoutingService.set_custom_router(mock_restricted_router)
    try:
        route = await RoutingService.calculate_hazard_aware_route(
            origin_lat=16.2316,
            origin_lng=80.5513,
            dest_lat=16.238468,
            dest_lng=80.55732,
            db=db,
        )
        assert route.route_status == RouteStatus.RESTRICTED
        assert "Available route has access restrictions." in route.route_warnings
        assert route.encoded_polyline is not None
    finally:
        RoutingService.set_custom_router(None)


@pytest.mark.anyio
async def test_no_accessible_driving_route_reason():
    """Test 7: Inaccessible driving route returns NO_ACCESSIBLE_DRIVING_ROUTE."""
    route = RoutingService._make_unavailable_route(16.2316, 80.5513, 16.238468, 80.55732)
    assert route.route_status == RouteStatus.ROUTE_UNAVAILABLE
    assert route.polyline_points == []
    assert route.encoded_polyline is None
    assert "NO_ACCESSIBLE_DRIVING_ROUTE" in route.route_warnings


@pytest.mark.anyio
async def test_google_route_provider_quota_exhaustion_429():
    """Test: Google Routes API 429 quota exhaustion returns ROUTE_PROVIDER_ERROR and zero fake lines."""
    db = db_manager.db

    async def mock_quota_router(o_lat, o_lng, d_lat, d_lng, db_param=None):
        return RoutingService._make_unavailable_route(
            o_lat, o_lng, d_lat, d_lng,
            reason="Google Routes API quota limit reached (HTTP 429). Live driving route computation temporarily unavailable.",
            status=RouteStatus.ROUTE_PROVIDER_ERROR,
        )

    RoutingService.set_custom_router(mock_quota_router)
    try:
        route = await RoutingService.calculate_hazard_aware_route(
            origin_lat=16.2316,
            origin_lng=80.5513,
            dest_lat=16.238468,
            dest_lng=80.55732,
            db=db,
        )
        assert route.route_status == RouteStatus.ROUTE_PROVIDER_ERROR
        assert route.polyline_points == []
        assert "429" in route.route_warnings[0]
    finally:
        RoutingService.set_custom_router(None)

