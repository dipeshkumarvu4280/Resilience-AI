import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
import time

from app.models.enums import DestinationType, SeverityLevel, GuidanceApprovalState, RouteStatus
from app.models.safety_guidance import VerifiedDestination, CitizenSafetyGuidance, RouteDetails
from app.services.places_service import PlacesService
from app.services.routing_service import RoutingService
from app.services.agents.adapters.safety_guidance_agent import SafetyGuidanceAgent
from app.services.resource_matching import haversine_distance_km


@pytest.mark.anyio
async def test_places_service_drive_time_estimation():
    """Verifies road drive time calculation using 40 km/h average emergency civilian speed."""
    assert PlacesService.estimate_drive_time_minutes(0.0) == 1.0
    # 10 km at 40 km/h = 15 minutes
    drive_10km = PlacesService.estimate_drive_time_minutes(10.0)
    assert drive_10km == 15.0
    # 2 km = 3 minutes
    drive_2km = PlacesService.estimate_drive_time_minutes(2.0)
    assert drive_2km == 3.0


@pytest.mark.anyio
async def test_places_service_google_search_nearby_local_first():
    """
    Tests Google Places API (New searchNearby) discovery with strict DISTANCE ranking.
    """
    PlacesService.clear_cache()
    mock_places_response = {
        "places": [
            {
                "id": "ChIJ0QwTlrsJSjoRZOV7g4CWLj8",
                "displayName": {"text": "DVC Hospital & Research Center", "languageCode": "en"},
                "formattedAddress": "D.NO 12-290, Guntur -Tenali Rd, Chebrolu Mandal, Vadlamudi, AP 522213",
                "location": {"latitude": 16.238468, "longitude": 80.557320},
                "types": ["hospital", "doctor", "health", "point_of_interest"],
                "rating": 4.5,
                "businessStatus": "OPERATIONAL",
                "currentOpeningHours": {"openNow": True},
            },
            {
                "id": "ChIJ41IfAxwNSjoRXTObrTewJVI",
                "displayName": {"text": "Praja vaidyasala Dr Shaik Haneef", "languageCode": "en"},
                "formattedAddress": "Chebrolu, Guntur, AP 522212",
                "location": {"latitude": 16.198305, "longitude": 80.531275},
                "types": ["hospital", "health"],
                "rating": 4.0,
                "businessStatus": "OPERATIONAL",
                "currentOpeningHours": {"openNow": True},
            },
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_places_response
        mock_post.return_value = mock_resp

        results = await PlacesService._fetch_google_places(
            origin_lat=16.227369,
            origin_lng=80.537579,
            need_category="MEDICAL",
            radius_meters=15000,
        )

        assert len(results) == 2
        # Nearest facility must be first
        assert results[0]["name"] == "DVC Hospital & Research Center"
        assert results[0]["place_id"] == "ChIJ0QwTlrsJSjoRZOV7g4CWLj8"
        assert results[0]["destination_type"] == DestinationType.HEALTHCARE
        assert results[0]["distance_km"] < results[1]["distance_km"]


@pytest.mark.anyio
async def test_places_service_quota_exhaustion_429_truthful_failure():
    """
    Verifies that when Google Places returns 429 quota exhaustion, it does not
    invent fake places or fall back to arbitrary text queries, returning [] instead.
    """
    PlacesService.clear_cache()
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = '{"error": {"code": 429, "message": "Resource has been exhausted", "status": "RESOURCE_EXHAUSTED"}}'
        mock_post.return_value = mock_resp

        results = await PlacesService._fetch_google_places(
            origin_lat=16.227369,
            origin_lng=80.537579,
            need_category="MEDICAL",
            radius_meters=15000,
        )

        assert results == []


@pytest.mark.anyio
async def test_places_service_caching_behavior():
    """
    Verifies that genuine Google Places responses are cached in memory and reused
    within the cache TTL, saving API quota.
    """
    PlacesService.clear_cache()
    mock_places_response = {
        "places": [
            {
                "id": "ChIJ0QwTlrsJSjoRZOV7g4CWLj8",
                "displayName": {"text": "DVC Hospital & Research Center", "languageCode": "en"},
                "formattedAddress": "Vadlamudi, Guntur, AP",
                "location": {"latitude": 16.238468, "longitude": 80.557320},
                "types": ["hospital"],
                "rating": 4.5,
                "businessStatus": "OPERATIONAL",
            }
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_places_response
        mock_post.return_value = mock_resp

        # First call fetches live
        res1 = await PlacesService.discover_nearby_facilities(
            origin_lat=16.227369,
            origin_lng=80.537579,
            need_category="MEDICAL",
            radius_meters=15000,
        )
        assert len(res1) == 1
        assert res1[0]["name"] == "DVC Hospital & Research Center"
        assert mock_post.call_count == 1

        # Second call for same location should hit cache without calling API again
        res2 = await PlacesService.discover_nearby_facilities(
            origin_lat=16.227369,
            origin_lng=80.537579,
            need_category="MEDICAL",
            radius_meters=15000,
        )
        assert len(res2) == 1
        assert res2[0]["name"] == "DVC Hospital & Research Center"
        assert mock_post.call_count == 1  # No additional network call made


@pytest.mark.anyio
async def test_safety_guidance_find_verified_destination_fastest_ranking():
    """
    Verifies that _find_verified_destination discovers facilities via PlacesService & DB,
    ranks them by fastest road travel time, and returns primary + up to 3 alternatives.
    """
    mock_places = [
        {
            "place_id": "ChIJ0QwTlrsJSjoRZOV7g4CWLj8",
            "name": "DVC Hospital & Research Center",
            "destination_type": DestinationType.HEALTHCARE,
            "latitude": 16.238468,
            "longitude": 80.557320,
            "address": "Vadlamudi, Guntur, AP",
            "distance_km": 2.44,
            "estimated_drive_minutes": 5.7,
            "rating": 4.5,
            "open_now": True,
            "provider": "google_places",
            "contact_phone": "+91-863-2345678",
        },
        {
            "place_id": "PLC-GUNTUR-001",
            "name": "Amar Clinic Ponnur Road",
            "destination_type": DestinationType.HEALTHCARE,
            "latitude": 16.2417,
            "longitude": 80.4496,
            "address": "Ponnur Road, Guntur, AP",
            "distance_km": 11.34,
            "estimated_drive_minutes": 22.8,
            "rating": 4.8,
            "open_now": True,
            "provider": "google_places",
        },
        {
            "place_id": "PLC-GUNTUR-002",
            "name": "St Joseph Hospital",
            "destination_type": DestinationType.HEALTHCARE,
            "latitude": 16.2891,
            "longitude": 80.4502,
            "address": "Guntur, AP",
            "distance_km": 11.45,
            "estimated_drive_minutes": 23.5,
            "rating": 4.2,
            "open_now": True,
            "provider": "google_places",
        },
        {
            "place_id": "PLC-GUNTUR-003",
            "name": "NRI General Hospital",
            "destination_type": DestinationType.HEALTHCARE,
            "latitude": 16.2798,
            "longitude": 80.4589,
            "address": "Tenali Road, Guntur",
            "distance_km": 11.48,
            "estimated_drive_minutes": 24.0,
            "rating": 4.0,
            "open_now": True,
            "provider": "google_places",
        },
    ]

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    
    async def empty_async_gen():
        if False:
            yield {}
    mock_cursor.__aiter__.side_effect = empty_async_gen
    mock_db.__getitem__.return_value.find.return_value = mock_cursor

    async def mock_router(o_lat, o_lng, d_lat, d_lng, db=None):
        dist = haversine_distance_km(o_lat, o_lng, d_lat, d_lng) * 1.2
        dur = (dist / 35.0) * 60.0
        return RouteDetails(
            origin_latitude=o_lat,
            origin_longitude=o_lng,
            destination_latitude=d_lat,
            destination_longitude=d_lng,
            distance_km=round(dist, 2),
            estimated_duration_minutes=round(dur, 1),
            route_status=RouteStatus.CALCULATED,
            polyline_points=[[o_lat, o_lng], [d_lat, d_lng]],
            route_warnings=[],
            avoid_areas=[],
            provider="Google Routes API (Driving)",
            calculated_at=datetime.now(timezone.utc),
        )

    RoutingService.set_custom_router(mock_router)
    try:
        with patch.object(PlacesService, "discover_nearby_facilities", new_callable=AsyncMock) as mock_discover:
            mock_discover.return_value = mock_places

            primary_dest, reason, alternatives = await SafetyGuidanceAgent._find_verified_destination(
                origin_lat=16.227369,
                origin_lng=80.537579,
                emergency_type="Road Accident",
                db=mock_db,
                description="bike accident near hostel, driver severely injured",
            )

            assert primary_dest is not None
            # DVC Hospital must be selected as Rank #1
            assert primary_dest.destination_name == "DVC Hospital & Research Center"
            assert primary_dest.place_id == "ChIJ0QwTlrsJSjoRZOV7g4CWLj8"
            assert primary_dest.estimated_drive_minutes > 0
            assert primary_dest.distance_km < 4.0
            assert primary_dest.rating == 4.5
            assert primary_dest.open_now is True
            assert "Fastest road-accessible" in reason
            assert len(alternatives) == 3
            alt_names = [a.destination_name for a in alternatives]
            assert "Amar Clinic Ponnur Road" in alt_names
            assert "St Joseph Hospital" in alt_names
            assert "NRI General Hospital" in alt_names
    finally:
        RoutingService.set_custom_router(None)


@pytest.mark.anyio
async def test_generate_safety_guidance_persists_nearby_alternatives():
    """
    Verifies that generate_safety_guidance constructs and persists nearby_alternatives
    to MongoDB and returns a complete CitizenSafetyGuidance model.
    """
    mock_db = MagicMock()
    mock_report = {
        "report_id": "RES-7ZN7PETM",
        "emergency_type": "Road Accident",
        "description": "bike accident near hostel, driver severely injured",
        "citizen_impact_level": "HIGH",
        "location": {
            "latitude": 16.227369,
            "longitude": 80.537579,
            "address": "Suddapalli, Chebrolu, Guntur, AP",
        },
    }

    mock_db.__getitem__.return_value.find_one = AsyncMock(side_effect=lambda q: mock_report if "report_id" in q and q.get("report_id") == "RES-7ZN7PETM" and "status" not in q else None)
    mock_db.__getitem__.return_value.insert_one = AsyncMock()
    mock_db.__getitem__.return_value.update_one = AsyncMock()
    mock_db.__getitem__.return_value.update_many = AsyncMock()
    
    mock_prev_cursor = MagicMock()
    mock_prev_cursor.to_list = AsyncMock(return_value=[])
    mock_prev_cursor.sort = MagicMock(return_value=mock_prev_cursor)
    mock_db.__getitem__.return_value.find.return_value = mock_prev_cursor

    mock_places = [
        {
            "place_id": "ChIJ0QwTlrsJSjoRZOV7g4CWLj8",
            "name": "DVC Hospital & Research Center",
            "destination_type": DestinationType.HEALTHCARE,
            "latitude": 16.238468,
            "longitude": 80.557320,
            "address": "Vadlamudi, Guntur, AP",
            "distance_km": 2.44,
            "estimated_drive_minutes": 5.7,
            "rating": 4.5,
            "open_now": True,
            "provider": "Google Places Live Discovery",
        },
        {
            "place_id": "PLC-HOSP-2",
            "name": "Chebrolu Primary Health Care Center",
            "destination_type": DestinationType.HEALTHCARE,
            "latitude": 16.197410,
            "longitude": 80.523910,
            "address": "Chebrolu, Guntur, AP",
            "distance_km": 3.74,
            "estimated_drive_minutes": 8.0,
            "rating": 4.1,
            "open_now": True,
            "provider": "Google Places Live Discovery",
        },
    ]

    with patch.object(PlacesService, "discover_nearby_facilities", new_callable=AsyncMock) as mock_discover:
        mock_discover.return_value = mock_places

        guidance = await SafetyGuidanceAgent.generate_safety_guidance(
            report_id="RES-7ZN7PETM",
            db=mock_db,
            force_refresh=True,
        )

        assert guidance is not None
        assert guidance.recommended_destination is not None
        assert guidance.recommended_destination.destination_name == "DVC Hospital & Research Center"
        assert guidance.recommended_destination.place_id == "ChIJ0QwTlrsJSjoRZOV7g4CWLj8"
        assert len(guidance.nearby_alternatives) == 1
        assert guidance.nearby_alternatives[0].destination_name == "Chebrolu Primary Health Care Center"

        assert mock_db["citizen_safety_guidance"].insert_one.called
        inserted_doc = mock_db["citizen_safety_guidance"].insert_one.call_args[0][0]
        assert "nearby_alternatives" in inserted_doc
        assert len(inserted_doc["nearby_alternatives"]) == 1


def test_is_valid_place_type_filters_irrelevant_businesses():
    """Verifies that commercial traders, shops, and restaurants are rejected for emergency categories."""
    # Medical: hospital/doctor/clinic must pass
    assert PlacesService._is_valid_place_type(["hospital", "health", "point_of_interest"], "MEDICAL") is True
    assert PlacesService._is_valid_place_type(["doctor", "health"], "MEDICAL") is True

    # Medical: Rice trader / wholesaler / restaurant must be rejected
    assert PlacesService._is_valid_place_type(["store", "wholesaler", "food"], "MEDICAL") is False
    assert PlacesService._is_valid_place_type(["restaurant", "food", "point_of_interest"], "MEDICAL") is False
    assert PlacesService._is_valid_place_type(["grocery_or_supermarket", "store"], "MEDICAL") is False

    # Police: police station must pass, bar/retail must be rejected
    assert PlacesService._is_valid_place_type(["police", "local_government_office"], "POLICE") is True
    assert PlacesService._is_valid_place_type(["night_club", "bar", "store"], "POLICE") is False

    # Fire: fire station must pass, general business rejected
    assert PlacesService._is_valid_place_type(["fire_station", "point_of_interest"], "FIRE") is True
    assert PlacesService._is_valid_place_type(["car_dealer", "store"], "FIRE") is False
