import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone

from app.main import app
from app.db.mongodb import db_manager
from app.models.enums import EmergencyType, CitizenImpactLevel, ReportStatus, TimelineEventType


from unittest.mock import patch, AsyncMock
from app.services.places_service import PlacesService
from app.services.routing_service import RoutingService


@pytest.fixture(autouse=True)
async def clean_test_collections():
    test_db = db_manager.db
    if test_db is not None:
        await test_db["citizen_reports"].delete_many({})
        await test_db["citizen_safety_guidance"].delete_many({})
        await test_db["timeline_events"].delete_many({})
        await test_db["resources"].delete_many({})

    async def mock_cr_router(o_lat, o_lng, d_lat, d_lng):
        return [
            [o_lat, o_lng],
            [d_lat, d_lng],
        ], 2.5, 5.0, "Google Directions API"

    RoutingService.set_custom_router(mock_cr_router)
    with patch.object(PlacesService, "discover_nearby_facilities", new_callable=AsyncMock) as mock_places:
        mock_places.return_value = []
        try:
            yield
        finally:
            RoutingService.set_custom_router(None)


@pytest.mark.anyio
async def test_report_creation_and_receipt_retrieval():
    """Verify emergency report creation generates guidance token and can be retrieved for receipt persistence."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_payload = {
            "full_name": "Ravi Kumar",
            "phone": "+919876543210",
            "emergency_type": "Flood",
            "citizen_impact_level": "HIGH",
            "description": "Severe waterlogging near market square, water level rising rapidly past 3 feet.",
            "location": {
                "latitude": 16.5062,
                "longitude": 80.6480,
                "address": "Market Square, Vijayawada",
                "manual_zone": "East Zone",
            }
        }
        res = await client.post("/api/v1/citizen/reports", json=create_payload)
        assert res.status_code == 201, res.text
        created = res.json()
        report_id = created["report_id"]
        assert report_id.startswith("RES-")
        assert created["citizen_name"] == "Ravi Kumar"
        assert created["safety_guidance_token"] is not None

        # Retrieve via GET /reports/{report_id}
        get_res = await client.get(f"/api/v1/citizen/reports/{report_id}")
        assert get_res.status_code == 200
        retrieved = get_res.json()
        assert retrieved["report_id"] == report_id
        assert retrieved["safety_guidance_token"] == created["safety_guidance_token"]
        assert retrieved["location"]["latitude"] == 16.5062


@pytest.mark.anyio
async def test_report_modification_with_valid_token():
    """Verify modifying a report using safety guidance token updates allowed fields, appends notes, and triggers re-evaluation."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create initial report
        create_payload = {
            "full_name": "Anita Sharma",
            "phone": "+919876500001",
            "emergency_type": "Flood",
            "citizen_impact_level": "MEDIUM",
            "description": "Water entered ground floor, power still active.",
            "location": {
                "latitude": 16.5062,
                "longitude": 80.6480,
                "address": "Gandhi Road, Vijayawada",
            }
        }
        create_res = await client.post("/api/v1/citizen/reports", json=create_payload)
        assert create_res.status_code == 201
        report = create_res.json()
        report_id = report["report_id"]
        token = report["safety_guidance_token"]
        assert token is not None

        # 2. Patch report details with token in header
        patch_payload = {
            "description": "Water level escalated to 5 feet, power transformer sparking nearby.",
            "citizen_impact_level": "CRITICAL",
            "full_name": "Anita Sharma - Urgent",
            "additional_notes": "Senior citizens stuck on terrace requiring boat assistance.",
        }
        patch_res = await client.patch(
            f"/api/v1/citizen/reports/{report_id}",
            json=patch_payload,
            headers={"X-Citizen-Token": token}
        )
        assert patch_res.status_code == 200, patch_res.text
        updated = patch_res.json()
        assert updated["description"] == "Water level escalated to 5 feet, power transformer sparking nearby."
        assert updated["citizen_impact_level"] == "CRITICAL"
        assert updated["citizen_name"] == "Anita Sharma - Urgent"

        # 3. Verify audit timeline event recorded
        db = db_manager.db
        timeline = await db["timeline_events"].find({"report_id": report_id}).to_list(20)
        event_types = [t.get("event_type") for t in timeline]
        assert TimelineEventType.CITIZEN_REPORT_MODIFIED.value in event_types


@pytest.mark.anyio
async def test_report_modification_unauthorized():
    """Verify modifying a report without a valid token returns 403 Forbidden (IDOR Protection)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_payload = {
            "full_name": "Test User",
            "phone": "+919876500002",
            "emergency_type": "Fire",
            "citizen_impact_level": "HIGH",
            "description": "Dense smoke coming from commercial complex.",
            "location": {
                "latitude": 16.5062,
                "longitude": 80.6480,
                "address": "MG Road",
            }
        }
        create_res = await client.post("/api/v1/citizen/reports", json=create_payload)
        assert create_res.status_code == 201
        report_id = create_res.json()["report_id"]

        # Attempt to patch with invalid token
        patch_res = await client.patch(
            f"/api/v1/citizen/reports/{report_id}",
            json={"description": "Hacked report description that should fail."},
            headers={"X-Citizen-Token": "invalid_token_12345"}
        )
        assert patch_res.status_code == 403

        # Attempt to patch with no token
        patch_res_no_tok = await client.patch(
            f"/api/v1/citizen/reports/{report_id}",
            json={"description": "Another unauthenticated attempt."}
        )
        assert patch_res_no_tok.status_code == 403


@pytest.mark.anyio
async def test_report_modification_lifecycle_protection():
    """Verify modifying a RESOLVED report is rejected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_payload = {
            "full_name": "Vikram Singh",
            "phone": "+919876500003",
            "emergency_type": "Medical Emergency",
            "citizen_impact_level": "HIGH",
            "description": "Patient stabilized and ambulance has arrived.",
            "location": {
                "latitude": 16.5062,
                "longitude": 80.6480,
                "address": "Ring Road",
            }
        }
        create_res = await client.post("/api/v1/citizen/reports", json=create_payload)
        assert create_res.status_code == 201
        report = create_res.json()
        report_id = report["report_id"]
        token = report["safety_guidance_token"]

        # Mark report as RESOLVED in database
        db = db_manager.db
        await db["citizen_reports"].update_one(
            {"report_id": report_id},
            {"$set": {"status": ReportStatus.RESOLVED.value}}
        )

        # Attempt to modify
        patch_res = await client.patch(
            f"/api/v1/citizen/reports/{report_id}",
            json={"description": "Trying to modify a resolved incident description."},
            headers={"X-Citizen-Token": token}
        )
        assert patch_res.status_code == 400
        assert "cannot be modified" in patch_res.text
