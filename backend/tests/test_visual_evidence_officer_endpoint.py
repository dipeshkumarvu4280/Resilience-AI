import os
import pytest
import base64
import hashlib
import json
from unittest.mock import MagicMock
from httpx import AsyncClient
from datetime import datetime, timezone

from app.core.config import settings
from app.db.mongodb import db_manager
from app.models.enums import EmergencyType, ReportStatus, TimelineEventType
from app.services.gemini_service import GeminiIntelligenceService

# 1x1 valid GIF binary for testing image bytes
TINY_GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


class MockGeminiVisionResponse:
    def __init__(self, text: str):
        self.text = text


async def get_officer_headers(client: AsyncClient):
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999002", "password": "OfficerPassword@2026"}
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_analyze_visual_evidence_live_camera_success(client: AsyncClient):
    """Test analyze-visual-evidence successfully retrieves camera image from storage and analyzes via Gemini Vision."""
    headers = await get_officer_headers(client)
    db = db_manager.db
    report_id = "RES-TESTVIS01"
    evidence_id = "EVD-TESTVIS01"

    # Write test image to citizen_evidence directory
    evidence_dir = os.path.join(settings.UPLOAD_DIR, "citizen_evidence")
    os.makedirs(evidence_dir, exist_ok=True)
    file_path = os.path.join(evidence_dir, f"{evidence_id}.jpg")
    with open(file_path, "wb") as f:
        f.write(TINY_GIF)

    content_hash = hashlib.sha256(TINY_GIF).hexdigest()

    # Create citizen report with live camera evidence
    await db["citizen_reports"].delete_many({"report_id": report_id})
    await db["timeline_events"].delete_many({"report_id": report_id})

    report_doc = {
        "report_id": report_id,
        "citizen_id": "CIT-001",
        "citizen_name": "Ramesh Varma",
        "citizen_phone": "9876543210",
        "emergency_type": "Flood",
        "citizen_impact_level": "HIGH",
        "description": "Rising flood water entered the ground floor near market junction.",
        "location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "address": "Vijayawada Center",
        },
        "media": [],
        "evidence": {
            "evidence_id": evidence_id,
            "report_id": report_id,
            "evidence_type": "LIVE_CAMERA_PHOTO",
            "source": "BROWSER_CAMERA",
            "filename": f"{evidence_id}.jpg",
            "file_url": f"/uploads/citizen_evidence/{evidence_id}.jpg",
            "content_hash": content_hash,
            "server_received_timestamp": datetime.now(timezone.utc),
            "validation_status": "VALIDATED",
            "trust_signals": ["LIVE_CAMERA_CAPTURED", "FRESH_CAPTURE"],
            "is_duplicate": False,
        },
        "status": ReportStatus.RECEIVED.value,
        "priority": "UNASSESSED",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db["citizen_reports"].insert_one(report_doc)

    # Mock Gemini client response
    mock_payload = {
        "status": "SUCCESS",
        "hazard_type": "FLOOD",
        "hazard_confidence": 0.95,
        "hazard_description": "Water logging up to 1 meter on street.",
        "text_image_consistency": "SUPPORTED",
        "consistency_explanation": "Visual water levels match reported flood incident.",
        "claim_evaluations": [],
        "visual_observations": [
            {"category": "FLOOD_WATER", "observation": "Submerged road", "confidence": 0.9}
        ],
        "vulnerable_person_indicators": [],
        "infrastructure_conditions": [
            {"infrastructure_type": "ROAD", "condition": "SUBMERGED", "is_access_blocked": True, "confidence": 0.9}
        ],
        "visible_impacts": ["Submerged road", "Inaccessible pathway"],
        "affected_people_observable": False,
        "estimated_people_count": None,
        "medical_indicators": [],
        "environmental_indicators": ["Turbulent flood water"],
        "obstruction_indicators": ["Road blocked by water"],
        "uncertainties": [],
        "overall_confidence": 0.92,
        "warnings": [],
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MockGeminiVisionResponse(json.dumps(mock_payload))
    GeminiIntelligenceService.set_client(mock_client)
    GeminiIntelligenceService.clear_cache()

    # Call endpoint
    res = await client.post(f"/api/v1/officer/reports/{report_id}/analyze-visual-evidence", headers=headers)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data["report_id"] == report_id
    assert data["visual_evidence"] is not None
    assert data["visual_evidence"]["status"] == "SUCCESS"
    assert data["visual_evidence"]["hazard_type"] == "FLOOD"
    assert data["visual_evidence"]["text_image_consistency"] == "SUPPORTED"
    assert data["visual_evidence"]["source_type"] == "LIVE_CAMERA_EVIDENCE"

    # Verify timeline event recorded
    timeline_ev = await db["timeline_events"].find_one({"report_id": report_id, "event_type": TimelineEventType.EVIDENCE_VALIDATED.value})
    assert timeline_ev is not None

    # Cleanup
    if os.path.exists(file_path):
        os.remove(file_path)
    await db["citizen_reports"].delete_many({"report_id": report_id})
    await db["timeline_events"].delete_many({"report_id": report_id})


@pytest.mark.anyio
async def test_analyze_visual_evidence_photo_attachment_success(client: AsyncClient):
    """Test analyze-visual-evidence successfully retrieves photo from media attachments and analyzes via Gemini Vision."""
    headers = await get_officer_headers(client)
    db = db_manager.db
    report_id = "RES-TESTVIS02"
    media_filename = "media_fire_photo01.jpg"

    # Write test image to citizen_reports media directory
    media_dir = os.path.join(settings.UPLOAD_DIR, "citizen_reports")
    os.makedirs(media_dir, exist_ok=True)
    file_path = os.path.join(media_dir, media_filename)
    with open(file_path, "wb") as f:
        f.write(TINY_GIF)

    # Create citizen report with photo attachment (no live camera)
    await db["citizen_reports"].delete_many({"report_id": report_id})
    await db["timeline_events"].delete_many({"report_id": report_id})

    report_doc = {
        "report_id": report_id,
        "citizen_id": "CIT-002",
        "citizen_name": "Sita Devi",
        "citizen_phone": "9876543211",
        "emergency_type": "Fire",
        "citizen_impact_level": "CRITICAL",
        "description": "Heavy flames and smoke coming from warehouse roof.",
        "location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "address": "Industrial Area",
        },
        "media": [
            {
                "filename": media_filename,
                "file_url": f"/uploads/citizen_reports/{media_filename}",
                "media_type": "image/jpeg",
                "size_bytes": len(TINY_GIF),
            }
        ],
        "evidence": None,
        "status": ReportStatus.RECEIVED.value,
        "priority": "UNASSESSED",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db["citizen_reports"].insert_one(report_doc)

    mock_payload = {
        "status": "SUCCESS",
        "hazard_type": "FIRE",
        "hazard_confidence": 0.98,
        "hazard_description": "Flames and heavy smoke plume visibly engulfing structure.",
        "text_image_consistency": "SUPPORTED",
        "consistency_explanation": "Flames confirmed in photo.",
        "claim_evaluations": [],
        "visual_observations": [
            {"category": "FIRE", "observation": "Flames", "confidence": 0.95}
        ],
        "vulnerable_person_indicators": [],
        "infrastructure_conditions": [
            {"infrastructure_type": "BUILDING", "condition": "DAMAGED", "is_access_blocked": False, "confidence": 0.9}
        ],
        "visible_impacts": ["Heavy smoke", "Active flame"],
        "affected_people_observable": False,
        "estimated_people_count": None,
        "medical_indicators": [],
        "environmental_indicators": ["Heavy smoke column"],
        "obstruction_indicators": [],
        "uncertainties": [],
        "overall_confidence": 0.95,
        "warnings": [],
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MockGeminiVisionResponse(json.dumps(mock_payload))
    GeminiIntelligenceService.set_client(mock_client)
    GeminiIntelligenceService.clear_cache()

    res = await client.post(f"/api/v1/officer/reports/{report_id}/analyze-visual-evidence", headers=headers)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data["visual_evidence"]["status"] == "SUCCESS"
    assert data["visual_evidence"]["hazard_type"] == "FIRE"
    assert data["visual_evidence"]["source_type"] == "PHOTO_ATTACHMENT"

    if os.path.exists(file_path):
        os.remove(file_path)
    await db["citizen_reports"].delete_many({"report_id": report_id})
    await db["timeline_events"].delete_many({"report_id": report_id})


@pytest.mark.anyio
async def test_analyze_visual_evidence_missing_evidence_returns_400(client: AsyncClient):
    """Test analyze-visual-evidence returns HTTP 400 when no camera evidence or photo exists."""
    headers = await get_officer_headers(client)
    db = db_manager.db
    report_id = "RES-TESTVIS03"

    await db["citizen_reports"].delete_many({"report_id": report_id})
    report_doc = {
        "report_id": report_id,
        "citizen_id": "CIT-003",
        "citizen_name": "Anil Kumar",
        "citizen_phone": "9876543212",
        "emergency_type": "Medical Emergency",
        "citizen_impact_level": "LOW",
        "description": "Minor medical assistance required.",
        "location": {"latitude": 16.5, "longitude": 80.6},
        "media": [],
        "evidence": None,
        "status": ReportStatus.RECEIVED.value,
        "priority": "UNASSESSED",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db["citizen_reports"].insert_one(report_doc)

    res = await client.post(f"/api/v1/officer/reports/{report_id}/analyze-visual-evidence", headers=headers)
    assert res.status_code == 400
    assert "No live camera evidence or photo attachment found on this report." in res.json()["detail"]

    await db["citizen_reports"].delete_many({"report_id": report_id})


@pytest.mark.anyio
async def test_analyze_visual_evidence_storage_file_missing_returns_422(client: AsyncClient):
    """Test analyze-visual-evidence returns HTTP 422 when metadata exists but file is missing from disk."""
    headers = await get_officer_headers(client)
    db = db_manager.db
    report_id = "RES-TESTVIS04"

    await db["citizen_reports"].delete_many({"report_id": report_id})
    report_doc = {
        "report_id": report_id,
        "citizen_id": "CIT-004",
        "citizen_name": "Kavita Rao",
        "citizen_phone": "9876543213",
        "emergency_type": "Fire",
        "citizen_impact_level": "HIGH",
        "description": "Fire spotted.",
        "location": {"latitude": 16.5, "longitude": 80.6},
        "media": [],
        "evidence": {
            "evidence_id": "EVD-NONEXISTENT",
            "report_id": report_id,
            "filename": "nonexistent_file_9999.jpg",
            "file_url": "/uploads/citizen_evidence/nonexistent_file_9999.jpg",
            "server_received_timestamp": datetime.now(timezone.utc),
            "validation_status": "VALIDATED",
            "is_duplicate": False,
        },
        "status": ReportStatus.RECEIVED.value,
        "priority": "UNASSESSED",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db["citizen_reports"].insert_one(report_doc)

    res = await client.post(f"/api/v1/officer/reports/{report_id}/analyze-visual-evidence", headers=headers)
    assert res.status_code == 422
    assert "The evidence record exists, but the image could not be retrieved from storage." in res.json()["detail"]

    await db["citizen_reports"].delete_many({"report_id": report_id})
