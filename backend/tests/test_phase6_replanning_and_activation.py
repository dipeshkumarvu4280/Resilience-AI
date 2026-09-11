import pytest
import mongomock
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from app.models.enums import (
    MonitoringEventType,
    EventSourceType,
    EventStatus,
    ImpactLevel,
    PlanValidityStatus,
    OperationalDomain,
    AgentName,
    SeverityLevel,
    NeedUrgency,
    ResourceType,
    CoordinationPlanStatus,
    PlanReviewAction,
    DiffChangeType,
    TimelineEventType,
)
from app.models.monitoring import (
    MonitoringEvent,
    ChangeImpactResult,
    PlanApprovalRequest,
    PlanModifyRequest,
    PlanRejectRequest,
)
from app.models.agent import (
    CoordinationPlan,
    PlanRecommendedResource,
    RecommendedShelter,
    RecommendedHealthcareFacility,
    RecommendedVolunteerAssignment,
    RecommendedTransport,
    RecommendedRoute,
)
from app.services.monitoring.replanning_service import DynamicReplanningService
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


def create_sample_active_plan(situation_id="SIT-001", plan_id="PLAN-001"):
    return {
        "_id": plan_id,
        "plan_id": plan_id,
        "situation_id": situation_id,
        "assessed_priority": SeverityLevel.CRITICAL.value,
        "status": CoordinationPlanStatus.ACTIVE.value,
        "version": 1,
        "is_revised_version": False,
        "generated_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "reasoning": "Baseline multi-agent coordination plan.",
        "state_fingerprint": "fp-init-001",
        "recommended_allocations": [
            {
                "resource_type": "Water",
                "quantity_required": 100.0,
                "unit": "LITRES",
                "urgency": "HIGH",
                "matched_resource_id": "RES-001",
                "matched_resource_name": "Bottled Drinking Water",
                "allocated_quantity": 100.0,
                "depot_location": "North Depot",
            }
        ],
        "recommended_shelters": [
            {
                "shelter_id": "SHELTER-001",
                "shelter_name": "Community Center A",
                "distance_km": 2.5,
                "total_capacity": 100.0,
                "current_occupancy": 10.0,
                "remaining_capacity": 90.0,
                "recommended_occupancy": 50.0,
                "coverage_percentage": 100.0,
                "suitability_score": 95.0,
                "recommendation_reason": "High capacity nearby facility.",
            }
        ],
        "recommended_facilities": [
            {
                "facility_id": "HOSP-001",
                "facility_name": "Central District Hospital",
                "facility_type": "Hospital",
                "distance_km": 3.0,
                "total_beds": 100.0,
                "available_beds": 20.0,
                "allocated_patients": 5.0,
                "coverage_percentage": 100.0,
                "recommendation_reason": "Level 1 trauma center.",
            }
        ],
        "recommended_volunteers": [
            {
                "volunteer_id": "VOL-001",
                "volunteer_name": "John Doe",
                "role_or_skill": "First Aid Responder",
                "assigned_operation": "First Aid Station A",
                "recommendation_reason": "Certified paramedic volunteer.",
            }
        ],
        "recommended_transports": [
            {
                "transport_id": "TRUCK-001",
                "vehicle_name": "Rescue Truck 1",
                "vehicle_type": "High Clearance Truck",
                "capacity": 5000.0,
                "allocated_load_or_passengers": 2500.0,
                "assigned_mission": "Water & Supply Transport",
                "recommendation_reason": "Flood-capable heavy logistics.",
            }
        ],
        "recommended_routes": [
            {
                "route_id": "ROUTE-001",
                "origin_name": "North Depot",
                "destination_name": "Community Center A",
                "origin_coordinates": {"latitude": 19.100, "longitude": 72.880},
                "destination_coordinates": {"latitude": 19.080, "longitude": 72.870},
                "distance_km": 4.5,
                "estimated_duration_minutes": 15.0,
                "assigned_mission": "Supply Transport",
                "recommendation_reason": "Fastest and safest dry route.",
            }
        ],
        "agent_results": {},
        "participating_agents": [],
    }


@pytest.mark.asyncio
async def test_material_change_evaluation():
    """Test that material vs non-material changes are correctly classified."""
    active_plan = CoordinationPlan(**create_sample_active_plan("SIT-001", "PLAN-001"))

    # Critical impact with INVALIDATED plan status
    impact_critical = ChangeImpactResult(
        impact_id="IMP-001",
        event_id="EVT-001",
        situation_id="SIT-001",
        coordination_plan_id="PLAN-001",
        impact_level=ImpactLevel.CRITICAL,
        plan_status=PlanValidityStatus.INVALIDATED,
        changed_entity="Expressway Corridor",
        changed_fields=["obstruction"],
        affected_domains=[OperationalDomain.ROUTE, OperationalDomain.TRANSPORT],
        affected_agents=[AgentName.ROUTE_AGENT],
        dependency_chain=[AgentName.ROUTE_AGENT, AgentName.CONFLICT_RESOLUTION_AGENT],
        affected_plan_components=["ROUTE-001"],
        explanation="Main expressway blocked by landslip.",
        officer_attention_required=True,
    )

    is_material = DynamicReplanningService.evaluate_material_change(impact_critical, active_plan)
    assert is_material is True

    # Low non-material impact with UNAFFECTED plan status
    impact_low = ChangeImpactResult(
        impact_id="IMP-002",
        event_id="EVT-002",
        situation_id="SIT-001",
        coordination_plan_id="PLAN-001",
        impact_level=ImpactLevel.LOW,
        plan_status=PlanValidityStatus.UNAFFECTED,
        changed_entity="Remote Depot Stock",
        changed_fields=["quantity"],
        explanation="Small non-allocated quantity change.",
        officer_attention_required=False,
    )

    is_material_low = DynamicReplanningService.evaluate_material_change(impact_low, active_plan)
    assert is_material_low is False


@pytest.mark.asyncio
async def test_resolve_selective_execution_set():
    """Test topological resolution of affected agents and downstream dependencies."""
    triggers = [AgentName.RESOURCE_COORDINATION_AGENT]
    ordered_agents = DynamicReplanningService.resolve_selective_execution_set(triggers)
    assert AgentName.RESOURCE_COORDINATION_AGENT in ordered_agents
    assert AgentName.CONFLICT_RESOLUTION_AGENT in ordered_agents
    assert AgentName.SHELTER_AGENT not in ordered_agents
    assert AgentName.HEALTHCARE_AGENT not in ordered_agents


@pytest.mark.asyncio
async def test_replan_from_impact_selective_execution_and_preservation(mock_db):
    """
    Test that re-planning executes ONLY selective agents, preserves unaffected components,
    and sets status to PENDING_OFFICER_REVIEW without mutating real inventory.
    """
    situation_id = "SIT-TEST-001"
    active_plan_dict = create_sample_active_plan(situation_id, "PLAN-ACT-001")
    await mock_db["coordination_plans"].insert_one(active_plan_dict)

    await mock_db["situations"].insert_one({
        "_id": situation_id,
        "situation_id": situation_id,
        "title": "Riverside Inundation Zone",
        "emergency_type": "FLOOD",
        "computed_severity_level": "CRITICAL",
        "report_ids": ["REP-1", "REP-2"],
        "center_location": {"latitude": 19.0760, "longitude": 72.8777},
    })

    event = MonitoringEvent(
        event_id="EVT-ROUTE-001",
        event_type=MonitoringEventType.ROUTE_OBSTRUCTION_CHANGED,
        source_type=EventSourceType.ROUTE_NETWORK,
        source_id="ROUTE-001",
        severity=SeverityLevel.HIGH,
        situation_id=situation_id,
        coordination_plan_id="PLAN-ACT-001",
        impact_level=ImpactLevel.HIGH,
        event_fingerprint="fp-route-001",
        previous_state={"status": "CLEAR"},
        new_state={"status": "SUBMERGED"},
        changed_fields=["status"],
    )
    await mock_db["monitoring_events"].insert_one(event.model_dump())

    impact = ChangeImpactResult(
        impact_id="IMP-ROUTE-001",
        event_id="EVT-ROUTE-001",
        situation_id=situation_id,
        coordination_plan_id="PLAN-ACT-001",
        impact_level=ImpactLevel.HIGH,
        plan_status=PlanValidityStatus.REQUIRES_OFFICER_REVIEW,
        changed_entity="Sector 4 Underpass",
        changed_fields=["status"],
        affected_domains=[OperationalDomain.ROUTE],
        affected_agents=[AgentName.ROUTE_AGENT],
        dependency_chain=[AgentName.ROUTE_AGENT, AgentName.CONFLICT_RESOLUTION_AGENT],
        affected_plan_components=["ROUTE-001"],
        explanation="Sector 4 Underpass submerged, reroute required.",
        officer_attention_required=True,
    )
    await mock_db["change_impact_results"].insert_one(impact.model_dump())

    actor = {"id": "OFF-1", "full_name": "Test Officer", "role": "EMERGENCY_OFFICER"}

    revised_plan = await DynamicReplanningService.replan_from_impact(
        impact=impact,
        event=event,
        actor=actor,
        db=mock_db,
    )

    assert revised_plan is not None
    assert revised_plan.status == CoordinationPlanStatus.PENDING_OFFICER_REVIEW
    assert revised_plan.version == 2
    assert revised_plan.previous_plan_id == "PLAN-ACT-001"
    assert revised_plan.is_revised_version is True

    # Verify unaffected components are strictly preserved
    assert len(revised_plan.recommended_allocations) == 1
    assert revised_plan.recommended_allocations[0].matched_resource_id == "RES-001"
    assert len(revised_plan.recommended_shelters) == 1
    assert revised_plan.recommended_shelters[0].shelter_id == "SHELTER-001"
    assert len(revised_plan.recommended_facilities) == 1
    assert revised_plan.recommended_facilities[0].facility_id == "HOSP-001"
    assert len(revised_plan.recommended_volunteers) == 1
    assert revised_plan.recommended_volunteers[0].volunteer_id == "VOL-001"
    assert len(revised_plan.recommended_transports) == 1
    assert revised_plan.recommended_transports[0].transport_id == "TRUCK-001"

    # Verify diff summary exists
    assert revised_plan.diff_summary is not None
    assert len(revised_plan.diff_summary["items"]) >= 1


@pytest.mark.asyncio
async def test_plan_diff_calculation():
    """Test side-by-side plan diff calculation with ADDED, REMOVED, CHANGED, UNCHANGED items."""
    old_plan = CoordinationPlan(
        plan_id="PLAN-OLD",
        situation_id="SIT-001",
        assessed_priority=SeverityLevel.CRITICAL,
        reasoning="Old baseline plan",
        version=1,
        status=CoordinationPlanStatus.ACTIVE,
        recommended_allocations=[
            PlanRecommendedResource(
                resource_type=ResourceType.WATER,
                quantity_required=100.0,
                unit="LITRES",
                urgency=NeedUrgency.HIGH,
                matched_resource_id="RES-001",
                matched_resource_name="Bottled Water",
                allocated_quantity=100.0,
            ),
            PlanRecommendedResource(
                resource_type=ResourceType.FOOD,
                quantity_required=50.0,
                unit="BOXES",
                urgency=NeedUrgency.MEDIUM,
                matched_resource_id="RES-002",
                matched_resource_name="Ration Packs",
                allocated_quantity=50.0,
            ),
        ],
        recommended_shelters=[
            RecommendedShelter(
                shelter_id="SHELTER-001",
                shelter_name="Center A",
                distance_km=2.0,
                total_capacity=100.0,
                current_occupancy=0.0,
                remaining_capacity=100.0,
                recommended_occupancy=50.0,
                coverage_percentage=100.0,
                suitability_score=95.0,
                recommendation_reason="Good capacity",
            )
        ],
    )

    new_plan = CoordinationPlan(
        plan_id="PLAN-NEW",
        situation_id="SIT-001",
        assessed_priority=SeverityLevel.CRITICAL,
        reasoning="Revised plan",
        version=2,
        status=CoordinationPlanStatus.PENDING_OFFICER_REVIEW,
        previous_plan_id="PLAN-OLD",
        recommended_allocations=[
            # RES-001 modified quantity 100 -> 150
            PlanRecommendedResource(
                resource_type=ResourceType.WATER,
                quantity_required=150.0,
                unit="LITRES",
                urgency=NeedUrgency.HIGH,
                matched_resource_id="RES-001",
                matched_resource_name="Bottled Water",
                allocated_quantity=150.0,
            ),
            # RES-002 removed, RES-003 added
            PlanRecommendedResource(
                resource_type=ResourceType.MEDICINE,
                quantity_required=20.0,
                unit="KITS",
                urgency=NeedUrgency.CRITICAL,
                matched_resource_id="RES-003",
                matched_resource_name="First Aid Kits",
                allocated_quantity=20.0,
            ),
        ],
        recommended_shelters=[
            # Shelter-001 unchanged
            RecommendedShelter(
                shelter_id="SHELTER-001",
                shelter_name="Center A",
                distance_km=2.0,
                total_capacity=100.0,
                current_occupancy=0.0,
                remaining_capacity=100.0,
                recommended_occupancy=50.0,
                coverage_percentage=100.0,
                suitability_score=95.0,
                recommendation_reason="Good capacity",
            )
        ],
    )

    diff_result = DynamicReplanningService.compute_plan_diff(old_plan, new_plan)

    assert diff_result.previous_plan_id == "PLAN-OLD"
    assert diff_result.new_plan_id == "PLAN-NEW"
    assert len(diff_result.items) >= 3

    # Check resources diff
    res_diffs = [item for item in diff_result.items if item.category == "Resource"]
    res_diff_map = {d.entity_id: d for d in res_diffs}

    assert res_diff_map["RES-001"].diff_type == DiffChangeType.CHANGED.value
    assert res_diff_map["RES-002"].diff_type == DiffChangeType.REMOVED.value
    assert res_diff_map["RES-003"].diff_type == DiffChangeType.ADDED.value

    # Check shelters diff
    shelter_diffs = [item for item in diff_result.items if item.category == "Shelter"]
    assert len(shelter_diffs) == 1
    assert shelter_diffs[0].diff_type == DiffChangeType.UNCHANGED.value


@pytest.mark.asyncio
async def test_officer_approval_activates_revised_plan(mock_db):
    """Test that Emergency Officer approval atomically activates revised plan and supersedes old plan."""
    situation_id = "SIT-ACT-001"
    old_plan = create_sample_active_plan(situation_id, "PLAN-V1")
    old_plan["status"] = CoordinationPlanStatus.ACTIVE.value
    await mock_db["coordination_plans"].insert_one(old_plan)

    revised_plan = create_sample_active_plan(situation_id, "PLAN-V2")
    revised_plan["status"] = CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value
    revised_plan["version"] = 2
    revised_plan["previous_plan_id"] = "PLAN-V1"
    revised_plan["generated_at"] = datetime.now(timezone.utc).isoformat()
    await mock_db["coordination_plans"].insert_one(revised_plan)

    await mock_db["situations"].insert_one({
        "_id": situation_id,
        "situation_id": situation_id,
        "computed_severity_level": "CRITICAL",
    })

    actor = {
        "id": "OFF-999",
        "full_name": "Officer Jane Smith",
        "role": "EMERGENCY_OFFICER",
    }

    response = await PlanActivationService.approve_and_activate_plan(
        plan_id="PLAN-V2",
        officer_actor=actor,
        officer_notes="Approved detour due to waterlogging at Sector 4 underpass.",
        db=mock_db,
    )

    assert response.status == CoordinationPlanStatus.ACTIVE.value
    assert response.plan_id == "PLAN-V2"
    assert response.previous_plan_id == "PLAN-V1"
    assert response.version == 2

    # Check database state
    db_v2 = await mock_db["coordination_plans"].find_one({"plan_id": "PLAN-V2"})
    assert db_v2["status"] == CoordinationPlanStatus.ACTIVE.value
    assert db_v2["officer_review"]["decision"] == "APPROVE"
    assert db_v2["officer_review"]["reviewed_by_id"] == "OFF-999"

    db_v1 = await mock_db["coordination_plans"].find_one({"plan_id": "PLAN-V1"})
    assert db_v1["status"] == CoordinationPlanStatus.SUPERSEDED.value

    # Verify audit logs was updated
    audit_logs = await mock_db["audit_logs"].find({}).to_list()
    assert len(audit_logs) >= 1
    approval_event = next((e for e in audit_logs if e.get("action") == TimelineEventType.PLAN_ACTIVATED.value), None)
    assert approval_event is not None


@pytest.mark.asyncio
async def test_stale_plan_detection_blocks_approval(mock_db):
    """Test that stale plan protection triggers when critical events occur after plan generation."""
    situation_id = "SIT-STALE-001"
    old_plan = create_sample_active_plan(situation_id, "PLAN-OLD-01")
    await mock_db["coordination_plans"].insert_one(old_plan)

    # Generated 10 minutes ago
    gen_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    revised_plan = create_sample_active_plan(situation_id, "PLAN-REV-02")
    revised_plan["status"] = CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value
    revised_plan["version"] = 2
    revised_plan["previous_plan_id"] = "PLAN-OLD-01"
    revised_plan["generated_at"] = gen_time.isoformat()
    await mock_db["coordination_plans"].insert_one(revised_plan)

    await mock_db["situations"].insert_one({
        "_id": situation_id,
        "situation_id": situation_id,
        "computed_severity_level": "CRITICAL",
    })

    # A newer CRITICAL event occurred 2 minutes ago
    newer_event = MonitoringEvent(
        event_id="EVT-NEWER-001",
        event_type=MonitoringEventType.SITUATION_SEVERITY_CHANGED,
        source_type=EventSourceType.SITUATION_INTELLIGENCE,
        source_id=situation_id,
        severity=SeverityLevel.CRITICAL,
        situation_id=situation_id,
        coordination_plan_id="PLAN-OLD-01",
        impact_level=ImpactLevel.CRITICAL,
        event_fingerprint="fp-newer-001",
        detected_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        previous_state={"severity": "MEDIUM"},
        new_state={"severity": "CRITICAL"},
        changed_fields=["severity"],
    )
    newer_event_doc = newer_event.model_dump()
    newer_event_doc["detected_at"] = newer_event_doc["detected_at"].isoformat()
    await mock_db["monitoring_events"].insert_one(newer_event_doc)

    revised_plan_obj = CoordinationPlan(**revised_plan)

    # Verify stale detection
    is_stale, reason = await PlanActivationService.is_plan_stale(revised_plan_obj, db=mock_db)
    assert is_stale is True
    assert "New critical event" in reason or "detected after plan generation" in reason

    actor = {
        "id": "OFF-1",
        "full_name": "Officer Jane",
        "role": "EMERGENCY_OFFICER",
    }

    # Attempting to approve should raise ValueError / block
    with pytest.raises(ValueError) as excinfo:
        await PlanActivationService.approve_and_activate_plan(
            plan_id="PLAN-REV-02",
            officer_actor=actor,
            officer_notes="Attempting approval",
            db=mock_db,
        )

    assert "STALE_PLAN_DETECTED" in str(excinfo.value)


@pytest.mark.asyncio
async def test_officer_modify_and_reject_workflows(mock_db):
    """Test HITL modifications and explicit rejection workflows."""
    situation_id = "SIT-HITL-001"
    revised_plan = create_sample_active_plan(situation_id, "PLAN-REV-HITL")
    revised_plan["status"] = CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value
    revised_plan["version"] = 2
    await mock_db["coordination_plans"].insert_one(revised_plan)

    actor = {
        "id": "OFF-1",
        "full_name": "Officer Jane",
        "role": "EMERGENCY_OFFICER",
    }

    # Test Modification
    mod_req = PlanModifyRequest(
        notes="Reduced allocated shelter capacity by 10 for safety buffer",
        modified_shelters=[
            {
                "shelter_id": "SHELTER-001",
                "shelter_name": "Community Center A",
                "distance_km": 2.5,
                "total_capacity": 100.0,
                "current_occupancy": 10.0,
                "remaining_capacity": 90.0,
                "recommended_occupancy": 40.0,  # modified from 50
                "coverage_percentage": 100.0,
                "suitability_score": 95.0,
                "recommendation_reason": "Adjusted for safety buffer.",
            }
        ]
    )

    updated_plan = await PlanActivationService.modify_revised_plan(
        plan_id="PLAN-REV-HITL",
        modify_req=mod_req,
        officer_actor=actor,
        db=mock_db,
    )

    assert updated_plan.status == CoordinationPlanStatus.MODIFIED
    assert updated_plan.recommended_shelters[0].recommended_occupancy == 40.0
    assert updated_plan.officer_review.decision == PlanReviewAction.MODIFY

    # Test Rejection
    rej_req = PlanRejectRequest(
        rejection_reason="Road condition report outdated; field team confirmed underpass is clear.",
        officer_notes="Retaining active baseline.",
    )

    rejected_plan = await PlanActivationService.reject_revised_plan(
        plan_id="PLAN-REV-HITL",
        reject_req=rej_req,
        officer_actor=actor,
        db=mock_db,
    )

    assert rejected_plan.status == CoordinationPlanStatus.REJECTED
    assert rejected_plan.officer_review.decision == PlanReviewAction.REJECT

    # Check DB state
    db_plan = await mock_db["coordination_plans"].find_one({"plan_id": "PLAN-REV-HITL"})
    assert db_plan["status"] == CoordinationPlanStatus.REJECTED.value
