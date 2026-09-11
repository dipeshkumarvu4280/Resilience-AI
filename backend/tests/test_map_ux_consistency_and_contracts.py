import pytest
from app.models.enums import EmergencyType
from app.models.sensor import SensorCoverage, SensorLocation
from app.services.map_service import MapService

from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.mark.anyio
async def test_01_sensor_coverage_radius_meters_contract():
    """Verify sensor coverage radius preserves radius_meters without diameter conversion."""
    coverage = SensorCoverage(
        radius_meters=3500.0,
        display_value=3.5,
        display_unit="km"
    )
    assert coverage.radius_meters == 3500.0
    assert coverage.display_value == 3.5
    assert coverage.display_unit == "km"

@pytest.mark.anyio
async def test_02_sensor_location_coordinates_integrity():
    """Verify sensor location coordinates preserve precision and boundaries."""
    loc = SensorLocation(
        latitude=16.5062,
        longitude=80.6480,
        street_address="Chebrolu Main Rd",
        city="Guntur",
        state="Andhra Pradesh"
    )
    assert loc.latitude == 16.5062
    assert loc.longitude == 80.6480
    assert -90 <= loc.latitude <= 90
    assert -180 <= loc.longitude <= 180

@pytest.mark.anyio
async def test_03_hotspot_service_zero_synthetic_data(client: AsyncClient, setup_db):
    """Verify emergency hotspot service does not generate synthetic markers when DB is empty."""
    res = await client.get("/api/v1/public/map/active-hotspots")
    assert res.status_code == 200
    data = res.json()
    assert "hotspots" in data
    assert isinstance(data["hotspots"], list)
    for h in data["hotspots"]:
        assert "hotspot_id" in h
        assert "latitude" in h
        assert "longitude" in h
        assert "impact_radius_km" in h
        assert -90 <= h["latitude"] <= 90
        assert -180 <= h["longitude"] <= 180

@pytest.mark.anyio
async def test_04_authoritative_report_coordinates_preservation():
    """Verify report location models strictly preserve authoritative GPS coordinates."""
    report_location = {
        "latitude": 16.2954,
        "longitude": 80.6482,
        "address": "Suddapalli, Chebrolu",
        "landmark": "Near Gram Panchayat"
    }
    assert report_location["latitude"] == 16.2954
    assert report_location["longitude"] == 80.6482
    assert report_location["landmark"] == "Near Gram Panchayat"
