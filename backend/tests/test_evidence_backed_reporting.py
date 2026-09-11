import pytest
import base64
import hashlib
from datetime import datetime, timezone, timedelta
from app.models.enums import CitizenImpactLevel, EvidenceValidationStatus, ReportTrustState, UserRole
from app.services.evidence_service import EvidenceValidationService
from app.core.security import create_access_token

# Valid distinct 1x1 PNGs for tests
PNG_RED = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
PNG_GREEN = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
PNG_BLUE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPj/HwADBwIAMCbhyQAAAABJRU5ErkJggg=="
PNG_WHITE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="


@pytest.mark.anyio
async def test_haversine_distance_math():
    """Verify the Haversine distance algorithm calculates accurate distances in meters."""
    # New Delhi (28.6139, 77.2090) to Connaught Place (28.6315, 77.2167) ~ 2.08 km (2080m)
    dist = EvidenceValidationService.calculate_haversine_distance(28.6139, 77.2090, 28.6315, 77.2167)
    assert 1900 < dist < 2200

    # Same location -> 0 meters
    zero_dist = EvidenceValidationService.calculate_haversine_distance(12.9716, 77.5946, 12.9716, 77.5946)
    assert zero_dist < 1.0


@pytest.mark.anyio
async def test_citizen_report_all_impact_levels(client, db):
    """Verify reports can be created with all 5 CitizenImpactLevel options."""
    impact_levels = ["LOW", "MEDIUM", "HIGH", "CRITICAL", "NOT_SURE"]

    for idx, impact in enumerate(impact_levels):
        phone = f"98765432{idx:02d}"
        payload = {
            "emergency_type": "Flood",
            "full_name": f"Citizen {impact}",
            "phone": phone,
            "description": f"Testing impact level {impact} with real user input description.",
            "citizen_impact_level": impact,
            "location": {
                "latitude": 28.6139 + (idx * 0.001),
                "longitude": 77.2090 + (idx * 0.001),
                "street_address": f"{idx} Main St, Delhi",
                "city": "Delhi",
                "state": "Delhi",
                "pincode": "110001",
            },
        }

        response = await client.post("/api/v1/citizen/reports", json=payload)
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["citizen_impact_level"] == impact
        assert data["status"] == "RECEIVED"
        assert data["trust_state"] in ["NORMAL", "REVIEW_REQUIRED"]

        # Verify underlying DB document maintains UNASSESSED priority (Human officer remains final authority)
        report_doc = await db["citizen_reports"].find_one({"report_id": data["report_id"]})
        assert report_doc["priority"] == "UNASSESSED"
        assert report_doc["citizen_impact_level"] == impact


@pytest.mark.anyio
async def test_live_evidence_capture_and_hashing(client, db):
    """Verify live camera evidence is persisted with SHA-256 content hash and metadata."""
    now_dt = datetime.now(timezone.utc)
    raw_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    expected_hash = hashlib.sha256(base64.b64decode(raw_b64)).hexdigest()

    payload = {
        "emergency_type": "Fire",
        "full_name": "Evidence Test User",
        "phone": "9811223344",
        "description": "Live fire captured with camera evidence in city square.",
        "citizen_impact_level": "HIGH",
        "location": {
            "latitude": 28.6139,
            "longitude": 77.2090,
            "street_address": "Connaught Place, Delhi",
            "city": "Delhi",
            "state": "Delhi",
            "pincode": "110001",
        },
        "evidence": {
            "image_base64": PNG_RED,
            "status": "VALIDATED",
            "latitude": 28.6140,  # ~15 meters away
            "longitude": 77.2091,
            "accuracy_meters": 12.5,
            "client_capture_timestamp": now_dt.isoformat(),
        },
    }

    response = await client.post("/api/v1/citizen/reports", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["evidence"] is not None
    assert data["evidence"]["validation_status"] in ["VALIDATED", "VERIFIED"]
    assert data["evidence"]["content_hash"] == expected_hash
    assert data["evidence"]["distance_from_report_meters"] is not None
    assert data["evidence"]["distance_from_report_meters"] < 50
    assert "LOCATION_MATCHED" in data["trust_signals"]
    assert "FRESH_CAPTURE" in data["trust_signals"]
    assert data["trust_state"] == "NORMAL"


@pytest.mark.anyio
async def test_duplicate_evidence_detection(client, db):
    """Verify duplicate image submissions are flagged with DUPLICATE_EVIDENCE."""
    now_dt = datetime.now(timezone.utc)

    # Report 1
    payload1 = {
        "emergency_type": "Building Collapse",
        "full_name": "First Submitter",
        "phone": "9800000001",
        "description": "First report of building collapse in the area.",
        "citizen_impact_level": "CRITICAL",
        "location": {
            "latitude": 19.0760,
            "longitude": 72.8777,
            "street_address": "Andheri East, Mumbai",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400069",
        },
        "evidence": {
            "image_base64": PNG_WHITE,
            "status": "VALIDATED",
            "latitude": 19.0760,
            "longitude": 72.8777,
            "accuracy_meters": 8.0,
            "client_capture_timestamp": now_dt.isoformat(),
        },
    }

    r1 = await client.post("/api/v1/citizen/reports", json=payload1)
    assert r1.status_code == 201

    # Report 2 using identical image payload
    payload2 = {
        "emergency_type": "Building Collapse",
        "full_name": "Second Submitter (Duplicate Image)",
        "phone": "9800000002",
        "description": "Second report with identical duplicate photograph.",
        "citizen_impact_level": "HIGH",
        "location": {
            "latitude": 19.0760,
            "longitude": 72.8777,
            "street_address": "Andheri East, Mumbai",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400069",
        },
        "evidence": {
            "image_base64": PNG_WHITE,
            "status": "VALIDATED",
            "latitude": 19.0760,
            "longitude": 72.8777,
            "accuracy_meters": 10.0,
            "client_capture_timestamp": now_dt.isoformat(),
        },
    }

    r2 = await client.post("/api/v1/citizen/reports", json=payload2)
    assert r2.status_code == 201
    d2 = r2.json()

    assert "DUPLICATE_EVIDENCE" in d2["trust_signals"]
    assert d2["evidence"]["validation_status"] in ["LOW_CONFIDENCE", "FLAGGED"]
    assert d2["trust_state"] == "LOW_CONFIDENCE"


@pytest.mark.anyio
async def test_evidence_location_mismatch_triage(client, db):
    """Verify evidence captured far away (>1km and >5km) sets appropriate trust signals."""
    now_dt = datetime.now(timezone.utc)

    # Moderate mismatch (~2.5 km away)
    payload_moderate = {
        "emergency_type": "Flood",
        "full_name": "Mismatch Submitter",
        "phone": "9877001122",
        "description": "Water logging in low lying residential area.",
        "citizen_impact_level": "MEDIUM",
        "location": {
            "latitude": 28.6139,
            "longitude": 77.2090,
            "street_address": "Central Delhi",
            "city": "Delhi",
            "state": "Delhi",
            "pincode": "110001",
        },
        "evidence": {
            "image_base64": PNG_GREEN,
            "status": "VALIDATED",
            "latitude": 28.6350,  # ~2.5km north
            "longitude": 77.2150,
            "accuracy_meters": 15.0,
            "client_capture_timestamp": now_dt.isoformat(),
        },
    }

    r_mod = await client.post("/api/v1/citizen/reports", json=payload_moderate)
    assert r_mod.status_code == 201
    d_mod = r_mod.json()

    assert "LOCATION_MISMATCH" in d_mod["trust_signals"]
    assert d_mod["evidence"]["validation_status"] in ["REVIEW_REQUIRED", "MISMATCH"]
    assert d_mod["trust_state"] == "REVIEW_REQUIRED"

    # Severe mismatch (>20 km away)
    payload_severe = {
        "emergency_type": "Flood",
        "full_name": "Severe Mismatch Submitter",
        "phone": "9877001133",
        "description": "Water logging in Delhi but camera captured in Gurgaon.",
        "citizen_impact_level": "CRITICAL",
        "location": {
            "latitude": 28.6139,
            "longitude": 77.2090,
            "street_address": "Central Delhi",
            "city": "Delhi",
            "state": "Delhi",
            "pincode": "110001",
        },
        "evidence": {
            "image_base64": PNG_BLUE,
            "status": "VALIDATED",
            "latitude": 28.4595,  # ~25km away in Gurgaon
            "longitude": 77.0266,
            "accuracy_meters": 20.0,
            "client_capture_timestamp": now_dt.isoformat(),
        },
    }

    r_sev = await client.post("/api/v1/citizen/reports", json=payload_severe)
    assert r_sev.status_code == 201
    d_sev = r_sev.json()

    assert "SEVERE_LOCATION_MISMATCH" in d_sev["trust_signals"]
    assert d_sev["evidence"]["validation_status"] in ["LOW_CONFIDENCE", "FLAGGED", "REVIEW_REQUIRED", "MISMATCH"]
    assert d_sev["trust_state"] == "LOW_CONFIDENCE"


@pytest.mark.anyio
async def test_camera_unavailable_graceful_submission(client, db):
    """Verify citizen report can be submitted when camera is denied/unavailable without blocking."""
    payload = {
        "emergency_type": "Medical Emergency",
        "full_name": "No Camera Citizen",
        "phone": "9876543299",
        "description": "Patient experiencing respiratory distress, no camera on device.",
        "citizen_impact_level": "CRITICAL",
        "location": {
            "latitude": 13.0827,
            "longitude": 80.2707,
            "street_address": "Chennai Central",
            "city": "Chennai",
            "state": "Tamil Nadu",
            "pincode": "600003",
        },
        "evidence": {
            "status": "UNAVAILABLE",
        },
    }

    response = await client.post("/api/v1/citizen/reports", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["evidence"]["validation_status"] == "UNAVAILABLE"
    assert "CAMERA_UNAVAILABLE" in data["trust_signals"]
    assert data["trust_state"] in ["NORMAL", "REVIEW_REQUIRED"]
    assert data["status"] == "RECEIVED"


@pytest.mark.anyio
async def test_poor_accuracy_and_time_skew(client, db):
    """Verify poor GPS accuracy (>150m) and stale timestamps (>30m) are flagged."""
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    payload = {
        "emergency_type": "Landslide",
        "full_name": "Skew Submitter",
        "phone": "9899887766",
        "description": "Debris on road causing blockade in hills.",
        "citizen_impact_level": "MEDIUM",
        "location": {
            "latitude": 30.3165,
            "longitude": 78.0322,
            "street_address": "Dehradun Highway",
            "city": "Dehradun",
            "state": "Uttarakhand",
            "pincode": "248001",
        },
        "evidence": {
            "image_base64": PNG_RED,
            "status": "VALIDATED",
            "latitude": 30.3166,
            "longitude": 78.0323,
            "accuracy_meters": 250.0,  # poor accuracy > 150m
            "client_capture_timestamp": stale_time,  # 2 hours stale
        },
    }

    response = await client.post("/api/v1/citizen/reports", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert "POOR_ACCURACY" in data["trust_signals"]
    assert "STALE_CAPTURE" in data["trust_signals"]
    assert data["trust_state"] in ["REVIEW_REQUIRED", "LOW_CONFIDENCE"]


@pytest.mark.anyio
async def test_separation_of_citizen_impact_and_human_officer_authority(client, db):
    """Verify citizen impact level does NOT auto-set officer priority or auto-dispatch resources."""
    payload = {
        "emergency_type": "Cyclone / Storm",
        "full_name": "High Alert Citizen",
        "phone": "9812345678",
        "description": "Trees down, strong gale winds along coastal belt.",
        "citizen_impact_level": "CRITICAL",
        "location": {
            "latitude": 20.2961,
            "longitude": 85.8245,
            "street_address": "Bhubaneswar Coastal",
            "city": "Bhubaneswar",
            "state": "Odisha",
            "pincode": "751001",
        },
    }

    response = await client.post("/api/v1/citizen/reports", json=payload)
    assert response.status_code == 201
    data = response.json()
    report_id = data["report_id"]

    # Authority assertions
    assert data["citizen_impact_level"] == "CRITICAL"
    assert data["status"] == "RECEIVED"

    # Verify underlying DB document priority remains UNASSESSED
    doc = await db["citizen_reports"].find_one({"report_id": report_id})
    assert doc["priority"] == "UNASSESSED"

    # Check zero auto-dispatches were created
    dispatches_count = await db["dispatches"].count_documents({"report_id": report_id})
    assert dispatches_count == 0, "No automatic dispatches should be created upon citizen intake"

    # Verify Timeline Events
    timeline_count = await db["timeline_events"].count_documents({"report_id": report_id})
    assert timeline_count >= 1

    # Officer explicitly sets priority to HIGH (human authority)
    officer_token = create_access_token(
        data={"sub": "9999999002", "role": UserRole.EMERGENCY_OFFICER.value}
    )
    headers = {"Authorization": f"Bearer {officer_token}"}

    update_res = await client.patch(
        f"/api/v1/officer/reports/{report_id}/priority",
        json={"priority": "HIGH"},
        headers=headers,
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["priority"] == "HIGH"
    assert updated_data["citizen_impact_level"] == "CRITICAL"


@pytest.mark.anyio
async def test_officer_report_details_evidence_contract(client, db):
    """Verify Officer Report Details endpoint returns complete evidence, trust signals, and impact level."""
    now_dt = datetime.now(timezone.utc)
    payload = {
        "emergency_type": "Fire",
        "full_name": "Inspection Citizen",
        "phone": "9811122233",
        "description": "Dense smoke seen rising from commercial building.",
        "citizen_impact_level": "HIGH",
        "location": {
            "latitude": 12.9716,
            "longitude": 77.5946,
            "street_address": "MG Road, Bengaluru",
            "city": "Bengaluru",
            "state": "Karnataka",
            "pincode": "560001",
        },
        "evidence": {
            "image_base64": PNG_RED,
            "status": "VALIDATED",
            "latitude": 12.9718,
            "longitude": 77.5948,
            "accuracy_meters": 10.0,
            "client_capture_timestamp": now_dt.isoformat(),
        },
    }

    create_res = await client.post("/api/v1/citizen/reports", json=payload)
    assert create_res.status_code == 201
    report_id = create_res.json()["report_id"]

    officer_token = create_access_token(
        data={"sub": "9999999002", "role": UserRole.EMERGENCY_OFFICER.value}
    )
    headers = {"Authorization": f"Bearer {officer_token}"}

    detail_res = await client.get(f"/api/v1/officer/reports/{report_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()

    assert detail["citizen_impact_level"] == "HIGH"
    assert detail["evidence"] is not None
    assert detail["evidence"]["latitude"] == 12.9718
    assert detail["evidence"]["longitude"] == 77.5948
    assert detail["evidence"]["accuracy_meters"] == 10.0
    assert detail["trust_state"] in ["NORMAL", "REVIEW_REQUIRED", "LOW_CONFIDENCE"]
    assert isinstance(detail["trust_signals"], list)
    assert len(detail["trust_signals"]) > 0
