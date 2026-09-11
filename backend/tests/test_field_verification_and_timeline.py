import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
import pytest

from app.models.enums import (
    EmergencyType,
    ReportStatus,
    ReportPriority,
    CitizenImpactLevel,
    EvidenceValidationStatus,
    LocationMatchState,
    CorroborationStatus,
    CorroborationSourceType,
    CorroborationAlignment,
    EvidenceConflictCategory,
    FieldVerificationStatus,
    FieldObservationCategory,
    IncidentEvolutionCategory,
    UserRole,
)
from app.models.citizen import LocationPayload
from app.models.field_verification import (
    FieldVerificationCreateRequest,
    FieldVerificationRecord,
)
from app.models.incident_evolution import (
    IncidentEvolutionEvent,
    IncidentEvolutionTimelineResponse,
)
from app.services.field_verification_service import FieldVerificationService
from app.services.corroboration_service import EvidenceCorroborationService
from app.services.incident_evolution_service import IncidentEvolutionService


class MockAsyncCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self.docs = docs
        self.idx = 0

    def sort(self, *args, **kwargs):
        return self

    def skip(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, length: int = 100):
        return self.docs[:length]

    def __aiter__(self):
        self.idx = 0
        return self

    async def __anext__(self):
        if self.idx < len(self.docs):
            doc = self.docs[self.idx]
            self.idx += 1
            return doc
        raise StopAsyncIteration


class MockCollection:
    def __init__(self, name: str, data: List[Dict[str, Any]] = None):
        self.name = name
        self.data: List[Dict[str, Any]] = data or []

    async def find_one(self, query: Dict[str, Any]):
        for doc in self.data:
            match = True
            for k, v in query.items():
                if k == "$or":
                    or_match = False
                    for sub_q in v:
                        sub_matched = True
                        for sk, sv in sub_q.items():
                            if sk == "report_id" and isinstance(sv, dict) and "$in" in sv:
                                if doc.get(sk) not in sv["$in"]:
                                    sub_matched = False
                            elif doc.get(sk) != sv:
                                sub_matched = False
                        if sub_matched:
                            or_match = True
                            break
                    if not or_match:
                        match = False
                elif isinstance(v, dict) and "$in" in v:
                    if doc.get(k) not in v["$in"]:
                        match = False
                elif doc.get(k) != v:
                    match = False
            if match:
                return doc
        return None

    def find(self, query: Dict[str, Any] = None):
        if not query:
            return MockAsyncCursor(self.data)
        matched = []
        for doc in self.data:
            match = True
            for k, v in query.items():
                if k == "$or":
                    or_match = False
                    for sub_q in v:
                        sub_matched = True
                        for sk, sv in sub_q.items():
                            if sk.startswith("metadata."):
                                m_key = sk.split(".")[1]
                                if (doc.get("metadata") or {}).get(m_key) != sv:
                                    sub_matched = False
                            elif sk == "report_id" and isinstance(sv, dict) and "$in" in sv:
                                if doc.get(sk) not in sv["$in"]:
                                    sub_matched = False
                            elif sk == "target_id" and isinstance(sv, dict) and "$in" in sv:
                                if doc.get(sk) not in sv["$in"]:
                                    sub_matched = False
                            elif doc.get(sk) != sv:
                                sub_matched = False
                        if sub_matched:
                            or_match = True
                            break
                    if not or_match:
                        match = False
                elif isinstance(v, dict) and "$in" in v:
                    if doc.get(k) not in v["$in"]:
                        match = False
                elif isinstance(v, dict) and "$ne" in v:
                    if doc.get(k) == v["$ne"]:
                        match = False
                elif k.startswith("metadata."):
                    m_key = k.split(".")[1]
                    if (doc.get("metadata") or {}).get(m_key) != v:
                        match = False
                elif doc.get(k) != v:
                    match = False
            if match:
                matched.append(doc)
        return MockAsyncCursor(matched)

    async def insert_one(self, doc: Dict[str, Any]):
        self.data.append(doc)
        return type("InsertResult", (), {"inserted_id": "mock_id"})()

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]):
        for doc in self.data:
            matched = True
            for k, v in query.items():
                if doc.get(k) != v:
                    matched = False
            if matched:
                if "$set" in update:
                    doc.update(update["$set"])
                if "$push" in update:
                    for pk, pv in update["$push"].items():
                        if pk not in doc:
                            doc[pk] = []
                        doc[pk].append(pv)
                return type("UpdateResult", (), {"modified_count": 1})()
        return type("UpdateResult", (), {"modified_count": 0})()

    async def count_documents(self, query: Dict[str, Any]):
        cursor = self.find(query)
        res = await cursor.to_list(1000)
        return len(res)


class MockDatabase:
    def __init__(self):
        self.collections: Dict[str, MockCollection] = {}

    def __getitem__(self, name: str) -> MockCollection:
        if name not in self.collections:
            self.collections[name] = MockCollection(name)
        return self.collections[name]


# =====================================================================
# PHASE C TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_01_authorized_responder_can_submit_field_verification():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    rep_doc = {
        "report_id": "RES-FLD001",
        "emergency_type": "Flood",
        "description": "Rising flood water near market",
        "citizen_impact_level": "HIGH",
        "location": {"latitude": 28.6139, "longitude": 77.2090, "address": "Market Sq"},
        "status": "RECEIVED",
        "priority": "UNASSESSED",
        "created_at": now,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    req = FieldVerificationCreateRequest(
        target_id="RES-FLD001",
        target_type="CITIZEN_REPORT",
        verification_status=FieldVerificationStatus.FIELD_VERIFIED,
        observation_category=FieldObservationCategory.INCIDENT_CONFIRMED,
        notes="Confirmed 2ft standing water across street.",
        location=LocationPayload(latitude=28.6140, longitude=77.2091, address="Market Sq West"),
    )
    actor = {"id": "VOL-101", "full_name": "Ravi Kumar", "role": "VOLUNTEER"}

    record = await FieldVerificationService.verify_ground_truth(req=req, actor=actor, db=db)
    assert record.verification_id.startswith("FLV-")
    assert record.responder_name == "Ravi Kumar"
    assert record.responder_role == UserRole.VOLUNTEER
    assert record.verification_status == FieldVerificationStatus.FIELD_VERIFIED
    assert record.observation_category == FieldObservationCategory.INCIDENT_CONFIRMED
    assert record.location_match_state == LocationMatchState.MATCH


@pytest.mark.asyncio
async def test_02_unauthorized_user_cannot_submit_field_verification():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    rep_doc = {
        "report_id": "RES-FLD002",
        "emergency_type": "Fire",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    req = FieldVerificationCreateRequest(
        target_id="RES-FLD002",
        target_type="CITIZEN_REPORT",
        verification_status=FieldVerificationStatus.FIELD_VERIFIED,
        observation_category=FieldObservationCategory.INCIDENT_CONFIRMED,
    )
    actor_citizen = {"id": "CIT-999", "full_name": "Random Citizen", "role": "CITIZEN"}

    with pytest.raises(ValueError) as exc:
        await FieldVerificationService.verify_ground_truth(req=req, actor=actor_citizen, db=db)
    assert "not authorized" in str(exc.value)


@pytest.mark.asyncio
async def test_03_field_verification_stores_actual_actor():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    rep_doc = {
        "report_id": "RES-FLD003",
        "emergency_type": "Flood",
        "location": {"latitude": 19.0760, "longitude": 72.8777},
        "created_at": now,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    req = FieldVerificationCreateRequest(
        target_id="RES-FLD003",
        target_type="CITIZEN_REPORT",
        verification_status=FieldVerificationStatus.FIELD_VERIFIED,
        observation_category=FieldObservationCategory.INCIDENT_CONFIRMED,
        notes="On-scene assessment completed.",
    )
    actor_officer = {"id": "OFF-800", "full_name": "Commander Sarah Jenkins", "role": "EMERGENCY_OFFICER"}

    record = await FieldVerificationService.verify_ground_truth(req=req, actor=actor_officer, db=db)
    assert record.responder_id == "OFF-800"
    assert record.responder_name == "Commander Sarah Jenkins"
    assert record.responder_role == UserRole.EMERGENCY_OFFICER


@pytest.mark.asyncio
async def test_04_field_gps_match_under_500m():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    rep_doc = {
        "report_id": "RES-GPS01",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    # 15 meters away
    req = FieldVerificationCreateRequest(
        target_id="RES-GPS01",
        verification_status=FieldVerificationStatus.FIELD_VERIFIED,
        observation_category=FieldObservationCategory.INCIDENT_CONFIRMED,
        location=LocationPayload(latitude=28.6140, longitude=77.2091),
    )
    actor = {"id": "VOL-001", "full_name": "Test Officer", "role": "EMERGENCY_OFFICER"}

    record = await FieldVerificationService.verify_ground_truth(req=req, actor=actor, db=db)
    assert record.location_match_state == LocationMatchState.MATCH
    assert record.distance_from_target_meters is not None
    assert record.distance_from_target_meters < 500.0


@pytest.mark.asyncio
async def test_05_field_gps_near_match_between_500m_and_2000m():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    rep_doc = {
        "report_id": "RES-GPS02",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    # ~1.2 km away
    req = FieldVerificationCreateRequest(
        target_id="RES-GPS02",
        verification_status=FieldVerificationStatus.PARTIALLY_VERIFIED,
        observation_category=FieldObservationCategory.INCIDENT_CONFIRMED,
        location=LocationPayload(latitude=28.6239, longitude=77.2140),
    )
    actor = {"id": "VOL-002", "full_name": "Test Officer", "role": "VOLUNTEER"}

    record = await FieldVerificationService.verify_ground_truth(req=req, actor=actor, db=db)
    assert record.location_match_state == LocationMatchState.NEAR_MATCH
    assert 500.0 < record.distance_from_target_meters <= 2000.0


@pytest.mark.asyncio
async def test_06_field_gps_mismatch_over_2000m():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    rep_doc = {
        "report_id": "RES-GPS03",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    # ~10 km away
    req = FieldVerificationCreateRequest(
        target_id="RES-GPS03",
        verification_status=FieldVerificationStatus.FIELD_VERIFIED,
        observation_category=FieldObservationCategory.INCIDENT_CONFIRMED,
        location=LocationPayload(latitude=28.7000, longitude=77.2090),
    )
    actor = {"id": "VOL-003", "full_name": "Test Officer", "role": "VOLUNTEER"}

    record = await FieldVerificationService.verify_ground_truth(req=req, actor=actor, db=db)
    assert record.location_match_state == LocationMatchState.MISMATCH
    assert record.distance_from_target_meters > 2000.0


@pytest.mark.asyncio
async def test_07_gps_unavailable_handled_honestly():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    rep_doc = {
        "report_id": "RES-GPS04",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    req = FieldVerificationCreateRequest(
        target_id="RES-GPS04",
        verification_status=FieldVerificationStatus.FIELD_VERIFIED,
        observation_category=FieldObservationCategory.INCIDENT_CONFIRMED,
        location=None,  # GPS denied
    )
    actor = {"id": "VOL-004", "full_name": "Test Officer", "role": "VOLUNTEER"}

    record = await FieldVerificationService.verify_ground_truth(req=req, actor=actor, db=db)
    assert record.location_match_state == LocationMatchState.UNAVAILABLE
    assert record.distance_from_target_meters is None


@pytest.mark.asyncio
async def test_08_field_verification_becomes_corroboration_source():
    now = datetime.now(timezone.utc)
    target = {
        "report_id": "RES-COR01",
        "emergency_type": "Flood",
        "description": "Flooding on arterial road",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    field_updates = [
        {
            "verification_id": "FLV-999",
            "responder_name": "Captain Sharma",
            "verification_status": "FIELD_VERIFIED",
            "observation_category": "INCIDENT_CONFIRMED",
            "notes": "Flooding confirmed 1.5ft high",
        }
    ]

    res = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[],
        candidate_sensors=[],
        candidate_alerts=[],
        candidate_field_updates=field_updates,
        eval_time=now,
    )
    assert res.total_sources_evaluated >= 1
    assert res.supporting_source_count >= 1
    assert any(s.source_type == CorroborationSourceType.FIELD_UPDATE for s in res.supporting_sources)


@pytest.mark.asyncio
async def test_09_supporting_field_evidence_contributes_to_corroborated():
    now = datetime.now(timezone.utc)
    target = {
        "report_id": "RES-COR02",
        "emergency_type": "Flood",
        "description": "Flooding on arterial road",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    peer = {
        "report_id": "RES-PEER02",
        "emergency_type": "Flood",
        "description": "Water logging near bridge",
        "location": {"latitude": 28.6145, "longitude": 77.2095},
        "created_at": now - timedelta(minutes=5),
    }
    field_updates = [
        {
            "verification_id": "FLV-998",
            "responder_name": "Captain Sharma",
            "verification_status": "FIELD_VERIFIED",
            "observation_category": "INCIDENT_CONFIRMED",
            "notes": "Confirmed on site",
        }
    ]

    res = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[peer],
        candidate_sensors=[],
        candidate_alerts=[],
        candidate_field_updates=field_updates,
        eval_time=now,
    )
    assert res.corroboration_status == CorroborationStatus.CORROBORATED
    assert res.supporting_source_count == 2
    assert res.conflicting_source_count == 0


@pytest.mark.asyncio
async def test_10_conflicting_field_observation_produces_conflicted():
    now = datetime.now(timezone.utc)
    target = {
        "report_id": "RES-COR03",
        "emergency_type": "Flood",
        "description": "Severe flooding reported",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    field_updates = [
        {
            "verification_id": "FLV-CONFLICT1",
            "responder_name": "Officer Patel",
            "verification_status": "NOT_FOUND",
            "observation_category": "INCIDENT_NOT_FOUND",
            "notes": "Arrived at location, road is dry with zero water accumulation",
        }
    ]

    res = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[],
        candidate_sensors=[],
        candidate_alerts=[],
        candidate_field_updates=field_updates,
        eval_time=now,
    )
    assert res.corroboration_status == CorroborationStatus.CONFLICTED
    assert res.conflicting_source_count >= 1
    assert any(c.category == EvidenceConflictCategory.OBSERVATION_CONFLICT for c in res.conflict_details)


@pytest.mark.asyncio
async def test_11_previous_evidence_is_not_deleted():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    rep_doc = {
        "report_id": "RES-KEEP01",
        "emergency_type": "Fire",
        "description": "Smoke seen",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "evidence": {
            "evidence_id": "EVD-ORIGINAL",
            "validation_status": "VALIDATED",
            "content_hash": "abc123hash",
        },
        "created_at": now,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    req = FieldVerificationCreateRequest(
        target_id="RES-KEEP01",
        verification_status=FieldVerificationStatus.CONDITION_CHANGED,
        observation_category=FieldObservationCategory.SEVERITY_CHANGED,
        notes="Fire now contained by local unit.",
    )
    actor = {"id": "OFF-11", "full_name": "Officer Lee", "role": "EMERGENCY_OFFICER"}

    await FieldVerificationService.verify_ground_truth(req=req, actor=actor, db=db)

    # Confirm original report and original evidence were preserved
    doc = await db["citizen_reports"].find_one({"report_id": "RES-KEEP01"})
    assert doc is not None
    assert doc["evidence"]["evidence_id"] == "EVD-ORIGINAL"
    assert doc["evidence"]["content_hash"] == "abc123hash"


@pytest.mark.asyncio
async def test_12_field_verification_does_not_mutate_officer_priority():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    rep_doc = {
        "report_id": "RES-PRIO01",
        "emergency_type": "Flood",
        "priority": "LOW",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    req = FieldVerificationCreateRequest(
        target_id="RES-PRIO01",
        verification_status=FieldVerificationStatus.FIELD_VERIFIED,
        observation_category=FieldObservationCategory.FIRE_SPREADING,
        notes="Hazard escalating.",
    )
    actor = {"id": "VOL-77", "full_name": "Volunteer Team", "role": "VOLUNTEER"}

    await FieldVerificationService.verify_ground_truth(req=req, actor=actor, db=db)

    # Officer priority MUST remain LOW
    doc = await db["citizen_reports"].find_one({"report_id": "RES-PRIO01"})
    assert doc["priority"] == "LOW"


@pytest.mark.asyncio
async def test_13_field_verification_does_not_auto_activate_plan():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    plan_doc = {
        "plan_id": "PLAN-001",
        "situation_id": "SIT-TEST01",
        "status": "DRAFT",
        "created_at": now,
    }
    await db["coordination_plans"].insert_one(plan_doc)

    sit_doc = {
        "situation_id": "SIT-TEST01",
        "center_location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    await db["situations"].insert_one(sit_doc)

    req = FieldVerificationCreateRequest(
        target_id="SIT-TEST01",
        target_type="SITUATION",
        verification_status=FieldVerificationStatus.FIELD_VERIFIED,
        observation_category=FieldObservationCategory.ROAD_BLOCKED,
        notes="Bridge blocked.",
    )
    actor = {"id": "OFF-1", "full_name": "Commander", "role": "EMERGENCY_OFFICER"}

    await FieldVerificationService.verify_ground_truth(req=req, actor=actor, db=db)

    plan = await db["coordination_plans"].find_one({"plan_id": "PLAN-001"})
    assert plan["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_14_field_verification_does_not_consume_inventory():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    res_doc = {
        "resource_id": "RES-INV01",
        "resource_name": "Inflatable Rescue Boat",
        "available_quantity": 10,
        "allocated_quantity": 0,
    }
    await db["resources"].insert_one(res_doc)

    rep_doc = {
        "report_id": "RES-INVREP01",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    req = FieldVerificationCreateRequest(
        target_id="RES-INVREP01",
        verification_status=FieldVerificationStatus.FIELD_VERIFIED,
        observation_category=FieldObservationCategory.INCIDENT_CONFIRMED,
    )
    actor = {"id": "VOL-8", "full_name": "Volunteer", "role": "VOLUNTEER"}

    await FieldVerificationService.verify_ground_truth(req=req, actor=actor, db=db)

    resource = await db["resources"].find_one({"resource_id": "RES-INV01"})
    assert resource["available_quantity"] == 10
    assert resource["allocated_quantity"] == 0


@pytest.mark.asyncio
async def test_15_timeline_contains_genuine_report_event():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    rep_doc = {
        "report_id": "RES-TL01",
        "emergency_type": "Flood",
        "description": "Flooding in sector 4",
        "citizen_name": "Aarav Gupta",
        "citizen_impact_level": "HIGH",
        "created_at": now,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    timeline = await IncidentEvolutionService.get_evolution_timeline(target_id="RES-TL01", db=db)
    assert timeline.total_events >= 1
    assert any(e.category == IncidentEvolutionCategory.REPORT for e in timeline.events)
    intake_ev = next(e for e in timeline.events if e.category == IncidentEvolutionCategory.REPORT)
    assert "Aarav Gupta" in intake_ev.summary


@pytest.mark.asyncio
async def test_16_timeline_contains_genuine_field_verification_event():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    rep_doc = {
        "report_id": "RES-TL02",
        "emergency_type": "Fire",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    req = FieldVerificationCreateRequest(
        target_id="RES-TL02",
        verification_status=FieldVerificationStatus.FIELD_VERIFIED,
        observation_category=FieldObservationCategory.INCIDENT_CONFIRMED,
        notes="On-scene confirmation of fire",
    )
    actor = {"id": "OFF-9", "full_name": "Fire Chief Roy", "role": "EMERGENCY_OFFICER"}
    await FieldVerificationService.verify_ground_truth(req=req, actor=actor, db=db)

    timeline = await IncidentEvolutionService.get_evolution_timeline(target_id="RES-TL02", db=db)
    assert any(e.category == IncidentEvolutionCategory.FIELD_VERIFICATION for e in timeline.events)
    fv_ev = next(e for e in timeline.events if e.category == IncidentEvolutionCategory.FIELD_VERIFICATION)
    assert fv_ev.actor_name == "Fire Chief Roy"


@pytest.mark.asyncio
async def test_17_timeline_ordering_is_deterministic():
    db = MockDatabase()
    t0 = datetime(2026, 9, 10, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 10, 10, 15, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 10, 10, 30, 0, tzinfo=timezone.utc)

    rep_doc = {
        "report_id": "RES-ORD01",
        "emergency_type": "Medical Emergency",
        "created_at": t0,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    await db["timeline_events"].insert_one({
        "event_id": "EVT-1",
        "report_id": "RES-ORD01",
        "event_type": "REPORT_ACKNOWLEDGED",
        "details": "Officer acknowledged",
        "timestamp": t1,
    })
    await db["field_verifications"].insert_one({
        "verification_id": "FLV-1",
        "target_id": "RES-ORD01",
        "responder_name": "Paramedic",
        "responder_role": "VOLUNTEER",
        "verification_status": "FIELD_VERIFIED",
        "observation_category": "MEDICAL_NEED_OBSERVED",
        "submitted_at": t2,
    })

    timeline = await IncidentEvolutionService.get_evolution_timeline(target_id="RES-ORD01", db=db, order="asc")
    assert len(timeline.events) == 3
    assert timeline.events[0].timestamp <= timeline.events[1].timestamp <= timeline.events[2].timestamp


@pytest.mark.asyncio
async def test_18_duplicate_event_is_not_shown_twice():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    rep_doc = {
        "report_id": "RES-DEDUP",
        "created_at": now,
        "timeline": [
            {"event_id": "EVT-SAME", "event_type": "NOTE_ADDED", "details": "Note 1", "timestamp": now}
        ],
    }
    await db["citizen_reports"].insert_one(rep_doc)

    # Insert same event_id into timeline_events collection
    await db["timeline_events"].insert_one({
        "event_id": "EVT-SAME",
        "report_id": "RES-DEDUP",
        "event_type": "NOTE_ADDED",
        "details": "Note 1",
        "timestamp": now,
    })

    timeline = await IncidentEvolutionService.get_evolution_timeline(target_id="RES-DEDUP", db=db)
    # Count occurrences of EVT-SAME
    matching = [e for e in timeline.events if e.event_id == "EVT-SAME"]
    assert len(matching) == 1, "Duplicate event IDs must be deduplicated in timeline aggregator"


@pytest.mark.asyncio
async def test_19_existing_phase_a_verification_remains_pass():
    from app.services.evidence_verification_service import EvidenceVerificationService
    now = datetime.now(timezone.utc)
    rep = {
        "report_id": "RES-A01",
        "citizen_name": "Test Citizen",
        "emergency_type": "Flood",
        "citizen_impact_level": "HIGH",
        "description": "High water levels observed",
        "evidence": {
            "evidence_id": "EVD-01",
            "source": "BROWSER_CAMERA",
            "file_url": "/uploads/citizen_evidence/EVD-01.jpg",
            "content_hash": "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0",
            "client_capture_timestamp": (now - timedelta(minutes=2)).isoformat(),
            "latitude": 28.6139,
            "longitude": 77.2090,
            "accuracy_meters": 10.0,
        },
        "location": {"latitude": 28.6139, "longitude": 77.2090, "address": "Delhi"},
        "created_at": now,
    }
    ver_res = EvidenceVerificationService.evaluate_report_evidence(rep, eval_time=now)
    assert ver_res.confidence_band.value == "HIGH"
    assert ver_res.verification_status.value == "PARTIALLY_VERIFIED"


@pytest.mark.asyncio
async def test_20_existing_phase_b_corroboration_remains_pass():
    now = datetime.now(timezone.utc)
    target = {
        "report_id": "RES-B01",
        "emergency_type": "Flood",
        "description": "Heavy flood",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    peer = {
        "report_id": "RES-B02",
        "emergency_type": "Flood",
        "description": "Submerged street",
        "location": {"latitude": 28.6142, "longitude": 77.2093},
        "created_at": now - timedelta(minutes=10),
    }
    res = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[peer],
        candidate_sensors=[],
        candidate_alerts=[],
        eval_time=now,
    )
    assert res.corroboration_status == CorroborationStatus.PARTIALLY_CORROBORATED
    assert res.supporting_source_count == 1


@pytest.mark.asyncio
async def test_21_existing_sensor_live_monitoring_remains_pass():
    now = datetime.now(timezone.utc)
    target = {
        "report_id": "RES-SEN01",
        "emergency_type": "Flood",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    sensor = {
        "sensor_id": "SENS-WATER-01",
        "sensor_type": "WATER_LEVEL",
        "latitude": 28.6145,
        "longitude": 77.2095,
        "coverage": {"radius_meters": 2000.0},
        "current_reading": 3.8,
        "unit": "meters",
        "threshold": 2.5,
        "in_alert": True,
        "last_updated": now,
    }
    alert = {
        "alert_id": "ALT-01",
        "sensor_id": "SENS-WATER-01",
        "status": "ACTIVE_BREACH",
        "value": 3.8,
        "created_at": now,
    }
    res = EvidenceCorroborationService.evaluate_report_corroboration(
        target_report=target,
        candidate_reports=[],
        candidate_sensors=[sensor],
        candidate_alerts=[alert],
        eval_time=now,
    )
    assert res.supporting_source_count == 1
    assert any(s.source_type == CorroborationSourceType.SENSOR_EVENT for s in res.supporting_sources)


@pytest.mark.asyncio
async def test_22_zero_dummy_data_audit():
    db = MockDatabase()
    # Empty DB querying timeline returns 0 events, NOT fake generated records
    timeline = await IncidentEvolutionService.get_evolution_timeline(target_id="RES-EMPTY", db=db)
    assert timeline.total_events == 0
    assert len(timeline.events) == 0


@pytest.mark.asyncio
async def test_23_repeated_refresh_creates_no_duplicate_records():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    rep_doc = {
        "report_id": "RES-REFRESH",
        "emergency_type": "Flood",
        "created_at": now,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    t1 = await IncidentEvolutionService.get_evolution_timeline(target_id="RES-REFRESH", db=db)
    t2 = await IncidentEvolutionService.get_evolution_timeline(target_id="RES-REFRESH", db=db)
    t3 = await IncidentEvolutionService.get_evolution_timeline(target_id="RES-REFRESH", db=db)

    assert t1.total_events == t2.total_events == t3.total_events == 1
    # Check that database collection count was NOT increased by reading
    count = await db["citizen_reports"].count_documents({})
    assert count == 1


@pytest.mark.asyncio
async def test_24_field_verification_condition_changed_emits_correct_event():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    rep_doc = {
        "report_id": "RES-COND01",
        "emergency_type": "Road Accident",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "created_at": now,
    }
    await db["citizen_reports"].insert_one(rep_doc)

    req = FieldVerificationCreateRequest(
        target_id="RES-COND01",
        verification_status=FieldVerificationStatus.CONDITION_CHANGED,
        observation_category=FieldObservationCategory.ROAD_BLOCKED,
        notes="Debris blocking lanes 1 and 2.",
    )
    actor = {"id": "VOL-88", "full_name": "Traffic Warden", "role": "VOLUNTEER"}

    record = await FieldVerificationService.verify_ground_truth(req=req, actor=actor, db=db)
    assert record.verification_status == FieldVerificationStatus.CONDITION_CHANGED
    assert record.observation_category == FieldObservationCategory.ROAD_BLOCKED

    timeline = await IncidentEvolutionService.get_evolution_timeline(target_id="RES-COND01", db=db)
    ev_types = [e.event_type for e in timeline.events]
    assert "FIELD_CONDITION_CHANGED" in ev_types


@pytest.mark.asyncio
async def test_25_field_verification_pagination_and_filtering():
    db = MockDatabase()
    now = datetime.now(timezone.utc)
    for i in range(5):
        doc = {
            "verification_id": f"FLV-PAG{i}",
            "target_id": "RES-PAG01" if i < 3 else "RES-PAG02",
            "responder_id": "VOL-PAG1",
            "responder_name": "Volunteer 1",
            "responder_role": "VOLUNTEER",
            "verification_status": "FIELD_VERIFIED",
            "observation_category": "INCIDENT_CONFIRMED",
            "notes": f"Verification {i}",
            "observed_at": now,
            "submitted_at": now,
            "created_at": now,
        }
        await db["field_verifications"].insert_one(doc)

    items_all, total_all = await FieldVerificationService.list_verifications(page=1, limit=10, db=db)
    assert total_all == 5

    items_filter, total_filter = await FieldVerificationService.list_verifications(target_id="RES-PAG01", page=1, limit=10, db=db)
    assert total_filter == 3
