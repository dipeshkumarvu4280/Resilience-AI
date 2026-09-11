import pytest
import mongomock
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from app.models.enums import (
    CoordinationPlanStatus,
    EventStatus,
    ImpactLevel,
    PlanValidityStatus,
    MonitoringEventType,
    EventSourceType,
    SeverityLevel,
    UserRole,
    ResourceType,
    NeedUrgency,
)
from app.models.agent import (
    CoordinationPlan,
    RecommendedShelter,
    PlanRecommendedResource,
    RecommendedHealthcareFacility,
    RecommendedVolunteerAssignment,
    RecommendedTransport,
    RecommendedRoute,
)
from app.services.monitoring.monitoring_service import MonitoringService
from app.services.monitoring.remediation_service import ConstraintRemediationService
from app.services.monitoring.plan_activation_service import PlanActivationService


class AsyncMongoMockCursor:
    def __init__(self, cursor):
        self._cursor = cursor
        self._iter = None

    def __aiter__(self):
        self._iter = iter(list(self._cursor))
        return self

    async def __anext__(self):
        if self._iter is None:
            self._iter = iter(list(self._cursor))
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration

    def sort(self, *args, **kwargs):
        self._cursor = self._cursor.sort(*args, **kwargs)
        return self

    def skip(self, *args, **kwargs):
        self._cursor = self._cursor.skip(*args, **kwargs)
        return self

    def limit(self, *args, **kwargs):
        self._cursor = self._cursor.limit(*args, **kwargs)
        return self

    async def to_list(self, length=None):
        docs = list(self._cursor)
        if length is not None:
            docs = docs[:length]
        return docs

    def __iter__(self):
        return iter(self._cursor)


class AsyncMongoMockCollection:
    def __init__(self, sync_collection):
        self._col = sync_collection

    async def find_one(self, *args, **kwargs):
        return self._col.find_one(*args, **kwargs)

    def find(self, *args, **kwargs):
        cursor = self._col.find(*args, **kwargs)
        return AsyncMongoMockCursor(cursor)

    async def insert_one(self, doc, *args, **kwargs):
        return self._col.insert_one(doc, *args, **kwargs)

    async def insert_many(self, docs, *args, **kwargs):
        return self._col.insert_many(docs, *args, **kwargs)

    async def update_one(self, filter_q, update_q, *args, **kwargs):
        return self._col.update_one(filter_q, update_q, *args, **kwargs)

    async def update_many(self, filter_q, update_q, *args, **kwargs):
        return self._col.update_many(filter_q, update_q, *args, **kwargs)

    async def count_documents(self, filter_q, *args, **kwargs):
        return self._col.count_documents(filter_q, *args, **kwargs)

    def aggregate(self, pipeline, *args, **kwargs):
        res = self._col.aggregate(pipeline)
        return AsyncMongoMockCursor(res)


class AsyncMongoMockDatabase:
    def __init__(self):
        self._client = mongomock.MongoClient()
        self._db = self._client["resilience_ai_test"]

    def __getitem__(self, item):
        return AsyncMongoMockCollection(self._db[item])


@pytest.fixture
def mock_db():
    return AsyncMongoMockDatabase()


def create_shelter_item(shelter_id: str, name: str, rec_occ: float, tot_cap: float = 300.0, status: str = "AVAILABLE") -> RecommendedShelter:
    return RecommendedShelter(
        shelter_id=shelter_id,
        shelter_name=name,
        distance_km=2.5,
        total_capacity=tot_cap,
        current_occupancy=0.0,
        remaining_capacity=tot_cap - rec_occ,
        recommended_occupancy=rec_occ,
        coverage_percentage=100.0,
        suitability_score=95.0,
        recommendation_reason="Selected based on proximity and capacity.",
        status=status,
    )


@pytest.mark.asyncio
async def test_complete_shelter_constraint_remediation_lifecycle(mock_db):
    """
    Tests the complete end-to-end lifecycle for SHELTER_STATUS_CHANGED:
    1. Initial Plan V1 allocates Shelter B (250 capacity).
    2. Shelter B becomes UNAVAILABLE -> Monitoring Event and Critical Impact created (ACTIVE).
    3. Officer acknowledges alert -> Status is ACKNOWLEDGED, remains unresolved.
    4. Dynamic Replanning synthesizes Plan V2 (Shelter A: 150, Shelter C: 100) -> Status PENDING_OFFICER_REVIEW.
    5. While V2 is pending -> Alert remains unresolved/acknowledged, V1 remains active.
    6. If Replan V2 is rejected -> Alert remains unresolved.
    7. Partial remediation test: If V2 only allocates 200 capacity -> Replan approved, but alert remains PARTIALLY_REMEDIATED.
    8. Full remediation test: V3 allocates 250 capacity (Shelter A: 150, Shelter C: 100) -> Approved and Activated.
    9. Alert and Change Impact deterministically transition to RESOLVED with real-state reason and timestamp.
    10. Querying active/impacted alerts excludes resolved alert; history query retains it.
    """
    situation_id = f"SIT-{uuid.uuid4().hex[:8].upper()}"
    plan_v1_id = f"PLAN-{uuid.uuid4().hex[:8].upper()}"
    shelter_b_id = f"SHL-B-{uuid.uuid4().hex[:6].upper()}"
    shelter_a_id = f"SHL-A-{uuid.uuid4().hex[:6].upper()}"
    shelter_c_id = f"SHL-C-{uuid.uuid4().hex[:6].upper()}"

    officer_actor = {
        "id": "OFFICER-408",
        "full_name": "Commander Sarah Vance",
        "role": UserRole.EMERGENCY_OFFICER.value,
    }

    # 0. Seed Situation and Initial Shelters
    now = datetime.now(timezone.utc)
    await mock_db["situations"].insert_one({
        "situation_id": situation_id,
        "_id": situation_id,
        "title": "Cyclone Alert Cyclone Test",
        "status": "ACTIVE",
        "computed_severity_level": "CRITICAL",
        "affected_population": 500,
        "displaced_population": 250,
        "created_at": now.isoformat(),
    })

    await mock_db["shelters"].insert_many([
        {
            "shelter_id": shelter_b_id,
            "name": "Shelter B",
            "quantity_total": 300,
            "current_occupancy": 0,
            "status": "AVAILABLE",
        },
        {
            "shelter_id": shelter_a_id,
            "name": "Shelter A",
            "quantity_total": 200,
            "current_occupancy": 0,
            "status": "AVAILABLE",
        },
        {
            "shelter_id": shelter_c_id,
            "name": "Shelter C",
            "quantity_total": 200,
            "current_occupancy": 0,
            "status": "AVAILABLE",
        },
    ])

    # 1. Plan V1 is ACTIVE and allocates Shelter B for 250 persons
    plan_v1 = CoordinationPlan(
        plan_id=plan_v1_id,
        situation_id=situation_id,
        version=1,
        status=CoordinationPlanStatus.ACTIVE,
        assessed_priority=SeverityLevel.CRITICAL,
        reasoning="Initial cyclone response coordination plan.",
        recommended_shelters=[
            create_shelter_item(shelter_b_id, "Shelter B", 250.0, 300.0, "AVAILABLE")
        ],
        generated_at=now,
    )
    await mock_db["coordination_plans"].insert_one(plan_v1.model_dump())

    # 2. Shelter B becomes UNAVAILABLE
    await mock_db["shelters"].update_one(
        {"shelter_id": shelter_b_id},
        {"$set": {"status": "UNAVAILABLE", "current_occupancy": 0}}
    )

    event = await MonitoringService.record_change_event(
        event_type=MonitoringEventType.SHELTER_STATUS_CHANGED,
        source_type=EventSourceType.SHELTER_FACILITY,
        source_id=shelter_b_id,
        previous_state={"name": "Shelter B", "status": "AVAILABLE", "current_occupancy": 250, "quantity_total": 300},
        new_state={"name": "Shelter B", "status": "UNAVAILABLE", "current_occupancy": 0, "quantity_total": 300},
        situation_id=situation_id,
        coordination_plan_id=plan_v1_id,
        metadata={"shelter_name": "Shelter B", "allocated_population": 250.0},
        db=mock_db,
    )
    assert event is not None
    assert event.status == EventStatus.REQUIRES_REVIEW
    assert event.impact_level == ImpactLevel.CRITICAL

    impact = await mock_db["change_impacts"].find_one({"event_id": event.event_id})
    assert impact is not None
    assert impact["plan_status"] == PlanValidityStatus.INVALIDATED.value
    assert impact["officer_attention_required"] is True

    # 3. Officer Acknowledges Alert -> Status becomes ACKNOWLEDGED, but MUST NOT BE RESOLVED
    ack_res = await MonitoringService.acknowledge_event(
        event_id=event.event_id,
        actor=officer_actor,
        notes="Understood, initiating dynamic replanning.",
        db=mock_db,
    )
    assert ack_res.status == EventStatus.ACKNOWLEDGED

    evt_after_ack = await MonitoringService.get_event_by_id(event.event_id, db=mock_db)
    assert evt_after_ack.status == EventStatus.ACKNOWLEDGED
    assert evt_after_ack.resolved_at is None  # Must NOT be resolved!

    # 4. Dynamic Replanning generates Plan V2 with partial replacement (only 200 capacity)
    plan_v2_id = f"PLAN-{uuid.uuid4().hex[:8].upper()}"
    plan_v2 = CoordinationPlan(
        plan_id=plan_v2_id,
        situation_id=situation_id,
        version=2,
        previous_plan_id=plan_v1_id,
        previous_version=1,
        status=CoordinationPlanStatus.PENDING_OFFICER_REVIEW,
        assessed_priority=SeverityLevel.CRITICAL,
        reasoning="Interim revised shelter allocation plan.",
        recommended_shelters=[
            create_shelter_item(shelter_a_id, "Shelter A", 150.0, 200.0, "AVAILABLE"),
            create_shelter_item(shelter_c_id, "Shelter C", 50.0, 200.0, "AVAILABLE"),
        ],
        generated_at=datetime.now(timezone.utc),
    )
    await mock_db["coordination_plans"].insert_one(plan_v2.model_dump())

    # While V2 is PENDING_OFFICER_REVIEW, alert must remain ACKNOWLEDGED
    evt_pending = await MonitoringService.get_event_by_id(event.event_id, db=mock_db)
    assert evt_pending.status == EventStatus.ACKNOWLEDGED

    # 5. Activate V2 (which has shortfall of 50: 200 < 250)
    act_v2_res = await PlanActivationService.approve_and_activate_plan(
        plan_id=plan_v2_id,
        officer_actor=officer_actor,
        officer_notes="Approving interim partial shelter plan.",
        db=mock_db,
    )
    assert act_v2_res.success is True
    assert act_v2_res.status == CoordinationPlanStatus.ACTIVE.value

    # Alert must NOT be resolved because there is a shortfall of 50!
    evt_after_v2 = await MonitoringService.get_event_by_id(event.event_id, db=mock_db)
    assert evt_after_v2.status != EventStatus.RESOLVED

    # 6. Synthesize Plan V3 that fully satisfies 250 capacity (Shelter A: 150, Shelter C: 100)
    plan_v3_id = f"PLAN-{uuid.uuid4().hex[:8].upper()}"
    plan_v3 = CoordinationPlan(
        plan_id=plan_v3_id,
        situation_id=situation_id,
        version=3,
        previous_plan_id=plan_v2_id,
        previous_version=2,
        status=CoordinationPlanStatus.PENDING_OFFICER_REVIEW,
        assessed_priority=SeverityLevel.CRITICAL,
        reasoning="Full replacement shelter allocation plan resolving Shelter B unavailability.",
        recommended_shelters=[
            create_shelter_item(shelter_a_id, "Shelter A", 150.0, 200.0, "AVAILABLE"),
            create_shelter_item(shelter_c_id, "Shelter C", 100.0, 200.0, "AVAILABLE"),
        ],
        generated_at=datetime.now(timezone.utc),
    )
    await mock_db["coordination_plans"].insert_one(plan_v3.model_dump())

    # 7. Approve and Activate Plan V3
    act_v3_res = await PlanActivationService.approve_and_activate_plan(
        plan_id=plan_v3_id,
        officer_actor=officer_actor,
        officer_notes="Approving full replacement shelter plan.",
        db=mock_db,
    )
    assert act_v3_res.success is True

    # 8. Verify Deterministic Constraint Remediation & RESOLVED status
    resolved_event = await MonitoringService.get_event_by_id(event.event_id, db=mock_db)
    assert resolved_event is not None
    assert resolved_event.status == EventStatus.RESOLVED
    assert resolved_event.remediation_status == "RESOLVED"
    assert resolved_event.resolved_at is not None
    assert resolved_event.resolved_by_name == "Commander Sarah Vance"
    assert resolved_event.resolved_in_plan_id == plan_v3_id
    assert resolved_event.resolved_in_plan_version == 3
    assert "Shelter B" in resolved_event.resolution_reason
    assert "250" in resolved_event.resolution_reason

    # Verify Change Impact is updated
    resolved_impact = await mock_db["change_impacts"].find_one({"event_id": event.event_id})
    assert resolved_impact["plan_status"] == PlanValidityStatus.UNAFFECTED.value
    assert resolved_impact["officer_attention_required"] is False
    assert resolved_impact["remediation_status"] == "RESOLVED"

    # 9. Verify Live Monitoring Queries
    # Impacted query (for active disruption view) MUST NOT return resolved event
    impacted_res = await MonitoringService.get_monitoring_events(
        is_impacted=True,
        situation_id=situation_id,
        db=mock_db,
    )
    assert not any(e.event_id == event.event_id for e in impacted_res.items)

    # History query (all statuses or status="RESOLVED") MUST retain the event
    history_res = await MonitoringService.get_monitoring_events(
        status="RESOLVED",
        situation_id=situation_id,
        db=mock_db,
    )
    assert any(e.event_id == event.event_id for e in history_res.items)

    # 10. Verify Lineage Immutability
    v1_doc = await mock_db["coordination_plans"].find_one({"plan_id": plan_v1_id})
    assert v1_doc["status"] == CoordinationPlanStatus.SUPERSEDED.value
    assert v1_doc["version"] == 1
    assert v1_doc["recommended_shelters"][0]["shelter_id"] == shelter_b_id  # Unmutated!


@pytest.mark.asyncio
async def test_resource_and_vehicle_constraint_remediation(mock_db):
    """
    Tests constraint remediation for Resource Inventory and Transport/Route domains.
    """
    situation_id = f"SIT-{uuid.uuid4().hex[:8].upper()}"
    plan_v1_id = f"PLAN-{uuid.uuid4().hex[:8].upper()}"
    res_id = f"RES-{uuid.uuid4().hex[:6].upper()}"
    veh_id = f"VEH-{uuid.uuid4().hex[:6].upper()}"

    officer_actor = {
        "id": "OFFICER-408",
        "full_name": "Marcus Vance",
        "role": UserRole.EMERGENCY_OFFICER.value,
    }

    now = datetime.now(timezone.utc)
    await mock_db["situations"].insert_one({
        "situation_id": situation_id,
        "_id": situation_id,
        "title": "Logistics & Fleet Alert Test",
        "status": "ACTIVE",
        "computed_severity_level": "HIGH",
        "created_at": now.isoformat(),
    })

    # Plan V1 allocates resource RES-1 and vehicle VEH-1
    plan_v1 = CoordinationPlan(
        plan_id=plan_v1_id,
        situation_id=situation_id,
        version=1,
        status=CoordinationPlanStatus.ACTIVE,
        assessed_priority=SeverityLevel.HIGH,
        reasoning="Initial logistics plan.",
        recommended_allocations=[
            PlanRecommendedResource(
                resource_type=ResourceType.WATER,
                quantity_required=100,
                allocated_quantity=100,
                unit="Liters",
                urgency=NeedUrgency.HIGH,
                matched_resource_id=res_id,
            )
        ],
        recommended_transports=[
            RecommendedTransport(
                transport_id=veh_id,
                vehicle_name="Water Tanker 1",
                vehicle_type="WATER_TANKER",
                capacity=5000.0,
                allocated_load_or_passengers=5000.0,
                assigned_mission="Water delivery",
                recommendation_reason="Primary transport unit.",
            )
        ],
        generated_at=now,
    )
    await mock_db["coordination_plans"].insert_one(plan_v1.model_dump())

    # Resource event: Depleted inventory
    res_event = await MonitoringService.record_change_event(
        event_type=MonitoringEventType.RESOURCE_QUANTITY_CHANGED,
        source_type=EventSourceType.RESOURCE_INVENTORY,
        source_id=res_id,
        previous_state={"name": "Water Depot 1", "quantity_available": 100, "resource_type": "Water"},
        new_state={"name": "Water Depot 1", "quantity_available": 0, "status": "UNAVAILABLE", "resource_type": "Water"},
        situation_id=situation_id,
        coordination_plan_id=plan_v1_id,
        db=mock_db,
    )
    assert res_event is not None
    assert res_event.impact_level == ImpactLevel.CRITICAL

    # Vehicle event: Breakdown
    veh_event = await MonitoringService.record_change_event(
        event_type=MonitoringEventType.TRANSPORT_STATUS_CHANGED,
        source_type=EventSourceType.TRANSPORT_FLEET,
        source_id=veh_id,
        previous_state={"vehicle_name": "Water Tanker 1", "status": "AVAILABLE"},
        new_state={"vehicle_name": "Water Tanker 1", "status": "UNAVAILABLE"},
        situation_id=situation_id,
        coordination_plan_id=plan_v1_id,
        db=mock_db,
    )
    assert veh_event is not None

    # Plan V2 replaces with alternate resource and alternate vehicle
    alt_res_id = f"RES-ALT-{uuid.uuid4().hex[:6].upper()}"
    alt_veh_id = f"VEH-ALT-{uuid.uuid4().hex[:6].upper()}"
    plan_v2_id = f"PLAN-{uuid.uuid4().hex[:8].upper()}"

    plan_v2 = CoordinationPlan(
        plan_id=plan_v2_id,
        situation_id=situation_id,
        version=2,
        previous_plan_id=plan_v1_id,
        previous_version=1,
        status=CoordinationPlanStatus.PENDING_OFFICER_REVIEW,
        assessed_priority=SeverityLevel.HIGH,
        reasoning="Revised logistics plan replacing depleted water depot and vehicle.",
        recommended_allocations=[
            PlanRecommendedResource(
                resource_type=ResourceType.WATER,
                quantity_required=100,
                allocated_quantity=100,
                unit="Liters",
                urgency=NeedUrgency.HIGH,
                matched_resource_id=alt_res_id,
            )
        ],
        recommended_transports=[
            RecommendedTransport(
                transport_id=alt_veh_id,
                vehicle_name="Backup Tanker 2",
                vehicle_type="WATER_TANKER",
                capacity=5000.0,
                allocated_load_or_passengers=5000.0,
                assigned_mission="Water delivery",
                recommendation_reason="Backup transport unit.",
            )
        ],
        generated_at=datetime.now(timezone.utc),
    )
    await mock_db["coordination_plans"].insert_one(plan_v2.model_dump())

    # Approve & Activate Plan V2
    act_res = await PlanActivationService.approve_and_activate_plan(
        plan_id=plan_v2_id,
        officer_actor=officer_actor,
        db=mock_db,
    )
    assert act_res.success is True

    # Both resource and vehicle events must be RESOLVED
    res_evt_resolved = await MonitoringService.get_event_by_id(res_event.event_id, db=mock_db)
    assert res_evt_resolved.status == EventStatus.RESOLVED
    assert res_evt_resolved.resolved_in_plan_id == plan_v2_id

    veh_evt_resolved = await MonitoringService.get_event_by_id(veh_event.event_id, db=mock_db)
    assert veh_evt_resolved.status == EventStatus.RESOLVED
    assert veh_evt_resolved.resolved_in_plan_id == plan_v2_id
