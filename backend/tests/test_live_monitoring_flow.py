import pytest
import mongomock
from datetime import datetime, timezone, timedelta

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
)
from app.models.monitoring import (
    MonitoringEvent,
    ChangeImpactResult,
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
from app.services.monitoring.monitoring_service import (
    MonitoringService,
    compute_event_fingerprint,
)
from app.services.monitoring.plan_activation_service import PlanActivationService


class AsyncMongoMockCursor:
    def __init__(self, sync_cursor):
        self._cursor = sync_cursor

    def sort(self, *args, **kwargs):
        self._cursor = self._cursor.sort(*args, **kwargs)
        return self

    def skip(self, count):
        self._cursor = self._cursor.skip(count)
        return self

    def limit(self, count):
        self._cursor = self._cursor.limit(count)
        return self

    async def to_list(self, length=None):
        return list(self._cursor)

    def __aiter__(self):
        self._iter = iter(self._cursor)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


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
        cursor = self._col.aggregate(pipeline, *args, **kwargs)
        return AsyncMongoMockCursor(cursor)


class AsyncMongoMockDatabase:
    def __init__(self):
        self._client = mongomock.MongoClient()
        self._db = self._client["resilience_test_live_monitoring"]

    def __getitem__(self, name):
        return AsyncMongoMockCollection(self._db[name])


@pytest.fixture
def mock_db():
    return AsyncMongoMockDatabase()


@pytest.mark.asyncio
async def test_record_live_operational_event(mock_db):
    """Test recording a real live event without simulation flag."""
    actor = {"id": "USR-123", "full_name": "Citizen User", "role": "CITIZEN"}
    event = await MonitoringService.record_change_event(
        event_type=MonitoringEventType.REPORT_CREATED,
        source_type=EventSourceType.CITIZEN_REPORT,
        source_id="rep-12345",
        previous_state={},
        new_state={"emergency_type": "FLOOD", "severity": "HIGH", "report_id": "rep-12345"},
        actor=actor,
        metadata={"is_simulation": False},
        db=mock_db,
    )

    assert event is not None
    assert event.event_type == MonitoringEventType.REPORT_CREATED
    assert event.source_id == "rep-12345"
    assert event.is_simulation is False

    # Verify event stored in DB
    stored = await mock_db["monitoring_events"].find_one({"event_id": event.event_id})
    assert stored is not None
    assert stored["event_type"] == "REPORT_CREATED"
    assert stored["is_simulation"] is False


@pytest.mark.asyncio
async def test_stats_filters_simulation_by_default(mock_db):
    """Test that live stats ignore simulations by default."""
    actor = {"id": "OFF-1", "full_name": "Officer Smith", "role": "EMERGENCY_OFFICER"}

    # Insert 2 live events
    await MonitoringService.record_change_event(
        event_type=MonitoringEventType.REPORT_CREATED,
        source_type=EventSourceType.CITIZEN_REPORT,
        source_id="rep-1",
        previous_state={},
        new_state={"report_id": "rep-1"},
        actor=actor,
        metadata={"is_simulation": False},
        db=mock_db,
    )
    await MonitoringService.record_change_event(
        event_type=MonitoringEventType.RESOURCE_ALLOCATED,
        source_type=EventSourceType.RESOURCE_INVENTORY,
        source_id="res-1",
        previous_state={"quantity": 100},
        new_state={"quantity": 80},
        actor=actor,
        metadata={"is_simulation": False},
        db=mock_db,
    )

    # Insert 1 simulation event
    await MonitoringService.record_change_event(
        event_type=MonitoringEventType.RESOURCE_RELEASED,
        source_type=EventSourceType.RESOURCE_INVENTORY,
        source_id="sim-res-1",
        previous_state={"quantity": 50},
        new_state={"quantity": 0},
        actor=actor,
        metadata={"is_simulation": True},
        db=mock_db,
    )

    stats = await MonitoringService.get_monitoring_stats(db=mock_db)
    assert stats.total_events == 2
    assert stats.domain_breakdown.get("RESOURCE_INVENTORY") == 1
    assert stats.domain_breakdown.get("CITIZEN_REPORT") == 1


@pytest.mark.asyncio
async def test_plan_activation_dispatches_events(mock_db):
    """Test that activating a coordination plan records PLAN_ACTIVATED and marks plan active."""
    # Seed a situation with uppercase ID
    await mock_db["situations"].insert_one({
        "_id": "SIT-LIVE-01",
        "situation_id": "SIT-LIVE-01",
        "title": "Downtown Flood",
        "computed_severity_level": "HIGH",
        "status": "ACTIVE",
    })

    # Seed an APPROVED / PENDING_OFFICER_REVIEW coordination plan
    plan_doc = {
        "plan_id": "PLAN-LIVE-01",
        "situation_id": "SIT-LIVE-01",
        "version": 1,
        "is_active": False,
        "status": CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
        "assessed_priority": SeverityLevel.HIGH.value,
        "reasoning": "Standard emergency deployment for urban flooding",
        "executive_summary": "Initial live deployment plan",
        "resource_allocations": [],
        "shelter_allocations": [],
        "healthcare_recommendations": [],
        "volunteer_assignments": [],
        "route_recommendations": [],
        "transport_plans": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await mock_db["coordination_plans"].insert_one(plan_doc)

    actor = {"id": "OFF-1", "full_name": "Officer Jane", "role": "EMERGENCY_OFFICER"}
    active_plan = await PlanActivationService.approve_and_activate_plan(
        plan_id="PLAN-LIVE-01",
        officer_actor=actor,
        officer_notes="Approved for field deployment",
        db=mock_db,
    )

    assert active_plan is not None
    assert active_plan.status == CoordinationPlanStatus.ACTIVE.value
    assert active_plan.version == 1

    # Check monitoring event generated
    events = await mock_db["monitoring_events"].find({"source_id": "PLAN-LIVE-01"}).to_list(10)
    assert len(events) >= 1
    activated_event = next((e for e in events if e["event_type"] == "PLAN_ACTIVATED"), None)
    assert activated_event is not None
    assert activated_event["source_id"] == "PLAN-LIVE-01"


@pytest.mark.asyncio
async def test_plan_superseded_when_new_version_activated(mock_db):
    """Test that activating version 2 supersedes version 1 and logs PLAN_SUPERSEDED."""
    await mock_db["situations"].insert_one({
        "_id": "SIT-LIVE-02",
        "situation_id": "SIT-LIVE-02",
        "title": "Industrial Fire",
        "computed_severity_level": "CRITICAL",
        "status": "ACTIVE",
    })

    # Plan V1 (currently ACTIVE)
    await mock_db["coordination_plans"].insert_one({
        "plan_id": "PLAN-V1",
        "situation_id": "SIT-LIVE-02",
        "version": 1,
        "is_active": True,
        "status": CoordinationPlanStatus.ACTIVE.value,
        "assessed_priority": SeverityLevel.HIGH.value,
        "reasoning": "V1 fire containment plan",
        "resource_allocations": [],
        "shelter_allocations": [],
        "healthcare_recommendations": [],
        "volunteer_assignments": [],
        "route_recommendations": [],
        "transport_plans": [],
        "generated_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    # Plan V2 (PENDING_OFFICER_REVIEW)
    await mock_db["coordination_plans"].insert_one({
        "plan_id": "PLAN-V2",
        "situation_id": "SIT-LIVE-02",
        "version": 2,
        "previous_plan_id": "PLAN-V1",
        "previous_version": 1,
        "is_active": False,
        "status": CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
        "assessed_priority": SeverityLevel.CRITICAL.value,
        "reasoning": "V2 revised evacuation and response plan",
        "resource_allocations": [],
        "shelter_allocations": [],
        "healthcare_recommendations": [],
        "volunteer_assignments": [],
        "route_recommendations": [],
        "transport_plans": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    actor = {"id": "OFF-1", "full_name": "Officer Jane", "role": "EMERGENCY_OFFICER"}
    
    # Activate V2
    activated_v2 = await PlanActivationService.approve_and_activate_plan(
        plan_id="PLAN-V2",
        officer_actor=actor,
        officer_notes="Switching to revised route plan",
        db=mock_db,
    )

    assert activated_v2.status == CoordinationPlanStatus.ACTIVE.value

    # Verify V1 is superseded in DB
    v1_doc = await mock_db["coordination_plans"].find_one({"plan_id": "PLAN-V1"})
    assert v1_doc["status"] == CoordinationPlanStatus.SUPERSEDED.value

    # Verify PLAN_SUPERSEDED event logged
    events = await mock_db["monitoring_events"].find({"source_id": "PLAN-V1"}).to_list(10)
    event_types = [e["event_type"] for e in events]
    assert "PLAN_SUPERSEDED" in event_types
