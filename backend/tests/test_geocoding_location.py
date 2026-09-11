import pytest
import uuid
from httpx import AsyncClient
from app.db.mongodb import get_database
from app.services.geocoding import (
    validate_coordinates,
    reverse_geocode_coordinates,
    _get_cache_key,
    _GEOCODE_CACHE,
)
from app.api.v1.endpoints.citizen import create_citizen_verification_token, generate_citizen_id
from app.core.security import create_access_token


def test_coordinate_validation_rules():
    # 1. Valid coordinates
    assert validate_coordinates(28.6139, 77.2090) is True
    assert validate_coordinates(-90.0, -180.0) is True
    assert validate_coordinates(90.0, 180.0) is True
    assert validate_coordinates(0.0, 0.0) is True
    assert validate_coordinates("37.7749", "-122.4194") is True

    # 2. Invalid Latitude rejected
    assert validate_coordinates(91.0, 77.2090) is False
    assert validate_coordinates(-90.01, 77.2090) is False

    # 3. Invalid Longitude rejected
    assert validate_coordinates(28.6139, 181.0) is False
    assert validate_coordinates(28.6139, -180.01) is False

    # 4. Non-numeric values rejected
    assert validate_coordinates("invalid", 77.2090) is False
    assert validate_coordinates(28.6139, None) is False


@pytest.mark.anyio
async def test_reverse_geocode_endpoint_validation(client: AsyncClient):
    # Valid coordinates endpoint call
    res = await client.get("/api/v1/citizen/location/reverse-geocode?lat=28.6139&lon=77.2090")
    assert res.status_code == 200
    data = res.json()
    assert data["latitude"] == 28.6139
    assert data["longitude"] == 77.2090
    assert "resolved" in data

    # Invalid latitude rejected
    bad_lat = await client.get("/api/v1/citizen/location/reverse-geocode?lat=95.0&lon=77.2090")
    assert bad_lat.status_code == 422 or bad_lat.status_code == 400

    # Invalid longitude rejected
    bad_lon = await client.get("/api/v1/citizen/location/reverse-geocode?lat=28.6139&lon=190.0")
    assert bad_lon.status_code == 422 or bad_lon.status_code == 400


@pytest.mark.anyio
async def test_geocoding_service_cache_and_failure_safety(monkeypatch):
    # Test caching behavior
    test_lat = 12.9716
    test_lon = 77.5946
    cache_key = _get_cache_key(test_lat, test_lon)
    mock_address_data = {
        "address": "MG Road, Bengaluru, Karnataka, India",
        "display_name": "MG Road, Bengaluru, Karnataka, India",
        "street_address": "MG Road",
        "zone_or_district": "Bengaluru Central, Bengaluru",
        "district": "Bengaluru Central",
        "city": "Bengaluru",
        "state": "Karnataka",
        "country": "India",
        "postal_code": "560001",
    }
    _GEOCODE_CACHE[cache_key] = (mock_address_data, 9999999999.0)

    cached_res = await reverse_geocode_coordinates(test_lat, test_lon)
    assert cached_res is not None
    assert cached_res["address"] == "MG Road, Bengaluru, Karnataka, India"
    assert cached_res["street_address"] == "MG Road"
    assert cached_res["zone_or_district"] == "Bengaluru Central, Bengaluru"
    assert cached_res["city"] == "Bengaluru"


@pytest.mark.anyio
async def test_emergency_report_creation_persists_canonical_location(client: AsyncClient):
    phone = f"985{uuid.uuid4().int % 10000000:07d}"
    citizen_id = generate_citizen_id()
    token = create_citizen_verification_token(phone, citizen_id)

    # Pre-populate cache with real resolved address for these coordinates
    lat = 28.6139
    lon = 77.2090
    cache_key = _get_cache_key(lat, lon)
    mock_address_data = {
        "address": "Connaught Place, New Delhi, Delhi, India",
        "display_name": "Connaught Place, New Delhi, Delhi, India",
        "street_address": "Connaught Place",
        "zone_or_district": "New Delhi, Delhi",
        "district": "New Delhi",
        "city": "New Delhi",
        "state": "Delhi",
        "country": "India",
        "postal_code": "110001",
    }
    _GEOCODE_CACHE[cache_key] = (mock_address_data, 9999999999.0)

    payload = {
        "full_name": "Naveen Sharma",
        "phone": phone,
        "emergency_type": "Medical Emergency",
        "description": "Pedestrian collapsed near central circle, immediate ambulance required.",
        "location": {
            "latitude": lat,
            "longitude": lon,
            "street_address": "Connaught Place",
            "manual_zone": "New Delhi, Delhi",
        },
        "verification_token": token,
        "media": []
    }

    # 1. Create Report
    create_res = await client.post("/api/v1/citizen/reports", json=payload)
    assert create_res.status_code == 201
    report = create_res.json()

    assert report["report_id"].startswith("RES-")
    assert report["location"]["latitude"] == lat
    assert report["location"]["longitude"] == lon
    assert report["location"]["address"] == "Connaught Place, New Delhi, Delhi, India"
    assert report["location"]["street_address"] == "Connaught Place"
    assert report["location"]["zone_or_district"] == "New Delhi, Delhi"
    assert report["location"]["city"] == "New Delhi"

    report_id = report["report_id"]

    # 2. Verify in MongoDB directly
    db = get_database()
    doc = await db["citizen_reports"].find_one({"report_id": report_id})
    assert doc is not None
    assert doc["location"]["latitude"] == lat
    assert doc["location"]["longitude"] == lon
    assert doc["location"]["address"] == "Connaught Place, New Delhi, Delhi, India"
    assert doc["location"]["street_address"] == "Connaught Place"
    assert doc["location"]["zone_or_district"] == "New Delhi, Delhi"
    assert doc["location"]["state"] == "Delhi"

    # 3. Retrieve through public endpoint
    fetch_res = await client.get(f"/api/v1/citizen/reports/{report_id}")
    assert fetch_res.status_code == 200
    fetched = fetch_res.json()
    assert fetched["location"]["latitude"] == lat
    assert fetched["location"]["longitude"] == lon
    assert fetched["location"]["address"] == "Connaught Place, New Delhi, Delhi, India"
    assert fetched["location"]["street_address"] == "Connaught Place"
    assert fetched["location"]["zone_or_district"] == "New Delhi, Delhi"


@pytest.mark.anyio
async def test_responder_list_emergency_reports_rbac(client: AsyncClient):
    # Unauthenticated request rejected
    unauth_res = await client.get("/api/v1/citizen/reports")
    assert unauth_res.status_code == 401 or unauth_res.status_code == 403

    # Authenticated Officer request allowed
    db = get_database()
    officer_phone = f"984{uuid.uuid4().int % 10000000:07d}"
    await db["users"].insert_one({
        "phone": officer_phone,
        "full_name": "Officer Miller",
        "role": "EMERGENCY_OFFICER",
        "is_active": True,
        "badge_number": "EOC-99",
        "created_at": "2026-09-07T00:00:00Z"
    })

    officer_token = create_access_token({"sub": officer_phone, "role": "EMERGENCY_OFFICER"})
    auth_headers = {"Authorization": f"Bearer {officer_token}"}

    list_res = await client.get("/api/v1/citizen/reports", headers=auth_headers)
    assert list_res.status_code == 200
    reports_list = list_res.json()
    assert isinstance(reports_list, list)
    if len(reports_list) > 0:
        first = reports_list[0]
        assert "latitude" in first["location"]
        assert "longitude" in first["location"]
        assert "address" in first["location"]

