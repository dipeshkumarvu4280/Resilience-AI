import pytest
import uuid
from datetime import datetime, timezone
from httpx import AsyncClient
from pydantic import ValidationError

from app.models.enums import (
    EmergencyType,
    SeverityLevel,
    SituationStatus,
    AssessmentStatus,
    OfficerReviewAction,
    TimelineEventType,
    ReportPriority,
    ReportStatus,
)
from app.models.situation import (
    SituationCluster,
    SituationAssessment,
    ImpactZone,
    SituationLocationCenter,
    OfficerSituationReview,
    OfficerSituationReviewRequest,
)
from app.services.incident_fusion import (
    calculate_cluster_centroid_and_radius,
    are_emergency_types_cluster_compatible,
)
from app.services.severity_engine import (
    calculate_explainable_severity,
    BASE_EMERGENCY_SEVERITY,
)
from app.services.situation_assessment import (
    calculate_evidence_confidence,
    generate_deterministic_situation_assessment,
    generate_situation_assessment,
    RawAISituationAssessmentSchema,
)


async def get_officer_headers(client: AsyncClient):
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"phone": "9999999002", "password": "OfficerPassword@2026"},
    )
    assert login_res.status_code == 200, login_res.text
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------
# 1. Situation Schema & Model Validation Tests
# --------------------------------------------------------------------------
@pytest.mark.anyio
async def test_situation_model_validations():
    """Test strict validation of situation models, fields, and numerical bounds."""
    now = datetime.now(timezone.utc)
    
    # Valid SituationCluster
    loc = SituationLocationCenter(latitude=16.2415, longitude=80.6433, city="Guntur", zone_or_district="Zone 4")
    impact = ImpactZone(center_latitude=16.2415, center_longitude=80.6433, radius_km=2.5)
    
    cluster = SituationCluster(
        situation_id="SIT-TEST1234",
        cluster_id="CLS-TEST1234",
        title="Flood Emergency - Zone 4",
        emergency_type=EmergencyType.FLOOD,
        primary_report_id="REP-TEST0001",
        report_ids=["REP-TEST0001"],
        report_count=1,
        center_location=loc,
        impact_zone=impact,
        severity_score=6.5,
        severity_level=SeverityLevel.HIGH,
        confidence=0.75,
        created_at=now,
        updated_at=now,
    )
    assert cluster.situation_id == "SIT-TEST1234"
    assert cluster.report_count == 1
    assert cluster.severity_level == SeverityLevel.HIGH

    # Invalid latitude raises ValidationError
    with pytest.raises(ValidationError):
        SituationLocationCenter(latitude=95.0, longitude=80.0)

    # Invalid severity score (> 10.0) raises ValidationError
    with pytest.raises(ValidationError):
        SituationAssessment(
            situation_id="SIT-TEST1234",
            severity_score=11.5,
            severity_level=SeverityLevel.CRITICAL,
            estimated_affected_population=500,
            impact_radius_km=3.0,
            hazard_risk="Flood",
            situation_summary="Summary",
            confidence=0.8,
            created_at=now,
            updated_at=now,
        )

    # Invalid confidence score (> 1.0) raises ValidationError
    with pytest.raises(ValidationError):
        SituationAssessment(
            situation_id="SIT-TEST1234",
            severity_score=7.0,
            severity_level=SeverityLevel.HIGH,
            estimated_affected_population=500,
            impact_radius_km=3.0,
            hazard_risk="Flood",
            situation_summary="Summary",
            confidence=1.5,
            created_at=now,
            updated_at=now,
        )


# --------------------------------------------------------------------------
# 2. Severity Engine & Explainable Calculations
# --------------------------------------------------------------------------
@pytest.mark.anyio
async def test_explainable_severity_engine():
    """Test explainable severity calculation, keyword matching, count weighting, and officer ground truth."""
    # 1. Base weights
    base_score, level, factors = calculate_explainable_severity(
        emergency_type=EmergencyType.BUILDING_COLLAPSE.value,
        descriptions=["Building damaged."],
        report_count=1,
    )
    assert base_score == BASE_EMERGENCY_SEVERITY[EmergencyType.BUILDING_COLLAPSE.value]
    assert level == SeverityLevel.HIGH
    assert any("Base category weight" in f for f in factors)

    # 2. Critical situational keywords boost
    crit_score, crit_level, crit_factors = calculate_explainable_severity(
        emergency_type=EmergencyType.BUILDING_COLLAPSE.value,
        descriptions=["Multiple people trapped under rubble, critical condition casualties reported!"],
        report_count=1,
    )
    assert crit_score >= 8.0
    assert crit_level == SeverityLevel.CRITICAL
    assert any("trapped" in f.lower() for f in crit_factors)

    # 3. Report density escalation
    dense_score, dense_level, dense_factors = calculate_explainable_severity(
        emergency_type=EmergencyType.FLOOD.value,
        descriptions=["Water rising in street."] * 8,
        report_count=8,
    )
    assert dense_score > BASE_EMERGENCY_SEVERITY[EmergencyType.FLOOD.value]
    assert any("High report density" in f for f in dense_factors)

    # 4. Officer priority ground truth respect
    officer_score, officer_level, officer_factors = calculate_explainable_severity(
        emergency_type=EmergencyType.OTHER.value,
        descriptions=["Minor issue."],
        report_count=1,
        officer_priorities=[ReportPriority.CRITICAL.value],
    )
    assert officer_score >= 8.2
    assert officer_level == SeverityLevel.CRITICAL
    assert any("confirmed CRITICAL officer priority" in f for f in officer_factors)


# --------------------------------------------------------------------------
# 3. Evidence-Based Confidence Metric Tests
# --------------------------------------------------------------------------
@pytest.mark.anyio
async def test_evidence_confidence_calculation():
    """Test evidence confidence formula based on corroboration, detail, media, geocoding, and officer triage."""
    # Low evidence: 1 report, short description, no media, not geocoded
    low_conf = calculate_evidence_confidence(
        report_count=1,
        has_geocoded_address=False,
        media_count=0,
        avg_description_len=20,
        officer_triaged=False,
    )
    assert low_conf <= 0.55

    # High evidence: 5+ reports, detailed description, media proof, geocoded, officer triaged
    high_conf = calculate_evidence_confidence(
        report_count=5,
        has_geocoded_address=True,
        media_count=3,
        avg_description_len=200,
        officer_triaged=True,
    )
    assert high_conf >= 0.85
    assert high_conf <= 0.98


# --------------------------------------------------------------------------
# 4. Deterministic Clustering & Fusion Logic Tests
# --------------------------------------------------------------------------
@pytest.mark.anyio
async def test_emergency_type_compatibility():
    """Test compatibility rules for compound disaster clustering."""
    # Same types are always compatible
    assert are_emergency_types_cluster_compatible(EmergencyType.FLOOD.value, EmergencyType.FLOOD.value, 1.5) is True
    
    # Building collapse and landslide within 1.0 km are compatible
    assert are_emergency_types_cluster_compatible(EmergencyType.BUILDING_COLLAPSE.value, EmergencyType.LANDSLIDE.value, 0.5) is True
    
    # Building collapse and landslide > 1.0 km are NOT compatible
    assert are_emergency_types_cluster_compatible(EmergencyType.BUILDING_COLLAPSE.value, EmergencyType.LANDSLIDE.value, 2.0) is False
    
    # Medical Emergency and Fire are NOT compatible
    assert are_emergency_types_cluster_compatible(EmergencyType.MEDICAL_EMERGENCY.value, EmergencyType.FIRE.value, 0.2) is False


@pytest.mark.anyio
async def test_calculate_cluster_centroid_and_radius():
    """Test geometric centroid and estimated impact radius calculation."""
    reports = [
        {"location": {"latitude": 16.2400, "longitude": 80.6400}},
        {"location": {"latitude": 16.2500, "longitude": 80.6500}},
    ]
    center_lat, center_lon, radius, bbox = calculate_cluster_centroid_and_radius(reports, EmergencyType.FLOOD.value)
    
    assert center_lat == 16.2450
    assert center_lon == 80.6450
    assert radius >= 2.0  # Base minimum for flood is 2.0 km
    assert bbox["min_lat"] == 16.2400
    assert bbox["max_lat"] == 16.2500


# --------------------------------------------------------------------------
# 5. AI Output Validation Schema Tests
# --------------------------------------------------------------------------
@pytest.mark.anyio
async def test_raw_ai_output_schema_validation():
    """Test strict validation of untrusted LLM assessment output."""
    valid_payload = {
        "situation_summary": "Extensive urban flooding observed across sector 4, isolating ground floor residents.",
        "severity_score": 7.5,
        "severity_level": "HIGH",
        "estimated_affected_population": 1200,
        "impact_radius_km": 3.2,
        "hazard_risk": "Submersion of arterial roads, electrical short circuits.",
        "key_factors": ["Rising floodwaters", "Access routes submerged"],
        "confidence": 0.82,
        "recommendations": ["Deploy inflatable rescue boats", "Establish relief camp on high ground"],
    }
    validated = RawAISituationAssessmentSchema(**valid_payload)
    assert validated.severity_score == 7.5
    assert validated.severity_level == SeverityLevel.HIGH

    # Invalid severity score (> 10.0) rejected
    invalid_score = dict(valid_payload, severity_score=15.0)
    with pytest.raises(ValidationError):
        RawAISituationAssessmentSchema(**invalid_score)

    # Invalid confidence (> 1.0) rejected
    invalid_conf = dict(valid_payload, confidence=1.2)
    with pytest.raises(ValidationError):
        RawAISituationAssessmentSchema(**invalid_conf)


# --------------------------------------------------------------------------
# 6. End-to-End Incident Fusion & Assessment Tests
# --------------------------------------------------------------------------
@pytest.mark.anyio
async def test_citizen_report_auto_fuses_into_situation(client: AsyncClient):
    """Test that submitting a real citizen report automatically creates or fuses into a SituationCluster."""
    headers = await get_officer_headers(client)
    phone = f"987{uuid.uuid4().int % 10000000:07d}"
    
    report_payload = {
        "full_name": "Ravi Shankar",
        "phone": phone,
        "emergency_type": EmergencyType.FIRE.value,
        "description": "Industrial warehouse fire spreading rapidly near Main Market, heavy smoke engulfing surrounding area.",
        "location": {
            "latitude": 16.3000,
            "longitude": 80.4500,
            "address": "Industrial Area, Phase 2",
            "street_address": "Plot 45, Main Road",
            "city": "Guntur",
            "zone_or_district": "West Industrial Zone",
        },
        "media": [],
    }

    res = await client.post("/api/v1/citizen/reports", json=report_payload)
    assert res.status_code == 201, res.text
    report_data = res.json()
    rep_id = report_data["report_id"]

    # Verify report detail via officer API has situation_id
    rep_detail_res = await client.get(f"/api/v1/officer/reports/{rep_id}", headers=headers)
    assert rep_detail_res.status_code == 200
    rep_detail = rep_detail_res.json()
    sit_id = rep_detail.get("situation_id")
    assert sit_id is not None
    assert sit_id.startswith("SIT-")

    # Verify situation cluster via officer API
    sit_res = await client.get(f"/api/v1/officer/situations/{sit_id}", headers=headers)
    assert sit_res.status_code == 200
    situation_obj = sit_res.json()["situation"]
    assert situation_obj["emergency_type"] == EmergencyType.FIRE.value
    assert rep_id in situation_obj["report_ids"]
    assert situation_obj["report_count"] == 1
    assert situation_obj["severity_score"] >= 6.5


@pytest.mark.anyio
async def test_multiple_reports_clustering_and_separation(client: AsyncClient):
    """
    Test that nearby compatible reports are clustered together,
    while distant or incompatible reports create separate situation clusters.
    """
    headers = await get_officer_headers(client)
    phone1 = f"987{uuid.uuid4().int % 10000000:07d}"
    phone2 = f"987{uuid.uuid4().int % 10000000:07d}"
    phone3 = f"987{uuid.uuid4().int % 10000000:07d}"
    phone4 = f"987{uuid.uuid4().int % 10000000:07d}"
    
    # Report 1: Flood at (16.2000, 80.6000)
    rep1_res = await client.post("/api/v1/citizen/reports", json={
        "full_name": "Citizen A",
        "phone": phone1,
        "emergency_type": EmergencyType.FLOOD.value,
        "description": "Rising water in colony, 3 feet deep.",
        "location": {"latitude": 16.2000, "longitude": 80.6000, "city": "Guntur"},
    })
    assert rep1_res.status_code == 201
    rep1_id = rep1_res.json()["report_id"]

    # Report 2: Flood at (16.2050, 80.6050) -> ~0.75 km away from Report 1 (Compatible + Close)
    rep2_res = await client.post("/api/v1/citizen/reports", json={
        "full_name": "Citizen B",
        "phone": phone2,
        "emergency_type": EmergencyType.FLOOD.value,
        "description": "Water entering homes nearby, multiple families stranded.",
        "location": {"latitude": 16.2050, "longitude": 80.6050, "city": "Guntur"},
    })
    assert rep2_res.status_code == 201
    rep2_id = rep2_res.json()["report_id"]

    # Report 3: Medical Emergency at (16.2010, 80.6010) -> Incompatible emergency type
    rep3_res = await client.post("/api/v1/citizen/reports", json={
        "full_name": "Citizen C",
        "phone": phone3,
        "emergency_type": EmergencyType.MEDICAL_EMERGENCY.value,
        "description": "Elderly patient having severe chest pain.",
        "location": {"latitude": 16.2010, "longitude": 80.6010, "city": "Guntur"},
    })
    assert rep3_res.status_code == 201
    rep3_id = rep3_res.json()["report_id"]

    # Report 4: Flood at (16.4500, 80.8500) -> > 35 km away (Geographically distant)
    rep4_res = await client.post("/api/v1/citizen/reports", json={
        "full_name": "Citizen D",
        "phone": phone4,
        "emergency_type": EmergencyType.FLOOD.value,
        "description": "River embankment breached in rural sector.",
        "location": {"latitude": 16.4500, "longitude": 80.8500, "city": "Distant Suburb"},
    })
    assert rep4_res.status_code == 201
    rep4_id = rep4_res.json()["report_id"]

    # Retrieve report details via officer endpoint
    r1_doc = (await client.get(f"/api/v1/officer/reports/{rep1_id}", headers=headers)).json()
    r2_doc = (await client.get(f"/api/v1/officer/reports/{rep2_id}", headers=headers)).json()
    r3_doc = (await client.get(f"/api/v1/officer/reports/{rep3_id}", headers=headers)).json()
    r4_doc = (await client.get(f"/api/v1/officer/reports/{rep4_id}", headers=headers)).json()

    # Verify Report 1 & 2 share the SAME situation cluster
    assert r1_doc["situation_id"] == r2_doc["situation_id"]
    shared_sit = (await client.get(f"/api/v1/officer/situations/{r1_doc['situation_id']}", headers=headers)).json()["situation"]
    assert shared_sit["report_count"] == 2
    assert rep1_id in shared_sit["report_ids"]
    assert rep2_id in shared_sit["report_ids"]

    # Verify Report 3 (Medical) is in a SEPARATE situation cluster
    assert r3_doc["situation_id"] != r1_doc["situation_id"]

    # Verify Report 4 (Distant Flood) is in a SEPARATE situation cluster
    assert r4_doc["situation_id"] != r1_doc["situation_id"]


# --------------------------------------------------------------------------
# 7. Officer Situation Intelligence API & Review Endpoints
# --------------------------------------------------------------------------
@pytest.mark.anyio
async def test_officer_situation_apis_and_review(client: AsyncClient):
    """Test officer viewing situations, stats, triggering assessment, and performing human-in-the-loop review."""
    headers = await get_officer_headers(client)

    # 1. Get stats
    stats_res = await client.get("/api/v1/officer/situations/stats", headers=headers)
    assert stats_res.status_code == 200
    stats_data = stats_res.json()
    assert "total_situations" in stats_data
    assert "active_situations" in stats_data
    assert "total_clustered_reports" in stats_data

    # 2. List situations
    list_res = await client.get("/api/v1/officer/situations", headers=headers)
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert len(items) > 0
    test_sit_id = items[0]["situation_id"]

    # 3. Get situation detail with member reports
    detail_res = await client.get(f"/api/v1/officer/situations/{test_sit_id}", headers=headers)
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["situation"]["situation_id"] == test_sit_id
    assert len(detail_data["clustered_reports"]) > 0

    # 4. Trigger / refresh situation assessment
    assess_res = await client.post(f"/api/v1/officer/situations/{test_sit_id}/assess", headers=headers)
    assert assess_res.status_code == 200
    assessed_situation = assess_res.json()
    assert assessed_situation["assessment_status"] == AssessmentStatus.COMPLETED.value
    assert assessed_situation["assessment"] is not None
    assert "situation_summary" in assessed_situation["assessment"]

    # 5. Officer Review: ACCEPT
    accept_res = await client.post(
        f"/api/v1/officer/situations/{test_sit_id}/review",
        json={"action": OfficerReviewAction.ACCEPT.value, "notes": "On-ground assessment verified by field scout."},
        headers=headers,
    )
    assert accept_res.status_code == 200
    accepted_sit = accept_res.json()
    assert accepted_sit["assessment_status"] == AssessmentStatus.REVIEWED.value
    assert accepted_sit["officer_review"]["action"] == OfficerReviewAction.ACCEPT.value

    # 6. Officer Review: MODIFY (override severity)
    modify_res = await client.post(
        f"/api/v1/officer/situations/{test_sit_id}/review",
        json={
            "action": OfficerReviewAction.MODIFY.value,
            "modified_severity_level": SeverityLevel.CRITICAL.value,
            "modified_severity_score": 9.2,
            "notes": "Escalating severity due to uncontained chemical smoke plume.",
        },
        headers=headers,
    )
    assert modify_res.status_code == 200
    modified_sit = modify_res.json()
    assert modified_sit["severity_level"] == SeverityLevel.CRITICAL.value
    assert modified_sit["severity_score"] == 9.2

    # 7. Get Situation Timeline
    timeline_res = await client.get(f"/api/v1/officer/situations/{test_sit_id}/timeline", headers=headers)
    assert timeline_res.status_code == 200
    events = timeline_res.json()
    assert len(events) > 0


# --------------------------------------------------------------------------
# 8. RBAC Security Tests for Situation Intelligence
# --------------------------------------------------------------------------
@pytest.mark.anyio
async def test_rbac_security_on_situation_endpoints(client: AsyncClient):
    """Ensure unauthenticated and citizen users cannot access officer situation routes."""
    # Unauthenticated -> 401
    res = await client.get("/api/v1/officer/situations")
    assert res.status_code == 401

    res = await client.get("/api/v1/officer/situations/stats")
    assert res.status_code == 401

    res = await client.post("/api/v1/officer/situations/SIT-TEST/assess")
    assert res.status_code == 401


# --------------------------------------------------------------------------
# 9. AI Fallback & Timeout Resilience Tests
# --------------------------------------------------------------------------
@pytest.mark.anyio
async def test_situation_assessment_deterministic_fallback():
    """Ensure assessment functions smoothly with deterministic synthesis when AI is offline or timeout occurs."""
    now = datetime.now(timezone.utc)
    cluster = SituationCluster(
        situation_id="SIT-FALLBACK1",
        cluster_id="CLS-FALLBACK1",
        title="Landslide at Mountain Pass",
        emergency_type=EmergencyType.LANDSLIDE,
        primary_report_id="REP-FB001",
        report_ids=["REP-FB001"],
        report_count=1,
        center_location=SituationLocationCenter(latitude=16.5, longitude=80.5, city="Hill District"),
        impact_zone=ImpactZone(center_latitude=16.5, center_longitude=80.5, radius_km=1.0),
        severity_score=6.5,
        severity_level=SeverityLevel.HIGH,
        created_at=now,
        updated_at=now,
    )
    reports = [
        {
            "report_id": "REP-FB001",
            "emergency_type": EmergencyType.LANDSLIDE.value,
            "description": "Road blocked by heavy debris, rocks falling.",
            "location": {"latitude": 16.5, "longitude": 80.5, "address": "Mountain Highway"},
        }
    ]

    # Generate deterministic assessment
    assessment = generate_deterministic_situation_assessment(cluster, reports)
    assert assessment is not None
    assert assessment.situation_id == "SIT-FALLBACK1"
    assert assessment.severity_level == SeverityLevel.HIGH
    assert assessment.confidence >= 0.20
    assert len(assessment.recommendations) > 0
    assert len(assessment.key_factors) > 0


# --------------------------------------------------------------------------
# 10. Non-Destructive Invariance & Zero Inventory Modification Tests
# --------------------------------------------------------------------------
@pytest.mark.anyio
async def test_situation_assessment_does_not_mutate_resources(client: AsyncClient):
    """
    Verify that Situation Intelligence is strictly advisory:
    Creating/assessing situations must NEVER modify resource inventory or dispatch resources.
    """
    headers = await get_officer_headers(client)

    # 1. Get resources list before
    res_before = await client.get("/api/v1/resources", headers=headers)
    assert res_before.status_code == 200
    res_items_before = res_before.json().get("items", [])

    # 2. Run fuse-all and assess situations
    fuse_res = await client.post("/api/v1/officer/situations/fuse-all", headers=headers)
    assert fuse_res.status_code == 200

    # 3. Get resources list after
    res_after = await client.get("/api/v1/resources", headers=headers)
    assert res_after.status_code == 200
    res_items_after = res_after.json().get("items", [])

    assert len(res_items_before) == len(res_items_after)


# --------------------------------------------------------------------------
# 11. Regression Tests: Officer Severity Override Persistence & Refresh
# --------------------------------------------------------------------------
@pytest.mark.anyio
async def test_officer_severity_override_persists_after_refresh(client: AsyncClient):
    """
    Core bug fix test:
    AI / Deterministic Severity (e.g. HIGH) -> Officer explicitly modifies to CRITICAL
    -> Save/Review -> Refresh Assessment
    -> Operational severity MUST REMAIN CRITICAL.
    """
    headers = await get_officer_headers(client)
    phone = f"987{uuid.uuid4().int % 10000000:07d}"

    # 1. Create citizen report
    rep_res = await client.post("/api/v1/citizen/reports", json={
        "full_name": "Override Test Citizen",
        "phone": phone,
        "emergency_type": EmergencyType.FLOOD.value,
        "description": "Standard water logging in residential street.",
        "location": {"latitude": 16.3100, "longitude": 80.4400, "city": "Guntur"},
    })
    assert rep_res.status_code == 201
    rep_id = rep_res.json()["report_id"]

    # Retrieve situation ID
    rep_doc = (await client.get(f"/api/v1/officer/reports/{rep_id}", headers=headers)).json()
    sit_id = rep_doc["situation_id"]

    # Initial assessment
    init_assess = (await client.post(f"/api/v1/officer/situations/{sit_id}/assess", headers=headers)).json()
    initial_severity = init_assess["severity_level"]
    assert initial_severity in [SeverityLevel.MEDIUM.value, SeverityLevel.HIGH.value]

    # 2. Officer explicitly overrides severity to CRITICAL
    modify_res = await client.post(
        f"/api/v1/officer/situations/{sit_id}/review",
        json={
            "action": OfficerReviewAction.MODIFY.value,
            "modified_severity_level": SeverityLevel.CRITICAL.value,
            "modified_severity_score": 9.5,
            "notes": "Emergency Officer elevated severity to CRITICAL due to compromised embankment.",
        },
        headers=headers,
    )
    assert modify_res.status_code == 200
    modified_sit = modify_res.json()
    assert modified_sit["severity_level"] == SeverityLevel.CRITICAL.value
    assert modified_sit["severity_score"] == 9.5
    assert modified_sit["officer_override_severity"] == SeverityLevel.CRITICAL.value
    assert modified_sit["officer_override_score"] == 9.5
    assert modified_sit["officer_override_by"] is not None

    # 3. Officer clicks 'Refresh Assessment'
    refresh_res = await client.post(f"/api/v1/officer/situations/{sit_id}/assess", headers=headers)
    assert refresh_res.status_code == 200
    refreshed_sit = refresh_res.json()

    # MUST REMAIN CRITICAL
    assert refreshed_sit["severity_level"] == SeverityLevel.CRITICAL.value
    assert refreshed_sit["severity_score"] == 9.5
    assert refreshed_sit["officer_override_severity"] == SeverityLevel.CRITICAL.value
    assert refreshed_sit["computed_severity_level"] == initial_severity
    assert refreshed_sit["assessment"]["severity_level"] == initial_severity


@pytest.mark.anyio
async def test_refresh_without_override_uses_computed_severity(client: AsyncClient):
    """
    When NO officer override exists, Refresh Assessment updates both computed and operational severity.
    """
    headers = await get_officer_headers(client)
    phone = f"987{uuid.uuid4().int % 10000000:07d}"

    rep_res = await client.post("/api/v1/citizen/reports", json={
        "full_name": "No Override Citizen",
        "phone": phone,
        "emergency_type": EmergencyType.MEDICAL_EMERGENCY.value,
        "description": "Patient experiencing severe trauma.",
        "location": {"latitude": 16.3200, "longitude": 80.4600, "city": "Guntur"},
    })
    assert rep_res.status_code == 201
    rep_id = rep_res.json()["report_id"]

    rep_doc = (await client.get(f"/api/v1/officer/reports/{rep_id}", headers=headers)).json()
    sit_id = rep_doc["situation_id"]

    refresh_res = await client.post(f"/api/v1/officer/situations/{sit_id}/assess", headers=headers)
    assert refresh_res.status_code == 200
    sit_data = refresh_res.json()
    assert sit_data["officer_override_severity"] is None
    assert sit_data["severity_level"] == sit_data["computed_severity_level"]
    assert sit_data["severity_score"] == sit_data["computed_severity_score"]


@pytest.mark.anyio
async def test_override_survives_situation_reopen_and_api_refetch(client: AsyncClient):
    """
    Verify that when modal is closed, reopened, or list is refetched,
    the persisted officer override severity is authoritatively returned.
    """
    headers = await get_officer_headers(client)
    phone = f"987{uuid.uuid4().int % 10000000:07d}"

    rep_res = await client.post("/api/v1/citizen/reports", json={
        "full_name": "Reopen Test Citizen",
        "phone": phone,
        "emergency_type": EmergencyType.FIRE.value,
        "description": "Small grass fire near perimeter fence.",
        "location": {"latitude": 16.3300, "longitude": 80.4700, "city": "Guntur"},
    })
    assert rep_res.status_code == 201
    sit_id = (await client.get(f"/api/v1/officer/reports/{rep_res.json()['report_id']}", headers=headers)).json()["situation_id"]

    # Modify to LOW
    await client.post(
        f"/api/v1/officer/situations/{sit_id}/review",
        json={
            "action": OfficerReviewAction.MODIFY.value,
            "modified_severity_level": SeverityLevel.LOW.value,
            "modified_severity_score": 2.5,
            "notes": "Grass fire already extinguished by locals. Severity lowered.",
        },
        headers=headers,
    )

    # Reopen situation detail
    detail_res = await client.get(f"/api/v1/officer/situations/{sit_id}", headers=headers)
    assert detail_res.status_code == 200
    situation_obj = detail_res.json()["situation"]
    assert situation_obj["severity_level"] == SeverityLevel.LOW.value
    assert situation_obj["severity_score"] == 2.5
    assert situation_obj["officer_override_severity"] == SeverityLevel.LOW.value

    # List situations
    list_res = await client.get(f"/api/v1/officer/situations?search={sit_id}", headers=headers)
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    matched = [s for s in items if s["situation_id"] == sit_id]
    assert len(matched) == 1
    assert matched[0]["severity_level"] == SeverityLevel.LOW.value
    assert matched[0]["officer_override_severity"] == SeverityLevel.LOW.value


@pytest.mark.anyio
async def test_computed_severity_can_change_without_overwriting_override(client: AsyncClient):
    """
    When new reports arrive and fuse into a situation cluster,
    computed severity recalculates, but operational severity remains the officer override.
    """
    headers = await get_officer_headers(client)
    phone1 = f"987{uuid.uuid4().int % 10000000:07d}"
    phone2 = f"987{uuid.uuid4().int % 10000000:07d}"

    # Report 1
    r1 = await client.post("/api/v1/citizen/reports", json={
        "full_name": "Multi Report Citizen 1",
        "phone": phone1,
        "emergency_type": EmergencyType.FLOOD.value,
        "description": "Flooding on street.",
        "location": {"latitude": 16.8800, "longitude": 81.2200, "city": "Isolated Sector"},
    })
    sit_id = (await client.get(f"/api/v1/officer/reports/{r1.json()['report_id']}", headers=headers)).json()["situation_id"]

    # Officer sets override to HIGH
    await client.post(
        f"/api/v1/officer/situations/{sit_id}/review",
        json={
            "action": OfficerReviewAction.MODIFY.value,
            "modified_severity_level": SeverityLevel.HIGH.value,
            "modified_severity_score": 7.5,
            "notes": "Officer manual override to HIGH.",
        },
        headers=headers,
    )

    # Report 2 arrives nearby -> fuses into same situation
    r2 = await client.post("/api/v1/citizen/reports", json={
        "full_name": "Multi Report Citizen 2",
        "phone": phone2,
        "emergency_type": EmergencyType.FLOOD.value,
        "description": "Water rising rapidly, trapped occupants.",
        "location": {"latitude": 16.8820, "longitude": 81.2210, "city": "Isolated Sector"},
    })
    assert r2.status_code == 201

    # Check situation after fusion
    sit_res = await client.get(f"/api/v1/officer/situations/{sit_id}", headers=headers)
    sit_obj = sit_res.json()["situation"]
    assert sit_obj["report_count"] >= 2
    assert r1.json()["report_id"] in sit_obj["report_ids"]
    assert r2.json()["report_id"] in sit_obj["report_ids"]
    # Operational severity still HIGH from officer override
    assert sit_obj["severity_level"] == SeverityLevel.HIGH.value
    assert sit_obj["severity_score"] == 7.5
    assert sit_obj["officer_override_severity"] == SeverityLevel.HIGH.value


@pytest.mark.anyio
async def test_only_authenticated_officer_can_modify_override(client: AsyncClient):
    """
    Ensure unauthorized or non-officer users cannot modify situation severity override.
    """
    phone = f"987{uuid.uuid4().int % 10000000:07d}"
    rep_res = await client.post("/api/v1/citizen/reports", json={
        "full_name": "Security Check Citizen",
        "phone": phone,
        "emergency_type": EmergencyType.FIRE.value,
        "description": "Small fire incident.",
        "location": {"latitude": 16.2900, "longitude": 80.4900, "city": "Guntur"},
    })
    sit_id = "SIT-SECURITYTEST"

    # Unauthenticated attempt -> 401
    res = await client.post(
        f"/api/v1/officer/situations/{sit_id}/review",
        json={"action": OfficerReviewAction.MODIFY.value, "modified_severity_level": SeverityLevel.CRITICAL.value},
    )
    assert res.status_code == 401


@pytest.mark.anyio
async def test_no_synthetic_actor_created(client: AsyncClient):
    """
    Verify that timeline audit records for officer override and refresh
    contain the exact authenticated officer identity and no synthetic/dummy actors.
    """
    headers = await get_officer_headers(client)
    phone = f"987{uuid.uuid4().int % 10000000:07d}"

    rep_res = await client.post("/api/v1/citizen/reports", json={
        "full_name": "Audit Real Actor Citizen",
        "phone": phone,
        "emergency_type": EmergencyType.LANDSLIDE.value,
        "description": "Small earth slip on roadside.",
        "location": {"latitude": 16.2800, "longitude": 80.4800, "city": "Guntur"},
    })
    sit_id = (await client.get(f"/api/v1/officer/reports/{rep_res.json()['report_id']}", headers=headers)).json()["situation_id"]

    # Modify severity
    await client.post(
        f"/api/v1/officer/situations/{sit_id}/review",
        json={
            "action": OfficerReviewAction.MODIFY.value,
            "modified_severity_level": SeverityLevel.CRITICAL.value,
            "modified_severity_score": 9.0,
            "notes": "Elevated for road safety.",
        },
        headers=headers,
    )

    # Refresh
    await client.post(f"/api/v1/officer/situations/{sit_id}/assess", headers=headers)

    # Inspect timeline
    timeline_res = await client.get(f"/api/v1/officer/situations/{sit_id}/timeline", headers=headers)
    assert timeline_res.status_code == 200
    events = timeline_res.json()
    assert len(events) > 0

    for ev in events:
        actor_name = ev.get("actor_name")
        if actor_name:
            assert "synthetic" not in actor_name.lower()
            assert "dummy" not in actor_name.lower()
            assert "fake" not in actor_name.lower()
            assert "mock" not in actor_name.lower()


@pytest.mark.anyio
async def test_officer_can_reset_override_to_computed_severity(client: AsyncClient):
    """
    Verify that an officer can explicitly reset/remove the override,
    causing the system to return to the computed severity baseline.
    """
    headers = await get_officer_headers(client)
    phone = f"987{uuid.uuid4().int % 10000000:07d}"

    rep_res = await client.post("/api/v1/citizen/reports", json={
        "full_name": "Reset Test Citizen",
        "phone": phone,
        "emergency_type": EmergencyType.ROAD_ACCIDENT.value,
        "description": "Two vehicle collision, minor damage.",
        "location": {"latitude": 16.2700, "longitude": 80.4700, "city": "Guntur"},
    })
    sit_id = (await client.get(f"/api/v1/officer/reports/{rep_res.json()['report_id']}", headers=headers)).json()["situation_id"]

    # Assess
    assess_res = (await client.post(f"/api/v1/officer/situations/{sit_id}/assess", headers=headers)).json()
    computed_sev = assess_res["computed_severity_level"]

    # Override to CRITICAL
    await client.post(
        f"/api/v1/officer/situations/{sit_id}/review",
        json={
            "action": OfficerReviewAction.MODIFY.value,
            "modified_severity_level": SeverityLevel.CRITICAL.value,
            "modified_severity_score": 9.5,
        },
        headers=headers,
    )
    sit_overridden = (await client.get(f"/api/v1/officer/situations/{sit_id}", headers=headers)).json()["situation"]
    assert sit_overridden["severity_level"] == SeverityLevel.CRITICAL.value

    # Reset override
    reset_res = await client.post(
        f"/api/v1/officer/situations/{sit_id}/review",
        json={
            "action": OfficerReviewAction.ACCEPT.value,
            "reset_override": True,
            "notes": "Resetting override back to AI baseline.",
        },
        headers=headers,
    )
    assert reset_res.status_code == 200
    sit_reset = reset_res.json()
    assert sit_reset["officer_override_severity"] is None
    assert sit_reset["severity_level"] == computed_sev

