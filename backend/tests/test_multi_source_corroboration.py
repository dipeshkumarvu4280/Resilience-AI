import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from app.models.enums import (
    EmergencyType,
    SensorType,
    CitizenImpactLevel,
    EvidenceValidationStatus,
    CorroborationStatus,
    CorroborationSourceType,
    CorroborationSpatialRelationship,
    CorroborationTemporalRelationship,
    CorroborationAlignment,
    EvidenceConflictCategory,
    ReportPriority,
    ReportStatus,
)
from app.services.corroboration_service import EvidenceCorroborationService
from app.services.evidence_verification_service import EvidenceVerificationService
from app.models.corroboration import CorroborationResult


# Base Reference Fixtures
BASE_TIME = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
BASE_LAT = 16.5062
BASE_LON = 80.6480


def create_mock_report(
    report_id: str = "RES-TARGET1",
    emergency_type: str = "Flood",
    impact_level: str = "HIGH",
    desc: str = "Severe flooding on main street, water rising rapidly",
    lat: float = BASE_LAT,
    lon: float = BASE_LON,
    created_at: datetime = BASE_TIME,
    has_evidence: bool = False,
    evidence_lat: float = BASE_LAT,
    evidence_lon: float = BASE_LON,
    evidence_status: str = "VALIDATED",
) -> Dict[str, Any]:
    doc: Dict[str, Any] = {
        "report_id": report_id,
        "citizen_id": f"CIT-{report_id[-4:]}",
        "citizen_name": "Test Citizen",
        "citizen_phone": "9876543210",
        "emergency_type": emergency_type,
        "citizen_impact_level": impact_level,
        "description": desc,
        "location": {
            "latitude": lat,
            "longitude": lon,
            "address": "MG Road, Vijayawada",
        },
        "status": "RECEIVED",
        "priority": "UNASSESSED",
        "created_at": created_at,
        "updated_at": created_at,
    }
    if has_evidence:
        doc["evidence"] = {
            "evidence_id": f"EVD-{report_id[-4:]}",
            "evidence_type": "LIVE_CAMERA_PHOTO",
            "file_url": "/uploads/test.jpg",
            "content_hash": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2",
            "latitude": evidence_lat,
            "longitude": evidence_lon,
            "accuracy_meters": 10.0,
            "client_capture_timestamp": created_at,
            "validation_status": evidence_status,
        }
    return doc


def create_mock_sensor(
    sensor_id: str = "SNS-WATER01",
    sensor_type: str = "WATER_LEVEL",
    val: float = 1.2,
    thresh: float = 0.8,
    is_breach: bool = True,
    lat: float = BASE_LAT + 0.002,  # ~220m away
    lon: float = BASE_LON + 0.002,
    cov_meters: float = 2000.0,
    timestamp: datetime = BASE_TIME,
) -> Dict[str, Any]:
    return {
        "sensor_id": sensor_id,
        "name": f"Station {sensor_id}",
        "sensor_type": sensor_type,
        "current_reading": val,
        "unit": "meters" if sensor_type == "WATER_LEVEL" else "AQI" if sensor_type in ["AQI", "SMOKE_AIR_QUALITY"] else "°C",
        "threshold": thresh,
        "in_alert": is_breach,
        "latitude": lat,
        "longitude": lon,
        "coverage": {"radius_meters": cov_meters},
        "last_updated": timestamp,
    }


# =============================================================================
# TEST 1: Single source -> NO_CORROBORATION
# =============================================================================
def test_01_single_source_no_corroboration():
    report = create_mock_report()
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=report,
        candidate_reports=[],
        candidate_sensors=[],
        eval_time=BASE_TIME,
    )
    assert result.corroboration_status == CorroborationStatus.NO_CORROBORATION
    assert result.supporting_source_count == 0
    assert result.conflicting_source_count == 0
    assert "Single-source report" in result.explanation


# =============================================================================
# TEST 2: Two nearby compatible citizen reports -> CORROBORATED
# =============================================================================
def test_02_two_nearby_compatible_citizen_reports_corroborated():
    target = create_mock_report(report_id="RES-001", has_evidence=True)
    peer = create_mock_report(
        report_id="RES-002",
        emergency_type="Flood",
        desc="Water level rising on street near hospital",
        lat=BASE_LAT + 0.003,  # ~330m away
        lon=BASE_LON + 0.002,
        created_at=BASE_TIME + timedelta(minutes=5),
    )
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[peer],
        eval_time=BASE_TIME + timedelta(minutes=10),
    )
    assert result.corroboration_status == CorroborationStatus.CORROBORATED
    assert result.supporting_source_count >= 2  # Evidence + Peer Report
    assert result.conflicting_source_count == 0


# =============================================================================
# TEST 3: Distant citizen report -> not corroborating (NEUTRAL)
# =============================================================================
def test_03_distant_citizen_report_not_corroborating():
    target = create_mock_report(report_id="RES-001")
    distant_peer = create_mock_report(
        report_id="RES-002",
        emergency_type="Flood",
        lat=BASE_LAT + 0.1,  # ~11 km away (well over 2000m)
        lon=BASE_LON + 0.1,
    )
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[distant_peer],
        eval_time=BASE_TIME,
    )
    assert result.corroboration_status == CorroborationStatus.NO_CORROBORATION
    assert result.supporting_source_count == 0
    assert len(result.neutral_sources) == 1
    assert result.neutral_sources[0].spatial_relationship == CorroborationSpatialRelationship.DISTANT


# =============================================================================
# TEST 4: Same location + compatible timestamps -> supporting
# =============================================================================
def test_04_same_location_compatible_timestamps_supporting():
    target = create_mock_report(report_id="RES-001")
    peer = create_mock_report(
        report_id="RES-002",
        lat=BASE_LAT + 0.001,  # ~110m away
        lon=BASE_LON + 0.001,
        created_at=BASE_TIME + timedelta(minutes=8),
    )
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[peer],
        eval_time=BASE_TIME + timedelta(minutes=10),
    )
    assert result.supporting_source_count == 1
    assert result.supporting_sources[0].spatial_relationship == CorroborationSpatialRelationship.MATCH
    assert result.supporting_sources[0].temporal_relationship == CorroborationTemporalRelationship.COINCIDENT


# =============================================================================
# TEST 5: Old historical report -> not current corroboration (NEUTRAL)
# =============================================================================
def test_05_old_historical_report_not_current_corroboration():
    target = create_mock_report(report_id="RES-001", created_at=BASE_TIME)
    old_peer = create_mock_report(
        report_id="RES-002",
        created_at=BASE_TIME - timedelta(hours=6),  # 6 hours ago (> 2 hours window)
    )
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[old_peer],
        eval_time=BASE_TIME,
    )
    assert result.corroboration_status == CorroborationStatus.NO_CORROBORATION
    assert result.supporting_source_count == 0
    assert any(s.temporal_relationship == CorroborationTemporalRelationship.HISTORICAL for s in result.neutral_sources)


# =============================================================================
# TEST 6: Sensor inside configured coverage -> eligible & supporting
# =============================================================================
def test_06_sensor_inside_coverage_eligible():
    target = create_mock_report(report_id="RES-001", emergency_type="Flood")
    sensor = create_mock_sensor(
        sensor_id="SNS-W1",
        sensor_type="WATER_LEVEL",
        val=1.5,
        thresh=0.8,
        is_breach=True,
        lat=BASE_LAT + 0.004,  # ~450m away
        lon=BASE_LON + 0.004,
        cov_meters=2000.0,
    )
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_sensors=[sensor],
        eval_time=BASE_TIME,
    )
    assert result.supporting_source_count == 1
    assert result.supporting_sources[0].within_coverage is True
    assert result.supporting_sources[0].is_breach is True


# =============================================================================
# TEST 7: Sensor outside configured coverage -> not corroborating (NEUTRAL)
# =============================================================================
def test_07_sensor_outside_coverage_neutral():
    target = create_mock_report(report_id="RES-001", emergency_type="Flood")
    # Sensor 3.5km away, but its configured coverage is only 1500m
    sensor = create_mock_sensor(
        sensor_id="SNS-W1",
        sensor_type="WATER_LEVEL",
        val=1.8,
        thresh=0.8,
        is_breach=True,
        lat=BASE_LAT + 0.03,  # ~3.3km away
        lon=BASE_LON + 0.03,
        cov_meters=1500.0,
    )
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_sensors=[sensor],
        eval_time=BASE_TIME,
    )
    assert result.corroboration_status == CorroborationStatus.NO_CORROBORATION
    assert result.supporting_source_count == 0
    assert len(result.neutral_sources) == 1
    assert result.neutral_sources[0].within_coverage is False
    assert "outside configured coverage radius" in result.neutral_sources[0].summary


# =============================================================================
# TEST 8: Relevant sensor + citizen report -> supporting
# =============================================================================
def test_08_relevant_sensor_and_citizen_report_supporting():
    target = create_mock_report(report_id="RES-001", emergency_type="Flood")
    peer = create_mock_report(report_id="RES-002", emergency_type="Flood", lat=BASE_LAT + 0.002, lon=BASE_LON)
    sensor = create_mock_sensor(sensor_id="SNS-W1", sensor_type="WATER_LEVEL", val=1.4, thresh=0.8, is_breach=True)
    
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[peer],
        candidate_sensors=[sensor],
        eval_time=BASE_TIME,
    )
    assert result.corroboration_status == CorroborationStatus.CORROBORATED
    assert result.supporting_source_count == 2
    assert result.conflicting_source_count == 0


# =============================================================================
# TEST 9: Unrelated sensor type -> neutral (NOT conflicting)
# =============================================================================
def test_09_unrelated_sensor_type_neutral():
    target = create_mock_report(report_id="RES-001", emergency_type="Flood")
    temp_sensor = create_mock_sensor(
        sensor_id="SNS-T1",
        sensor_type="TEMPERATURE",
        val=31.0,
        thresh=45.0,
        is_breach=False,
    )
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_sensors=[temp_sensor],
        eval_time=BASE_TIME,
    )
    assert result.conflicting_source_count == 0
    assert result.supporting_source_count == 0
    assert len(result.neutral_sources) == 1
    assert "not directly relevant" in result.neutral_sources[0].summary


# =============================================================================
# TEST 10: Contradictory citizen observations -> CONFLICTED
# =============================================================================
def test_10_contradictory_citizen_observations_conflicted():
    target = create_mock_report(
        report_id="RES-001",
        emergency_type="Flood",
        impact_level="CRITICAL",
        desc="Severe massive flooding submerged main road",
    )
    conflicting_peer = create_mock_report(
        report_id="RES-002",
        emergency_type="Flood",
        desc="Roads clear, no flood, false alarm, traffic normal",
        lat=BASE_LAT + 0.001,
        lon=BASE_LON + 0.001,
    )
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[conflicting_peer],
        eval_time=BASE_TIME,
    )
    assert result.corroboration_status == CorroborationStatus.CONFLICTED
    assert result.conflicting_source_count == 1
    assert len(result.conflict_details) == 1
    assert result.conflict_details[0].category == EvidenceConflictCategory.CITIZEN_REPORT_CONFLICT


# =============================================================================
# TEST 11: Citizen vs sensor contradiction -> CONFLICTED
# =============================================================================
def test_11_citizen_vs_sensor_contradiction_conflicted():
    target = create_mock_report(
        report_id="RES-001",
        emergency_type="Flood",
        impact_level="HIGH",
        desc="Severe flooding everywhere, waist deep water",
    )
    # Nearby sensor inside coverage shows flat 0.00m (normal)
    normal_sensor = create_mock_sensor(
        sensor_id="SNS-W1",
        sensor_type="WATER_LEVEL",
        val=0.0,
        thresh=1.0,
        is_breach=False,
    )
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_sensors=[normal_sensor],
        eval_time=BASE_TIME,
    )
    assert result.corroboration_status == CorroborationStatus.CONFLICTED
    assert result.conflicting_source_count == 1
    assert result.conflict_details[0].category == EvidenceConflictCategory.SENSOR_REPORT_CONFLICT
    assert "Citizen-reported severe flooding is not corroborated" in result.conflict_details[0].reason


# =============================================================================
# TEST 12: Missing sensor -> not a conflict
# =============================================================================
def test_12_missing_sensor_not_a_conflict():
    target = create_mock_report(report_id="RES-001")
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_sensors=[],
        eval_time=BASE_TIME,
    )
    assert result.conflicting_source_count == 0
    assert result.corroboration_status == CorroborationStatus.NO_CORROBORATION


# =============================================================================
# TEST 13: Missing GPS -> UNAVAILABLE, not mismatch
# =============================================================================
def test_13_missing_gps_unavailable_not_mismatch():
    target = create_mock_report(report_id="RES-001", lat=0.0, lon=0.0)
    peer = create_mock_report(report_id="RES-002", lat=BASE_LAT, lon=BASE_LON)
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[peer],
        eval_time=BASE_TIME,
    )
    assert result.conflicting_source_count == 0
    assert result.neutral_sources[0].spatial_relationship == CorroborationSpatialRelationship.UNAVAILABLE


# =============================================================================
# TEST 14: High evidence confidence + conflict -> both preserved separately
# =============================================================================
def test_14_high_evidence_confidence_and_conflict_preserved_separately():
    target = create_mock_report(
        report_id="RES-001",
        impact_level="CRITICAL",
        desc="Severe massive flood",
        has_evidence=True,
        evidence_status="VALIDATED",
    )
    # Phase A Evidence Verification
    verif = EvidenceVerificationService.evaluate_report_evidence(target, eval_time=BASE_TIME)
    
    # Phase B Conflict: Normal sensor contradicts citizen severe claim
    normal_sensor = create_mock_sensor(sensor_id="SNS-W1", sensor_type="WATER_LEVEL", val=0.0, thresh=1.0, is_breach=False)
    corrob = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_sensors=[normal_sensor],
        eval_time=BASE_TIME,
    )

    # Evidence Confidence is HIGH (clean live photo + GPS match + content hash)
    assert verif.confidence_band.value == "HIGH"
    # Corroboration is CONFLICTED
    assert corrob.corroboration_status == CorroborationStatus.CONFLICTED
    # Both are independent and strictly preserved
    assert verif.confidence_band.value != corrob.corroboration_status.value


# =============================================================================
# TEST 15: Conflict does not mutate officer_final_priority
# =============================================================================
def test_15_conflict_does_not_mutate_officer_priority():
    target = create_mock_report(report_id="RES-001")
    target["priority"] = ReportPriority.HIGH.value
    
    normal_sensor = create_mock_sensor(sensor_id="SNS-W1", val=0.0, thresh=1.0, is_breach=False)
    corrob = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_sensors=[normal_sensor],
        eval_time=BASE_TIME,
    )
    assert corrob.corroboration_status == CorroborationStatus.CONFLICTED
    # Target report priority in data model remains intact
    assert target["priority"] == ReportPriority.HIGH.value


# =============================================================================
# TEST 16: Conflict does not activate response plan (Purely Advisory)
# =============================================================================
def test_16_conflict_is_strictly_advisory():
    target = create_mock_report(report_id="RES-001")
    conflicting_peer = create_mock_report(report_id="RES-002", desc="Roads clear, false alarm")
    corrob = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[conflicting_peer],
        eval_time=BASE_TIME,
    )
    assert corrob.corroboration_status == CorroborationStatus.CONFLICTED
    assert "HUMAN REVIEW REQUIRED" in corrob.warnings[0]
    # No autonomous action fields in CorroborationResult
    assert not hasattr(corrob, "auto_dispatch")
    assert not hasattr(corrob, "activated_plan_id")


# =============================================================================
# TEST 17: Repeated evaluation is deterministic
# =============================================================================
def test_17_repeated_evaluation_is_deterministic():
    target = create_mock_report(report_id="RES-001")
    peer = create_mock_report(report_id="RES-002", lat=BASE_LAT + 0.002, lon=BASE_LON)
    sensor = create_mock_sensor(sensor_id="SNS-W1", val=1.5, thresh=0.8, is_breach=True)

    res1 = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[peer],
        candidate_sensors=[sensor],
        eval_time=BASE_TIME,
    )
    res2 = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[peer],
        candidate_sensors=[sensor],
        eval_time=BASE_TIME,
    )

    assert res1.corroboration_status == res2.corroboration_status
    assert res1.supporting_source_count == res2.supporting_source_count
    assert res1.conflicting_source_count == res2.conflicting_source_count
    assert res1.explanation == res2.explanation


# =============================================================================
# TEST 18: Live Camera Evidence Location Mismatch -> Spatial Conflict
# =============================================================================
def test_18_live_evidence_spatial_mismatch_triggers_conflict():
    target = create_mock_report(
        report_id="RES-001",
        has_evidence=True,
        evidence_lat=BASE_LAT + 0.05,  # ~5.5 km away from report location!
        evidence_lon=BASE_LON + 0.05,
    )
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        eval_time=BASE_TIME,
    )
    assert result.corroboration_status == CorroborationStatus.CONFLICTED
    assert result.conflicting_source_count == 1
    assert result.conflict_details[0].category == EvidenceConflictCategory.SPATIAL_CONFLICT


# =============================================================================
# TEST 19: Field Update Confirmation & Contradiction
# =============================================================================
def test_19_field_update_corroboration_and_contradiction():
    target = create_mock_report(report_id="RES-001", emergency_type="Flood")
    
    # Supporting field update
    supporting_fu = [{
        "update_id": "FU-01",
        "notes": "Field unit arrived on scene, 1.2m flood water confirmed on MG Road",
        "author_name": "Officer Sharma",
    }]
    res_supp = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_field_updates=supporting_fu,
        eval_time=BASE_TIME,
    )
    assert res_supp.supporting_source_count == 1
    assert res_supp.corroboration_status == CorroborationStatus.PARTIALLY_CORROBORATED

    # Contradicting field update
    contradicting_fu = [{
        "update_id": "FU-02",
        "notes": "Field unit inspected location, situation normal, no water or flood found",
        "author_name": "Officer Sharma",
    }]
    res_conf = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_field_updates=contradicting_fu,
        eval_time=BASE_TIME,
    )
    assert res_conf.conflicting_source_count == 1
    assert res_conf.corroboration_status == CorroborationStatus.CONFLICTED
    assert res_conf.conflict_details[0].category == EvidenceConflictCategory.OBSERVATION_CONFLICT


# =============================================================================
# TEST 20: Event Type Conflict at Same Location
# =============================================================================
def test_20_incompatible_event_types_at_same_location_conflicted():
    target = create_mock_report(report_id="RES-001", emergency_type="Fire", desc="Heavy fire in warehouse")
    peer = create_mock_report(
        report_id="RES-002",
        emergency_type="Flood",
        desc="Massive flood wave submerging building",
        lat=BASE_LAT + 0.001,
        lon=BASE_LON + 0.001,
    )
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[peer],
        eval_time=BASE_TIME,
    )
    assert result.corroboration_status == CorroborationStatus.CONFLICTED
    assert result.conflict_details[0].category == EvidenceConflictCategory.EVENT_TYPE_CONFLICT


# =============================================================================
# TEST 21: Existing Phase A Verification remains functional
# =============================================================================
def test_21_existing_phase_a_verification_remains_unchanged():
    report = create_mock_report(has_evidence=True, evidence_status="VALIDATED")
    verif = EvidenceVerificationService.evaluate_report_evidence(report, eval_time=BASE_TIME)
    assert verif.confidence_band.value == "HIGH"
    assert verif.verification_status.value == "PARTIALLY_VERIFIED"
    assert verif.has_live_photo is True
    assert verif.location_match_state.value == "MATCH"


# =============================================================================
# TEST 22: Zero Dummy Data Invariant — Genuine Model Structure
# =============================================================================
def test_22_zero_dummy_data_audit():
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=create_mock_report(),
        candidate_reports=[],
        candidate_sensors=[],
        eval_time=BASE_TIME,
    )
    # Verification that result is clean, deterministic, with 0 dummy counts
    assert result.total_sources_evaluated == 0
    assert result.supporting_source_count == 0
    assert result.conflicting_source_count == 0
    assert result.neutral_source_count == 0
    assert len(result.supporting_sources) == 0
    assert len(result.conflicting_sources) == 0
    assert len(result.neutral_sources) == 0
    assert len(result.conflict_details) == 0


# =============================================================================
# TEST 23: Fire Emergency + Smoke Sensor Corroboration
# =============================================================================
def test_23_fire_emergency_and_smoke_sensor_corroboration():
    target = create_mock_report(report_id="RES-FIRE1", emergency_type="Fire", desc="Huge warehouse fire with dense smoke")
    smoke_sensor = create_mock_sensor(
        sensor_id="SNS-AQI1",
        sensor_type="SMOKE_AIR_QUALITY",
        val=250.0,
        thresh=100.0,
        is_breach=True,
    )
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_sensors=[smoke_sensor],
        eval_time=BASE_TIME,
    )
    assert result.supporting_source_count == 1
    assert result.corroboration_status == CorroborationStatus.PARTIALLY_CORROBORATED
    assert "Thermal / smoke sensor" in result.corroboration_factors[0]


# =============================================================================
# TEST 24: Corroboration Explainability ("Why this result?")
# =============================================================================
def test_24_corroboration_explainability_narrative():
    target = create_mock_report(report_id="RES-001", has_evidence=True)
    peer = create_mock_report(report_id="RES-002", lat=BASE_LAT + 0.002, lon=BASE_LON)
    sensor = create_mock_sensor(sensor_id="SNS-W1", val=1.3, thresh=0.8, is_breach=True)
    
    result = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[peer],
        candidate_sensors=[sensor],
        eval_time=BASE_TIME,
    )
    assert result.corroboration_status == CorroborationStatus.CORROBORATED
    assert "Multi-source corroboration established: 3 independent sources" in result.explanation
    assert len(result.corroboration_factors) == 3
    assert len(result.recommendations) > 0
