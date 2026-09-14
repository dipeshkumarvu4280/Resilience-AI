import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from app.models.enums import DestinationType, SeverityLevel, GuidanceApprovalState, RouteStatus
from app.models.safety_guidance import VerifiedDestination, CitizenSafetyGuidance
from app.services.places_service import PlacesService
from app.services.agents.adapters.safety_guidance_agent import SafetyGuidanceAgent


@pytest.mark.anyio
async def test_canonical_google_place_type_normalizer():
    """
    Verifies that Google Places types normalize deterministically:
    - hospital / clinic / doctor / health / pharmacy -> HEALTHCARE
    - fire_station -> FIRE_STATION
    - police / law_enforcement -> POLICE
    - bus_station / transit_station -> BUS_STATION
    - community_center / city_hall / school / stadium -> SHELTER
    - unknown / non-operational -> OTHER
    """
    # 1. Hospital & Medical
    assert PlacesService.normalize_google_place_type(["hospital", "point_of_interest", "establishment"]) == DestinationType.HEALTHCARE
    assert PlacesService.normalize_google_place_type(["medical_clinic", "health"]) == DestinationType.HEALTHCARE
    assert PlacesService.normalize_google_place_type(["doctor", "health"]) == DestinationType.HEALTHCARE
    assert PlacesService.normalize_google_place_type(["pharmacy", "health"]) == DestinationType.HEALTHCARE

    # 2. Fire Station
    assert PlacesService.normalize_google_place_type(["fire_station", "point_of_interest", "establishment"]) == DestinationType.FIRE_STATION

    # 3. Police Station
    assert PlacesService.normalize_google_place_type(["police", "point_of_interest"]) == DestinationType.POLICE
    assert PlacesService.normalize_google_place_type(["law_enforcement", "point_of_interest"]) == DestinationType.POLICE

    # 4. Bus & Transit
    assert PlacesService.normalize_google_place_type(["bus_station", "transit_station"]) == DestinationType.BUS_STATION
    assert PlacesService.normalize_google_place_type(["train_station"]) == DestinationType.BUS_STATION

    # 5. Shelters & Community Centers
    assert PlacesService.normalize_google_place_type(["community_center"]) == DestinationType.SHELTER
    assert PlacesService.normalize_google_place_type(["city_hall", "local_government_office"]) == DestinationType.SHELTER
    assert PlacesService.normalize_google_place_type(["school", "civic_center"]) == DestinationType.SHELTER

    # 6. Unrelated / Commercial / Other
    assert PlacesService.normalize_google_place_type(["beauty_salon", "hair_care"]) == DestinationType.OTHER
    assert PlacesService.normalize_google_place_type(["tailor", "clothing_store"]) == DestinationType.OTHER
    assert PlacesService.normalize_google_place_type(["restaurant", "food"]) == DestinationType.OTHER
    assert PlacesService.normalize_google_place_type([]) == DestinationType.OTHER


@pytest.mark.anyio
async def test_commercial_businesses_are_strictly_rejected():
    """
    Verifies that commercial stores, salons, tailor shops, and restaurants
    are excluded from operational emergency recommendations by _is_valid_place_type.
    """
    # Salons and tailors must be rejected
    assert not PlacesService._is_valid_place_type(["beauty_salon", "hair_care", "point_of_interest"], "FIRE")
    assert not PlacesService._is_valid_place_type(["tailor", "clothing_store", "point_of_interest"], "FIRE")
    assert not PlacesService._is_valid_place_type(["restaurant", "food"], "MEDICAL")
    assert not PlacesService._is_valid_place_type(["store", "supermarket"], "SHELTER")
    assert not PlacesService._is_valid_place_type([], "FIRE")

    # Valid emergency facilities must be accepted
    assert PlacesService._is_valid_place_type(["fire_station", "point_of_interest"], "FIRE")
    assert PlacesService._is_valid_place_type(["hospital", "health"], "FIRE")
    assert PlacesService._is_valid_place_type(["hospital", "health"], "MEDICAL")
    assert PlacesService._is_valid_place_type(["police", "point_of_interest"], "POLICE")
    assert PlacesService._is_valid_place_type(["community_center"], "SHELTER")


@pytest.mark.anyio
async def test_fire_incident_does_not_force_hospital_to_fire_station():
    """
    CRITICAL REGRESSION TEST:
    When the incident is a FIRE, and Google Places returns a hospital as a nearby facility,
    it MUST retain destination_type = HEALTHCARE, NOT be coerced to FIRE_STATION.
    """
    PlacesService.clear_cache()
    mock_places_response = {
        "places": [
            {
                "id": "ChIJ_HOSPITAL_001",
                "displayName": {"text": "Apollo Emergency Hospital", "languageCode": "en"},
                "formattedAddress": "Main Road, Guntur, AP",
                "location": {"latitude": 16.3000, "longitude": 80.4500},
                "types": ["hospital", "health", "point_of_interest"],
                "rating": 4.6,
                "businessStatus": "OPERATIONAL",
                "currentOpeningHours": {"openNow": True},
            },
            {
                "id": "ChIJ_FIRE_002",
                "displayName": {"text": "Guntur Central Fire Station", "languageCode": "en"},
                "formattedAddress": "Fire Station Road, Guntur, AP",
                "location": {"latitude": 16.3100, "longitude": 80.4600},
                "types": ["fire_station", "point_of_interest"],
                "rating": 4.2,
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
            origin_lat=16.2950,
            origin_lng=80.4450,
            need_category="FIRE",
            radius_meters=15000,
        )

        assert len(results) == 2
        # Hospital must be HEALTHCARE
        assert results[0]["name"] == "Apollo Emergency Hospital"
        assert results[0]["destination_type"] == DestinationType.HEALTHCARE
        assert results[0]["google_place_types"] == ["hospital", "health", "point_of_interest"]

        # Fire Station must be FIRE_STATION
        assert results[1]["name"] == "Guntur Central Fire Station"
        assert results[1]["destination_type"] == DestinationType.FIRE_STATION
        assert results[1]["google_place_types"] == ["fire_station", "point_of_interest"]


@pytest.mark.anyio
async def test_safety_guidance_destination_selection_truthful_rationale():
    """
    Verifies that SafetyGuidanceAgent produces truthful suitability rationale
    matching the actual destination type (e.g. healthcare for hospital, fire station for fire station).
    """
    PlacesService.clear_cache()

    async def mock_places_provider(lat, lng, need_cat, radius):
        return [
            {
                "facility_id": "PLC-HOSP-01",
                "place_id": "ChIJ_HOSP_01",
                "name": "City General Hospital",
                "destination_type": DestinationType.HEALTHCARE,
                "latitude": 16.2990,
                "longitude": 80.4480,
                "address": "12 Hospital Rd",
                "distance_km": 1.5,
                "estimated_drive_minutes": 2.5,
                "provider": "Google Places Live Discovery",
                "google_place_types": ["hospital", "health"],
            }
        ]

    PlacesService.set_custom_places_provider(mock_places_provider)

    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find.return_value = AsyncMock()
    mock_db.__getitem__.return_value.find.return_value.__aiter__.return_value = []

    primary_dest, reason, alts = await SafetyGuidanceAgent._find_verified_destination(
        origin_lat=16.2950,
        origin_lng=80.4450,
        emergency_type="Fire",
        description="Building fire with smoke",
        db=mock_db,
    )

    PlacesService.set_custom_places_provider(None)

    assert primary_dest is not None
    assert primary_dest.destination_name == "City General Hospital"
    assert primary_dest.destination_type == DestinationType.HEALTHCARE
    # Rationale must say healthcare, NOT fire station
    assert "healthcare" in primary_dest.suitability_reason.lower()
    assert "healthcare" in reason.lower()
    assert "fire station" not in reason.lower()
