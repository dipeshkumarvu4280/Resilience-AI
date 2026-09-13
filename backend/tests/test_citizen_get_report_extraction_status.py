import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
from app.db.mongodb import db_manager
from app.models.llm_extraction import ExtractionStatus
from app.services.routing_service import RoutingService
from app.services.places_service import PlacesService
from app.services.gemini_service import GeminiIntelligenceService


@pytest.fixture(autouse=True)
async def mock_external_calls():
    async def mock_router(o_lat, o_lng, d_lat, d_lng):
        return [[o_lat, o_lng], [d_lat, d_lng]], 1.0, 2.0, "Mock Router"

    RoutingService.set_custom_router(mock_router)
    with patch.object(PlacesService, "discover_nearby_facilities", new_callable=AsyncMock) as mock_places, \
         patch("app.api.v1.endpoints.citizen.reverse_geocode_coordinates", new_callable=AsyncMock) as mock_geo, \
         patch.object(GeminiIntelligenceService, "extract_structured_evidence", new_callable=AsyncMock) as mock_extract:
        mock_places.return_value = []
        mock_geo.return_value = {
            "address": "MG Road, Vijayawada",
            "city": "Vijayawada",
            "state": "Andhra Pradesh",
            "country": "India",
        }
        mock_extract.return_value = None
        try:
            yield
        finally:
            RoutingService.set_custom_router(None)


@pytest.mark.anyio
async def test_get_emergency_report_with_null_and_failed_extraction_status(client: AsyncClient):
    """Verify GET /api/v1/citizen/reports/{report_id} returns HTTP 200 without NameError for ExtractionStatus."""
    payload = {
        "full_name": "Ravi Kumar",
        "phone": "9876543210",
        "emergency_type": "Flood",
        "citizen_impact_level": "CRITICAL",
        "description": "Rising flood waters near residence",
        "location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "address": "MG Road, Vijayawada, Andhra Pradesh",
        },
    }

    create_res = await client.post("/api/v1/citizen/reports", json=payload)
    assert create_res.status_code == 201
    report_id = create_res.json()["report_id"]

    db = db_manager.db
    # Set llm_extraction to FAILED status
    await db["citizen_reports"].update_one(
        {"report_id": report_id},
        {"$set": {"llm_extraction": {"status": ExtractionStatus.FAILED.value, "confidence": 0.0}}}
    )

    # GET report should not raise NameError and return 200
    res = await client.get(f"/api/v1/citizen/reports/{report_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["report_id"] == report_id

    # Set llm_extraction to UNAVAILABLE status
    await db["citizen_reports"].update_one(
        {"report_id": report_id},
        {"$set": {"llm_extraction": {"status": ExtractionStatus.UNAVAILABLE.value, "confidence": 0.0}}}
    )

    res2 = await client.get(f"/api/v1/citizen/reports/{report_id}")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["report_id"] == report_id
