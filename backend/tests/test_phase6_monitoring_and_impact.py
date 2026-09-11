import pytest
import mongomock
from datetime import datetime
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
    UserRole,
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
from app.services.monitoring.impact_analyzer import ChangeImpactAnalyzer, TOPOLOGICAL_AGENT_ORDER
from app.services.monitoring.monitoring_service import (
    MonitoringService,
    compute_event_fingerprint,
)


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

    async def count_documents(self, filter_q, *args, **kwargs):
        return self._col.count_documents(filter_q, *args, **kwargs)

    def aggregate(self, pipeline, *args, **kwargs):
        cursor = self._col.aggregate(pipeline, *args, **kwargs)
        return AsyncMongoMockCursor(cursor)


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


class AsyncMongoMockDatabase:
    def __init__(self):
        self._client = mongomock.MongoClient()
        self._db = self._client["resilience_ai_test"]

    def __getitem__(self, name):
        return AsyncMongoMockCollection(self._db[name])


@pytest.fixture
def mock_db():
    return AsyncMongoMockDatabase()


# =========================================================================
# TEST SUITE 1: EVENT CREATION, NORMALIZATION & DEDUPLICATION
# =========================================================================

@pytest.mark.asyncio
async def test_event_creation_and_normalization_resource(mock_db):
    """
    Test 1: Real resource quantity reduction (120 -> 70) creates normalized MonitoringEvent.
    """
    event = await MonitoringService.record_change_event(
        event_type=MonitoringEventType.RESOURCE_QUANTITY_CHANGED,
        source_type=EventSourceType.RESOURCE_INVENTORY,
        source_id="RES-WATER-001",
        previous_state={"resource_type": "Water", "quantity_available": 120.0, "status": "AVAILABLE"},
        new_state={"resource_type": "Water", "quantity_available": 70.0, "status": "AVAILABLE"},
        actor={"id": "OFF-1", "full_name": "Duty Officer", "role": "RESOURCE_MANAGER"},
        db=mock_db,
    )

    assert event is not None
    assert event.event_id.startswith("EVT-")
    assert event.source_type == EventSourceType.RESOURCE_INVENTORY
    assert event.source_id == "RES-WATER-001"
    assert "quantity_available" in event.changed_fields
    assert event.previous_state["quantity_available"] == 120.0
    assert event.new_state["quantity_available"] == 70.0

    # Verify document stored in database
    doc = await mock_db["monitoring_events"].find_one({"event_id": event.event_id})
    assert doc is not None
    assert doc["source_id"] == "RES-WATER-001"


@pytest.mark.asyncio
async def test_zero_change_creates_no_event(mock_db):
    """
    Test 2: Zero-change invariant (100 -> 100) does NOT produce a false-positive event.
    """
    event = await MonitoringService.record_change_event(
        event_type=MonitoringEventType.RESOURCE_QUANTITY_CHANGED,
        source_type=EventSourceType.RESOURCE_INVENTORY,
        source_id="RES-WATER-001",
        previous_state={"quantity_available": 100.0, "status": "AVAILABLE"},
        new_state={"quantity_available": 100.0, "status": "AVAILABLE"},
        db=mock_db,
    )

    assert event is None
    count = await mock_db["monitoring_events"].count_documents({})
    assert count == 0


@pytest.mark.asyncio
async def test_event_deduplication(mock_db):
    """
    Test 3: Identical event dispatched multiple times is deduplicated within the time window.
    """
    event1 = await MonitoringService.record_change_event(
        event_type=MonitoringEventType.RESOURCE_QUANTITY_CHANGED,
        source_type=EventSourceType.RESOURCE_INVENTORY,
        source_id="RES-WATER-001",
        previous_state={"quantity_available": 120.0},
        new_state={"quantity_available": 70.0},
        db=mock_db,
    )

    event2 = await MonitoringService.record_change_event(
        event_type=MonitoringEventType.RESOURCE_QUANTITY_CHANGED,
        source_type=EventSourceType.RESOURCE_INVENTORY,
        source_id="RES-WATER-001",
        previous_state={"quantity_available": 120.0},
        new_state={"quantity_available": 70.0},
        db=mock_db,
    )

    assert event1 is not None
    assert event2 is not None
    assert event1.event_id == event2.event_id
    count = await mock_db["monitoring_events"].count_documents({})
    assert count == 1


# =========================================================================
# TEST SUITE 2: CHANGE IMPACT ANALYSIS ACROSS ALL DOMAINS
# =========================================================================

@pytest.mark.asyncio
async def test_resource_shortfall_impact_analysis(mock_db):
    """
    Test 4: Resource reduction below active plan requirement invalidates plan and flags Resource + Conflict agents.
    Plan requires 100 Litres Water. Inventory drops from 120 to 70.
    Shortfall = 30 Litres. Impact = HIGH / CRITICAL.
    """
    active_plan = CoordinationPlan(
        plan_id="PLAN-2026-001",
        situation_id="SIT-001",
        assessed_priority=SeverityLevel.HIGH,
        recommended_allocations=[
            PlanRecommendedResource(
                resource_type=ResourceType.WATER,
                quantity_required=100.0,
                allocated_quantity=100.0,
                unit="Litres",
                urgency=NeedUrgency.HIGH,
                matched_resource_id="RES-WATER-001",
                matched_resource_name="Regional Depot Alpha Water",
            )
        ],
        reasoning="Baseline plan",
    )

    event = MonitoringEvent(
        event_id="EVT-TEST-001",
        event_type=MonitoringEventType.RESOURCE_QUANTITY_CHANGED,
        source_type=EventSourceType.RESOURCE_INVENTORY,
        source_id="RES-WATER-001",
        situation_id="SIT-001",
        coordination_plan_id="PLAN-2026-001",
        previous_state={"name": "Regional Depot Alpha Water", "resource_type": "Water", "quantity_available": 120.0},
        new_state={"name": "Regional Depot Alpha Water", "resource_type": "Water", "quantity_available": 70.0},
        changed_fields=["quantity_available"],
        event_fingerprint="fp1",
    )

    impact = await ChangeImpactAnalyzer.analyze_impact(
        event=event,
        active_plan=active_plan,
        db=mock_db,
    )

    assert impact.impact_level in [ImpactLevel.HIGH, ImpactLevel.CRITICAL]
    assert impact.plan_status == PlanValidityStatus.INVALIDATED
    assert impact.officer_attention_required is True
    assert OperationalDomain.RESOURCE in impact.affected_domains
    assert AgentName.RESOURCE_COORDINATION_AGENT in impact.affected_agents
    assert AgentName.CONFLICT_RESOLUTION_AGENT in impact.affected_agents
    # Verify exact mathematical shortfall calculation (100 - 70 = 30)
    assert impact.shortfalls.get("Regional Depot Alpha Water_Water") == 30.0
    assert len(impact.violated_constraints) > 0


@pytest.mark.asyncio
async def test_shelter_capacity_breach_impact_analysis(mock_db):
    """
    Test 5: Shelter occupancy increase breaches remaining capacity needed by active plan.
    Plan requires 250 beds. Total capacity = 300. Occupancy increases 0 -> 180 (Remaining = 120).
    Shortfall = 250 - 120 = 130. Plan is INVALIDATED.
    """
    active_plan = CoordinationPlan(
        plan_id="PLAN-2026-002",
        situation_id="SIT-002",
        assessed_priority=SeverityLevel.HIGH,
        recommended_shelters=[
            RecommendedShelter(
                shelter_id="SHL-CENTRAL-01",
                shelter_name="Central High School Shelter",
                distance_km=2.5,
                total_capacity=300.0,
                current_occupancy=0.0,
                remaining_capacity=300.0,
                recommended_occupancy=250.0,
                coverage_percentage=100.0,
                suitability_score=95.0,
                status="AVAILABLE",
                recommendation_reason="Primary regional shelter",
            )
        ],
        reasoning="Shelter plan",
    )

    event = MonitoringEvent(
        event_id="EVT-SHL-001",
        event_type=MonitoringEventType.SHELTER_OCCUPANCY_CHANGED,
        source_type=EventSourceType.SHELTER_FACILITY,
        source_id="SHL-CENTRAL-01",
        situation_id="SIT-002",
        coordination_plan_id="PLAN-2026-002",
        previous_state={"name": "Central High School Shelter", "quantity_total": 300.0, "current_occupancy": 0.0, "status": "AVAILABLE"},
        new_state={"name": "Central High School Shelter", "quantity_total": 300.0, "current_occupancy": 180.0, "status": "AVAILABLE"},
        changed_fields=["current_occupancy"],
        event_fingerprint="fp2",
    )

    impact = await ChangeImpactAnalyzer.analyze_impact(
        event=event,
        active_plan=active_plan,
        db=mock_db,
    )

    assert impact.impact_level in [ImpactLevel.CRITICAL, ImpactLevel.HIGH]
    assert impact.plan_status == PlanValidityStatus.INVALIDATED
    assert impact.officer_attention_required is True
    assert OperationalDomain.SHELTER in impact.affected_domains
    assert AgentName.SHELTER_AGENT in impact.affected_agents
    assert AgentName.CONFLICT_RESOLUTION_AGENT in impact.affected_agents
    assert impact.shortfalls.get("Central High School Shelter_shelter_capacity") == 130.0


@pytest.mark.asyncio
async def test_healthcare_facility_bed_reduction_impact(mock_db):
    """
    Test 6: Healthcare facility loses bed capacity below allocated casualties.
    Plan allocates 20 casualties to City General Hospital. Available beds drop from 25 to 12.
    Shortfall = 8 beds. Flags HealthcareAgent + ConflictResolutionAgent.
    """
    active_plan = CoordinationPlan(
        plan_id="PLAN-2026-003",
        situation_id="SIT-003",
        assessed_priority=SeverityLevel.HIGH,
        recommended_facilities=[
            RecommendedHealthcareFacility(
                facility_id="HOSP-GENERAL-01",
                facility_name="City General Hospital",
                distance_km=3.0,
                total_beds=50.0,
                available_beds=25.0,
                allocated_patients=20.0,
                coverage_percentage=100.0,
                status="AVAILABLE",
                recommendation_reason="Primary trauma center",
            )
        ],
        reasoning="Medical plan",
    )

    event = MonitoringEvent(
        event_id="EVT-HOSP-001",
        event_type=MonitoringEventType.HEALTHCARE_CAPACITY_CHANGED,
        source_type=EventSourceType.HEALTHCARE_FACILITY,
        source_id="HOSP-GENERAL-01",
        situation_id="SIT-003",
        coordination_plan_id="PLAN-2026-003",
        previous_state={"facility_name": "City General Hospital", "available_beds": 25.0, "facility_status": "OPERATIONAL"},
        new_state={"facility_name": "City General Hospital", "available_beds": 12.0, "facility_status": "OPERATIONAL"},
        changed_fields=["available_beds"],
        event_fingerprint="fp3",
    )

    impact = await ChangeImpactAnalyzer.analyze_impact(
        event=event,
        active_plan=active_plan,
        db=mock_db,
    )

    assert impact.impact_level == ImpactLevel.HIGH
    assert impact.plan_status == PlanValidityStatus.INVALIDATED
    assert impact.officer_attention_required is True
    assert OperationalDomain.HEALTHCARE in impact.affected_domains
    assert AgentName.HEALTHCARE_AGENT in impact.affected_agents
    assert AgentName.CONFLICT_RESOLUTION_AGENT in impact.affected_agents
    assert impact.shortfalls.get("City General Hospital_medical_beds") == 8.0


@pytest.mark.asyncio
async def test_volunteer_unavailability_impact(mock_db):
    """
    Test 7: Assigned volunteer becomes UNAVAILABLE.
    Plan assigns volunteer VOL-01. Volunteer status transitions to Currently Unavailable.
    Flags VolunteerAgent + ConflictResolutionAgent.
    """
    active_plan = CoordinationPlan(
        plan_id="PLAN-2026-004",
        situation_id="SIT-004",
        assessed_priority=SeverityLevel.MEDIUM,
        recommended_volunteers=[
            RecommendedVolunteerAssignment(
                volunteer_id="VOL-001",
                volunteer_name="Dr. Jane Smith",
                role_or_skill="First Aid & CPR",
                assigned_operation="Triage Support",
                recommendation_reason="Qualified medic",
            )
        ],
        reasoning="Volunteer assignment",
    )

    event = MonitoringEvent(
        event_id="EVT-VOL-001",
        event_type=MonitoringEventType.VOLUNTEER_AVAILABILITY_CHANGED,
        source_type=EventSourceType.VOLUNTEER_NETWORK,
        source_id="VOL-001",
        situation_id="SIT-004",
        coordination_plan_id="PLAN-2026-004",
        previous_state={"full_name": "Dr. Jane Smith", "availability": "Available Immediately", "status": "ACTIVE"},
        new_state={"full_name": "Dr. Jane Smith", "availability": "Currently Unavailable", "status": "ACTIVE"},
        changed_fields=["availability"],
        event_fingerprint="fp4",
    )

    impact = await ChangeImpactAnalyzer.analyze_impact(
        event=event,
        active_plan=active_plan,
        db=mock_db,
    )

    assert impact.impact_level == ImpactLevel.HIGH
    assert OperationalDomain.VOLUNTEER in impact.affected_domains
    assert AgentName.VOLUNTEER_AGENT in impact.affected_agents
    assert AgentName.CONFLICT_RESOLUTION_AGENT in impact.affected_agents
    assert impact.shortfalls.get("Dr. Jane Smith_personnel") == 1.0


@pytest.mark.asyncio
async def test_transport_and_route_blockage_impact(mock_db):
    """
    Test 8: Transport asset becomes UNAVAILABLE / route is BLOCKED.
    Plan assigns Ambulance AMB-01 on Route RT-01. Route is reported BLOCKED.
    Plan is INVALIDATED. Flags RouteAgent + ConflictResolutionAgent.
    """
    active_plan = CoordinationPlan(
        plan_id="PLAN-2026-005",
        situation_id="SIT-005",
        assessed_priority=SeverityLevel.HIGH,
        recommended_transports=[
            RecommendedTransport(
                transport_id="AMB-001",
                vehicle_name="Ambulance Unit 1",
                vehicle_type="Ambulance",
                capacity=2.0,
                allocated_load_or_passengers=2.0,
                assigned_mission="Medical Evacuation",
                recommendation_reason="Emergency transport",
            )
        ],
        recommended_routes=[
            RecommendedRoute(
                route_id="RT-001",
                origin_name="Incident Site",
                destination_name="General Hospital",
                origin_coordinates={"latitude": 16.24, "longitude": 80.64},
                destination_coordinates={"latitude": 16.26, "longitude": 80.66},
                distance_km=4.5,
                estimated_duration_minutes=12.0,
                transport_id="AMB-001",
                assigned_mission="Evacuation Route",
                recommendation_reason="Fastest corridor",
            )
        ],
        reasoning="Logistics plan",
    )

    event = MonitoringEvent(
        event_id="EVT-ROUTE-001",
        event_type=MonitoringEventType.ROUTE_OBSTRUCTION_CHANGED,
        source_type=EventSourceType.ROUTE_NETWORK,
        source_id="RT-001",
        situation_id="SIT-005",
        coordination_plan_id="PLAN-2026-005",
        previous_state={"route_id": "RT-001", "road_condition_status": "PASSABLE"},
        new_state={"route_id": "RT-001", "road_condition_status": "BLOCKED"},
        changed_fields=["road_condition_status"],
        event_fingerprint="fp5",
    )

    impact = await ChangeImpactAnalyzer.analyze_impact(
        event=event,
        active_plan=active_plan,
        db=mock_db,
    )

    assert impact.impact_level == ImpactLevel.CRITICAL
    assert impact.plan_status == PlanValidityStatus.INVALIDATED
    assert impact.officer_attention_required is True
    assert OperationalDomain.ROUTE in impact.affected_domains
    assert AgentName.ROUTE_AGENT in impact.affected_agents
    assert AgentName.CONFLICT_RESOLUTION_AGENT in impact.affected_agents


@pytest.mark.asyncio
async def test_situation_severity_escalation_cascades(mock_db):
    """
    Test 9: Situation severity escalates LOW -> CRITICAL without officer override.
    Cascades across the entire downstream agent pipeline and sets REQUIRES_OFFICER_REVIEW.
    """
    event = MonitoringEvent(
        event_id="EVT-SIT-001",
        event_type=MonitoringEventType.SITUATION_SEVERITY_CHANGED,
        source_type=EventSourceType.SITUATION_INTELLIGENCE,
        source_id="SIT-006",
        situation_id="SIT-006",
        previous_state={"situation_id": "SIT-006", "severity_level": "LOW"},
        new_state={"situation_id": "SIT-006", "severity_level": "CRITICAL"},
        changed_fields=["severity_level"],
        event_fingerprint="fp6",
    )

    impact = await ChangeImpactAnalyzer.analyze_impact(
        event=event,
        db=mock_db,
    )

    assert impact.impact_level == ImpactLevel.HIGH
    assert impact.plan_status == PlanValidityStatus.REQUIRES_OFFICER_REVIEW
    assert impact.officer_attention_required is True
    assert set(impact.affected_agents) == set(TOPOLOGICAL_AGENT_ORDER)


@pytest.mark.asyncio
async def test_situation_officer_override_preservation(mock_db):
    """
    Test 10: Situation with an explicit Emergency Officer severity override preserves officer authority.
    """
    event = MonitoringEvent(
        event_id="EVT-SIT-002",
        event_type=MonitoringEventType.OFFICER_SEVERITY_OVERRIDDEN,
        source_type=EventSourceType.SITUATION_INTELLIGENCE,
        source_id="SIT-007",
        situation_id="SIT-007",
        previous_state={"situation_id": "SIT-007", "officer_override_severity": "HIGH"},
        new_state={"situation_id": "SIT-007", "officer_override_severity": "HIGH"},
        changed_fields=[],
        event_fingerprint="fp7",
    )

    impact = await ChangeImpactAnalyzer.analyze_impact(
        event=event,
        db=mock_db,
    )

    assert "Officer override remains authoritative" in impact.explanation
    assert impact.plan_status == PlanValidityStatus.POTENTIALLY_AFFECTED


@pytest.mark.asyncio
async def test_dependency_propagation_isolation(mock_db):
    """
    Test 11: Dependency propagation isolation: A change in Shelter capacity does NOT mark
    unrelated domains (Volunteer, Resource, Transport) as affected.
    """
    active_plan = CoordinationPlan(
        plan_id="PLAN-2026-008",
        situation_id="SIT-008",
        assessed_priority=SeverityLevel.HIGH,
        recommended_shelters=[
            RecommendedShelter(
                shelter_id="SHL-001",
                shelter_name="School Hall",
                distance_km=1.0,
                total_capacity=100.0,
                current_occupancy=0.0,
                remaining_capacity=100.0,
                recommended_occupancy=50.0,
                coverage_percentage=100.0,
                suitability_score=90.0,
                status="AVAILABLE",
                recommendation_reason="Shelter match",
            )
        ],
        reasoning="Isolation test",
    )

    event = MonitoringEvent(
        event_id="EVT-SHL-002",
        event_type=MonitoringEventType.SHELTER_CAPACITY_CHANGED,
        source_type=EventSourceType.SHELTER_FACILITY,
        source_id="SHL-001",
        situation_id="SIT-008",
        coordination_plan_id="PLAN-2026-008",
        previous_state={"name": "School Hall", "quantity_total": 100.0, "current_occupancy": 0.0},
        new_state={"name": "School Hall", "quantity_total": 100.0, "current_occupancy": 80.0},
        changed_fields=["current_occupancy"],
        event_fingerprint="fp8",
    )

    impact = await ChangeImpactAnalyzer.analyze_impact(
        event=event,
        active_plan=active_plan,
        db=mock_db,
    )

    # Only Shelter and Conflict agents should be in the affected set
    assert set(impact.affected_agents) == {AgentName.SHELTER_AGENT, AgentName.CONFLICT_RESOLUTION_AGENT}
    assert AgentName.VOLUNTEER_AGENT not in impact.affected_agents
    assert AgentName.RESOURCE_COORDINATION_AGENT not in impact.affected_agents
    assert AgentName.ROUTE_AGENT not in impact.affected_agents


@pytest.mark.asyncio
async def test_officer_event_acknowledgement(mock_db):
    """
    Test 12: Officer acknowledges an operational alert, updating its status to ACKNOWLEDGED
    and writing an immutable audit timeline record.
    """
    event = await MonitoringService.record_change_event(
        event_type=MonitoringEventType.RESOURCE_QUANTITY_CHANGED,
        source_type=EventSourceType.RESOURCE_INVENTORY,
        source_id="RES-FOOD-001",
        previous_state={"quantity_available": 500.0},
        new_state={"quantity_available": 200.0},
        db=mock_db,
    )
    assert event is not None

    ack_res = await MonitoringService.acknowledge_event(
        event_id=event.event_id,
        actor={"id": "OFF-DUTY-1", "full_name": "Capt. Miller", "role": "EMERGENCY_OFFICER"},
        notes="Noted food reduction; preparing mutual aid request.",
        db=mock_db,
    )

    assert ack_res.success is True
    assert ack_res.status == EventStatus.ACKNOWLEDGED
    assert ack_res.acknowledged_by_name == "Capt. Miller"

    # Verify event updated in database
    doc = await mock_db["monitoring_events"].find_one({"event_id": event.event_id})
    assert doc["status"] == EventStatus.ACKNOWLEDGED.value
    assert doc["metadata"]["acknowledged_by_name"] == "Capt. Miller"


@pytest.mark.asyncio
async def test_zero_mutation_safety_and_advisory_nature(mock_db):
    """
    Test 13: Zero mutation invariant: Monitoring and impact analysis remain 100% advisory
    and read-only. They do NOT mutate resource inventories, occupy shelters, or create plans.
    """
    initial_resource = {"resource_id": "RES-001", "quantity_available": 100.0, "status": "AVAILABLE"}
    await mock_db["resources"].insert_one(initial_resource)

    # Run monitoring on a change
    await MonitoringService.record_change_event(
        event_type=MonitoringEventType.RESOURCE_QUANTITY_CHANGED,
        source_type=EventSourceType.RESOURCE_INVENTORY,
        source_id="RES-001",
        previous_state={"quantity_available": 100.0},
        new_state={"quantity_available": 40.0},
        db=mock_db,
    )

    # Database resource document remains exactly as recorded (not auto-mutated by monitoring)
    res_doc = await mock_db["resources"].find_one({"resource_id": "RES-001"})
    assert res_doc["quantity_available"] == 100.0

    # No automatic response plans created
    plan_count = await mock_db["coordination_plans"].count_documents({})
    assert plan_count == 0
