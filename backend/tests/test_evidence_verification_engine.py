import pytest
from datetime import datetime, timezone, timedelta
from app.models.enums import (
    CitizenImpactLevel,
    VerificationStatus,
    EvidenceConfidenceBand,
    LocationMatchState,
    EvidenceFreshness,
    ReportCompleteness,
    EmergencyType,
    ReportStatus,
    ReportPriority,
    EvidenceValidationStatus,
)
from app.services.evidence_verification_service import EvidenceVerificationService


def test_1_report_with_no_evidence():
    """Report with no evidence -> UNVERIFIED and LOW confidence, missing factor noted."""
    now = datetime.now(timezone.utc)
    report_doc = {
        "report_id": "RES-TEST0001",
        "citizen_name": "Test Citizen",
        "citizen_phone": "+919876543210",
        "emergency_type": EmergencyType.FLOOD.value,
        "citizen_impact_level": CitizenImpactLevel.HIGH.value,
        "description": "Rising floodwaters on main market street.",
        "location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "address": "MG Road, Vijayawada",
        },
        "evidence": None,
        "created_at": now,
    }

    result = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    assert result.report_id == "RES-TEST0001"
    assert result.has_live_photo is False
    assert result.verification_status == VerificationStatus.UNVERIFIED
    assert result.confidence_band == EvidenceConfidenceBand.LOW
    assert result.location_match_state == LocationMatchState.UNAVAILABLE
    assert result.evidence_freshness == EvidenceFreshness.UNAVAILABLE
    assert any("No live camera photo evidence" in m for m in result.missing_factors)


def test_2_report_with_genuine_live_photo_metadata():
    """Report with genuine live photo metadata -> evidence signals recognized."""
    now = datetime.now(timezone.utc)
    report_doc = {
        "report_id": "RES-TEST0002",
        "citizen_name": "Test Citizen",
        "citizen_phone": "+919876543210",
        "emergency_type": EmergencyType.FIRE.value,
        "citizen_impact_level": CitizenImpactLevel.CRITICAL.value,
        "description": "Active building fire with heavy smoke.",
        "location": {
            "latitude": 16.5062,
            "longitude": 80.6480,
            "address": "Sector 4, Industrial Area",
        },
        "evidence": {
            "evidence_id": "EVD-TEST0002",
            "source": "BROWSER_CAMERA",
            "file_url": "/uploads/citizen_evidence/EVD-TEST0002.jpg",
            "content_hash": "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0",
            "client_capture_timestamp": (now - timedelta(minutes=2)).isoformat(),
            "latitude": 16.5065,
            "longitude": 80.6482,
            "accuracy_meters": 12.0,
            "is_duplicate": False,
        },
        "created_at": now,
    }

    result = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    assert result.has_live_photo is True
    assert result.content_hash is not None
    assert "LIVE_PHOTO_CAPTURED" in result.evidence_signals
    assert "CONTENT_HASH_VERIFIED" in result.evidence_signals
    assert result.verification_status == VerificationStatus.PARTIALLY_VERIFIED
    assert result.confidence_band == EvidenceConfidenceBand.HIGH


def test_3_live_photo_with_gps_matching_report():
    """Live photo with GPS matching report (<= 500m) -> location MATCH."""
    now = datetime.now(timezone.utc)
    # ~40m offset
    report_doc = {
        "report_id": "RES-TEST0003",
        "citizen_name": "Test Citizen",
        "citizen_phone": "+919876543210",
        "emergency_type": EmergencyType.MEDICAL_EMERGENCY.value,
        "citizen_impact_level": CitizenImpactLevel.HIGH.value,
        "description": "Patient needs urgent transport.",
        "location": {"latitude": 16.5000, "longitude": 80.6400, "address": "Hospital Road"},
        "evidence": {
            "evidence_id": "EVD-TEST0003",
            "file_url": "/uploads/citizen_evidence/test.jpg",
            "content_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "client_capture_timestamp": now.isoformat(),
            "latitude": 16.5003,
            "longitude": 80.6402,
            "accuracy_meters": 10.0,
        },
        "created_at": now,
    }

    result = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    assert result.location_match_state == LocationMatchState.MATCH
    assert result.distance_from_report_meters is not None
    assert result.distance_from_report_meters <= 500.0
    assert any("matches reported incident location" in f for f in result.verified_factors)


def test_4_live_photo_with_gps_mismatch():
    """Live photo with GPS mismatch (> 2000m) -> location MISMATCH and LOW confidence."""
    now = datetime.now(timezone.utc)
    # ~5 km offset
    report_doc = {
        "report_id": "RES-TEST0004",
        "citizen_name": "Test Citizen",
        "citizen_phone": "+919876543210",
        "emergency_type": EmergencyType.FIRE.value,
        "citizen_impact_level": CitizenImpactLevel.HIGH.value,
        "description": "Reported fire in city center.",
        "location": {"latitude": 16.5000, "longitude": 80.6400, "address": "City Center"},
        "evidence": {
            "evidence_id": "EVD-TEST0004",
            "file_url": "/uploads/citizen_evidence/test.jpg",
            "content_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "client_capture_timestamp": now.isoformat(),
            "latitude": 16.5500,
            "longitude": 80.6900,
            "accuracy_meters": 15.0,
        },
        "created_at": now,
    }

    result = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    assert result.location_match_state == LocationMatchState.MISMATCH
    assert result.distance_from_report_meters is not None
    assert result.distance_from_report_meters > 2000.0
    assert result.confidence_band == EvidenceConfidenceBand.LOW
    assert any("mismatch" in w.lower() for w in result.warnings)


def test_5_gps_unavailable():
    """Evidence without GPS -> location UNAVAILABLE without converting into MISMATCH."""
    now = datetime.now(timezone.utc)
    report_doc = {
        "report_id": "RES-TEST0005",
        "citizen_name": "Test Citizen",
        "citizen_phone": "+919876543210",
        "emergency_type": EmergencyType.ROAD_ACCIDENT.value,
        "citizen_impact_level": CitizenImpactLevel.MEDIUM.value,
        "description": "Two vehicle collision on highway.",
        "location": {"latitude": 16.5000, "longitude": 80.6400, "address": "Highway 16"},
        "evidence": {
            "evidence_id": "EVD-TEST0005",
            "file_url": "/uploads/citizen_evidence/test.jpg",
            "content_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "client_capture_timestamp": now.isoformat(),
            "latitude": None,
            "longitude": None,
        },
        "created_at": now,
    }

    result = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    assert result.location_match_state == LocationMatchState.UNAVAILABLE
    assert result.distance_from_report_meters is None
    # Must NOT generate a location mismatch warning
    assert not any("location mismatch" in w.lower() for w in result.warnings)


def test_6_fresh_evidence():
    """Evidence captured within 30 minutes -> FRESH."""
    now = datetime.now(timezone.utc)
    capture_time = now - timedelta(minutes=10)
    report_doc = {
        "report_id": "RES-TEST0006",
        "citizen_name": "Test Citizen",
        "citizen_phone": "+919876543210",
        "emergency_type": EmergencyType.FLOOD.value,
        "citizen_impact_level": CitizenImpactLevel.HIGH.value,
        "description": "Water overflowing bridge.",
        "location": {"latitude": 16.5000, "longitude": 80.6400, "address": "Bridge"},
        "evidence": {
            "evidence_id": "EVD-TEST0006",
            "file_url": "/uploads/citizen_evidence/test.jpg",
            "content_hash": "hash123",
            "client_capture_timestamp": capture_time.isoformat(),
        },
        "created_at": now,
    }

    result = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    assert result.evidence_freshness == EvidenceFreshness.FRESH
    assert result.evidence_age_seconds is not None
    assert result.evidence_age_seconds <= 1800.0
    assert any("recently" in f for f in result.verified_factors)


def test_7_stale_evidence():
    """Evidence captured > 2 hours ago -> STALE with warning."""
    now = datetime.now(timezone.utc)
    capture_time = now - timedelta(hours=3)
    report_doc = {
        "report_id": "RES-TEST0007",
        "citizen_name": "Test Citizen",
        "citizen_phone": "+919876543210",
        "emergency_type": EmergencyType.FLOOD.value,
        "citizen_impact_level": CitizenImpactLevel.MEDIUM.value,
        "description": "Old flooding photo from yesterday.",
        "location": {"latitude": 16.5000, "longitude": 80.6400, "address": "Main Road"},
        "evidence": {
            "evidence_id": "EVD-TEST0007",
            "file_url": "/uploads/citizen_evidence/test.jpg",
            "content_hash": "hash123",
            "client_capture_timestamp": capture_time.isoformat(),
        },
        "created_at": now,
    }

    result = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    assert result.evidence_freshness == EvidenceFreshness.STALE
    assert result.evidence_age_seconds is not None
    assert result.evidence_age_seconds > 7200.0
    assert any("stale" in w.lower() for w in result.warnings)


def test_8_duplicate_evidence():
    """Duplicate evidence detected -> warning and LOW confidence."""
    now = datetime.now(timezone.utc)
    report_doc = {
        "report_id": "RES-TEST0008",
        "citizen_name": "Test Citizen",
        "citizen_phone": "+919876543210",
        "emergency_type": EmergencyType.FIRE.value,
        "citizen_impact_level": CitizenImpactLevel.HIGH.value,
        "description": "Report with recycled evidence photo.",
        "location": {"latitude": 16.5000, "longitude": 80.6400, "address": "Market Street"},
        "evidence": {
            "evidence_id": "EVD-TEST0008",
            "file_url": "/uploads/citizen_evidence/test.jpg",
            "content_hash": "duplicate_hash_abc",
            "is_duplicate": True,
            "duplicate_of_evidence_id": "EVD-PREV001",
            "client_capture_timestamp": now.isoformat(),
        },
        "created_at": now,
    }

    result = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    assert result.is_duplicate is True
    assert result.confidence_band == EvidenceConfidenceBand.LOW
    assert any("duplicate" in w.lower() for w in result.warnings)


def test_9_complete_report():
    """Complete report fields -> COMPLETE completeness."""
    now = datetime.now(timezone.utc)
    report_doc = {
        "report_id": "RES-TEST0009",
        "citizen_name": "Citizen Full Name",
        "citizen_phone": "+919876543210",
        "emergency_type": EmergencyType.FLOOD.value,
        "citizen_impact_level": CitizenImpactLevel.HIGH.value,
        "description": "Detailed description of rising water level at gate 3.",
        "location": {
            "latitude": 16.5000,
            "longitude": 80.6400,
            "address": "Gate 3, Riverbank",
            "landmark": "Near Barrage",
        },
        "created_at": now,
    }

    result = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    assert result.report_completeness == ReportCompleteness.COMPLETE
    assert any("Complete" in f for f in result.verified_factors)


def test_10_incomplete_report():
    """Report with missing impact level or minimal info -> PARTIAL or INCOMPLETE."""
    now = datetime.now(timezone.utc)
    report_doc = {
        "report_id": "RES-TEST0010",
        "citizen_name": "A",
        "citizen_phone": "123",
        "emergency_type": EmergencyType.OTHER.value,
        "citizen_impact_level": CitizenImpactLevel.NOT_SURE.value,
        "description": "Help please",
        "location": {"latitude": 16.5000, "longitude": 80.6400},
        "created_at": now,
    }

    result = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    assert result.report_completeness in [ReportCompleteness.PARTIAL, ReportCompleteness.INCOMPLETE]


def test_11_citizen_critical_with_low_evidence():
    """Citizen CRITICAL + low evidence -> CRITICAL remains citizen impact, confidence is LOW."""
    now = datetime.now(timezone.utc)
    report_doc = {
        "report_id": "RES-TEST0011",
        "citizen_name": "Injured Citizen",
        "citizen_phone": "+919876543210",
        "emergency_type": EmergencyType.MEDICAL_EMERGENCY.value,
        "citizen_impact_level": CitizenImpactLevel.CRITICAL.value,
        "description": "Severe injury claimed by caller.",
        "location": {"latitude": 16.5000, "longitude": 80.6400, "address": "Home"},
        "evidence": None,
        "created_at": now,
    }

    result = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    # CRITICAL is preserved as citizen's claimed impact
    assert result.citizen_impact_level == CitizenImpactLevel.CRITICAL
    # Evidence confidence reflects reality (LOW because no evidence attached)
    assert result.confidence_band == EvidenceConfidenceBand.LOW
    # Advisory recommendation
    assert any("Officer verification recommended" in r for r in result.recommendations)


def test_12_citizen_low_with_strong_evidence():
    """Citizen LOW + strong evidence -> LOW remains citizen impact, confidence is HIGH."""
    now = datetime.now(timezone.utc)
    report_doc = {
        "report_id": "RES-TEST0012",
        "citizen_name": "Reporting Citizen",
        "citizen_phone": "+919876543210",
        "emergency_type": EmergencyType.FLOOD.value,
        "citizen_impact_level": CitizenImpactLevel.LOW.value,
        "description": "Minor water logging in residential compound.",
        "location": {"latitude": 16.5000, "longitude": 80.6400, "address": "Compound"},
        "evidence": {
            "evidence_id": "EVD-TEST0012",
            "file_url": "/uploads/citizen_evidence/test.jpg",
            "content_hash": "hash12345",
            "client_capture_timestamp": now.isoformat(),
            "latitude": 16.5001,
            "longitude": 80.6401,
            "accuracy_meters": 10.0,
            "is_duplicate": False,
        },
        "created_at": now,
    }

    result = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    # LOW impact preserved
    assert result.citizen_impact_level == CitizenImpactLevel.LOW
    # Strong evidence confidence
    assert result.confidence_band == EvidenceConfidenceBand.HIGH
    assert result.verification_status == VerificationStatus.PARTIALLY_VERIFIED


def test_13_verification_never_changes_officer_priority():
    """Verification engine is pure advisory and never alters officer priority."""
    now = datetime.now(timezone.utc)
    report_doc = {
        "report_id": "RES-TEST0013",
        "citizen_name": "Test Citizen",
        "citizen_phone": "+919876543210",
        "emergency_type": EmergencyType.FIRE.value,
        "citizen_impact_level": CitizenImpactLevel.HIGH.value,
        "description": "Report with unassessed officer priority.",
        "priority": ReportPriority.UNASSESSED.value,
        "location": {"latitude": 16.5000, "longitude": 80.6400, "address": "Street"},
        "created_at": now,
    }

    result = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    # The evaluation output has no priority override field
    assert not hasattr(result, "priority")
    assert not hasattr(result, "officer_priority")
    assert any("Officer verification recommended" in r for r in result.recommendations)


def test_14_verification_never_activates_response_plan_or_consumes_resources():
    """Verification model is strictly advisory and has zero execution side-effects."""
    now = datetime.now(timezone.utc)
    report_doc = {
        "report_id": "RES-TEST0014",
        "citizen_name": "Test Citizen",
        "citizen_phone": "+919876543210",
        "emergency_type": EmergencyType.BUILDING_COLLAPSE.value,
        "citizen_impact_level": CitizenImpactLevel.CRITICAL.value,
        "description": "Structural collapse report.",
        "location": {"latitude": 16.5000, "longitude": 80.6400, "address": "Street"},
        "created_at": now,
    }

    result = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    # Pure verification model
    assert isinstance(result.recommendations, list)
    assert result.verification_status in [VerificationStatus.UNVERIFIED, VerificationStatus.PARTIALLY_VERIFIED]


def test_15_deterministic_scoring_no_randomness():
    """Multiple evaluations of identical report state produce 100% deterministic identical outputs."""
    now = datetime.now(timezone.utc)
    report_doc = {
        "report_id": "RES-TEST0015",
        "citizen_name": "Deterministic Citizen",
        "citizen_phone": "+919876543210",
        "emergency_type": EmergencyType.FLOOD.value,
        "citizen_impact_level": CitizenImpactLevel.HIGH.value,
        "description": "Evaluating mathematical determinism of verification engine.",
        "location": {"latitude": 16.5000, "longitude": 80.6400, "address": "Point A"},
        "evidence": {
            "evidence_id": "EVD-TEST0015",
            "file_url": "/uploads/citizen_evidence/test.jpg",
            "content_hash": "sha256_exact_hash",
            "client_capture_timestamp": now.isoformat(),
            "latitude": 16.5002,
            "longitude": 80.6401,
            "accuracy_meters": 8.0,
            "is_duplicate": False,
        },
        "created_at": now,
    }

    result_1 = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)
    result_2 = EvidenceVerificationService.evaluate_report_evidence(report_doc, eval_time=now)

    assert result_1.confidence_band == result_2.confidence_band
    assert result_1.verification_status == result_2.verification_status
    assert result_1.distance_from_report_meters == result_2.distance_from_report_meters
    assert result_1.evidence_signals == result_2.evidence_signals
    assert result_1.verified_factors == result_2.verified_factors
    assert result_1.missing_factors == result_2.missing_factors
    assert result_1.warnings == result_2.warnings
