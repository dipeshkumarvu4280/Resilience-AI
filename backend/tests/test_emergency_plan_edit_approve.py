import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.models.enums import (
    CoordinationPlanStatus,
    PlanReviewAction,
    ResourceType,
    NeedUrgency,
    SeverityLevel,
    TimelineEventType,
    UserRole,
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
from app.services.agents.orchestrator import CentralOrchestrator


class MockDBHelper:
    """Helper to mock MongoDB collections with in-memory dict storage for fast async testing."""
    def __init__(self):
        self.coordination_plans = {}
        self.resources = {}
        self.shelters = {}
        self.healthcare_facilities = {}
        self.situations = {}
        self.incident_timeline = []
        self.response_tasks = []

    def get_mock_db(self):
        async def plans_find_one(query):
            pid = query.get("plan_id")
            if pid and pid in self.coordination_plans:
                return dict(self.coordination_plans[pid])
            return None

        async def plans_update_one(query, update_doc):
            pid = query.get("plan_id")
            if pid and pid in self.coordination_plans:
                if "$set" in update_doc:
                    self.coordination_plans[pid].update(update_doc["$set"])
                return AsyncMock(matched_count=1)
            return AsyncMock(matched_count=0)

        async def plans_update_many(query, update_doc):
            sit_id = query.get("situation_id")
            count = 0
            for pid, doc in self.coordination_plans.items():
                if doc.get("situation_id") == sit_id and pid != query.get("plan_id", {}).get("$ne"):
                    if "$set" in update_doc:
                        doc.update(update_doc["$set"])
                        count += 1
            return AsyncMock(matched_count=count)

        async def resources_find_one(query):
            for r in self.resources.values():
                if query.get("$or"):
                    for clause in query["$or"]:
                        if clause.get("resource_id") == r.get("resource_id") or clause.get("_id") == r.get("resource_id"):
                            return dict(r)
                elif query.get("resource_id") == r.get("resource_id"):
                    return dict(r)
            return None

        async def shelters_find_one(query):
            for s in self.shelters.values():
                if query.get("$or"):
                    for clause in query["$or"]:
                        if clause.get("shelter_id") == s.get("shelter_id") or clause.get("_id") == s.get("shelter_id"):
                            return dict(s)
                elif query.get("shelter_id") == s.get("shelter_id"):
                    return dict(s)
            return None

        async def healthcare_find_one(query):
            for h in self.healthcare_facilities.values():
                if query.get("$or"):
                    for clause in query["$or"]:
                        if clause.get("facility_id") == h.get("facility_id") or clause.get("_id") == h.get("facility_id"):
                            return dict(h)
                elif query.get("facility_id") == h.get("facility_id"):
                    return dict(h)
            return None

        async def situations_find_one(query):
            sit_id = query.get("situation_id") or query.get("_id")
            return self.situations.get(sit_id)

        async def timeline_insert_one(doc):
            self.incident_timeline.append(doc)
            return AsyncMock()

        async def tasks_insert_one(doc):
            self.response_tasks.append(doc)
            return AsyncMock()

        async def tasks_insert_many(docs):
            self.response_tasks.extend(docs)
            return AsyncMock()

        return {
            "coordination_plans": AsyncMock(
                find_one=AsyncMock(side_effect=plans_find_one),
                update_one=AsyncMock(side_effect=plans_update_one),
                update_many=AsyncMock(side_effect=plans_update_many),
            ),
            "resources": AsyncMock(find_one=AsyncMock(side_effect=resources_find_one)),
            "shelters": AsyncMock(find_one=AsyncMock(side_effect=shelters_find_one)),
            "healthcare_facilities": AsyncMock(find_one=AsyncMock(side_effect=healthcare_find_one)),
            "facilities": AsyncMock(find_one=AsyncMock(side_effect=healthcare_find_one)),
            "situations": AsyncMock(find_one=AsyncMock(side_effect=situations_find_one)),
            "incident_timeline": AsyncMock(insert_one=AsyncMock(side_effect=timeline_insert_one)),
            "timeline_events": AsyncMock(insert_one=AsyncMock(side_effect=timeline_insert_one)),
            "response_tasks": AsyncMock(
                find_one=AsyncMock(return_value=None),
                insert_one=AsyncMock(side_effect=tasks_insert_one),
                insert_many=AsyncMock(side_effect=tasks_insert_many),
            ),
            "monitoring_events": AsyncMock(find_one=AsyncMock(return_value=None)),
            "citizen_reports": AsyncMock(update_one=AsyncMock(return_value=AsyncMock())),
            "audit_logs": AsyncMock(insert_one=AsyncMock()),
        }


@pytest.mark.asyncio
async def test_full_hitl_edit_validate_diff_approve_lifecycle():
    """
    Tests full Emergency Officer HITL workflow:
    1. AI Plan Generated in PENDING_OFFICER_REVIEW.
    2. Authoritative Need is 100 L Water; AI allocated 60 L from Depot A and 40 L from Depot B.
    3. Depot A has 80 L available; Depot B has 50 L available.
    4. Officer edits: Depot A = 70 L, Depot B = 30 L.
    5. Server validates allocation within depot stock.
    6. Verifies Authoritative Need is untouched (remains 100 L).
    7. Verifies Plan Diff correctly tracks both changes.
    8. Approval transitions plan to ACTIVE and records audit event.
    9. Verifies inventory in DB is NOT consumed by editing/approval.
    """
    orchestrator = CentralOrchestrator()
    helper = MockDBHelper()

    # Seed genuine authoritative resources
    helper.resources["DEPOT-A-WTR"] = {
        "resource_id": "DEPOT-A-WTR",
        "name": "Central Water Depot",
        "resource_type": "WATER",
        "quantity_total": 80.0,
        "quantity_available": 80.0,
        "unit": "Liters",
    }
    helper.resources["DEPOT-B-WTR"] = {
        "resource_id": "DEPOT-B-WTR",
        "name": "East Reserve Depot",
        "resource_type": "WATER",
        "quantity_total": 50.0,
        "quantity_available": 50.0,
        "unit": "Liters",
    }

    # Seed genuine situation
    helper.situations["SIT-FLOOD-001"] = {
        "situation_id": "SIT-FLOOD-001",
        "title": "Sector 4 Urban Flood",
        "computed_severity_level": "HIGH",
        "officer_override_severity": "HIGH",
        "state_fingerprint": "fp-flood-001",
    }

    # 1. AI Generated Coordination Plan
    ai_plan_dict = {
        "plan_id": "PLAN-SIT-001",
        "situation_id": "SIT-FLOOD-001",
        "assessed_priority": SeverityLevel.HIGH,
        "assessed_needs": [
            {
                "resource_type": "WATER",
                "requested_quantity": 100.0,
                "unit": "Liters",
                "officer_assessed": True,
                "reasoning": "Authoritative community hydration requirement",
            }
        ],
        "recommended_allocations": [
            {
                "resource_type": ResourceType.WATER,
                "quantity_required": 100.0,
                "allocated_quantity": 60.0,
                "unit": "Liters",
                "matched_resource_id": "DEPOT-A-WTR",
                "matched_resource_name": "Central Water Depot",
                "available_in_inventory": 80.0,
                "urgency": NeedUrgency.HIGH,
            },
            {
                "resource_type": ResourceType.WATER,
                "quantity_required": 100.0,
                "allocated_quantity": 40.0,
                "unit": "Liters",
                "matched_resource_id": "DEPOT-B-WTR",
                "matched_resource_name": "East Reserve Depot",
                "available_in_inventory": 50.0,
                "urgency": NeedUrgency.HIGH,
            },
        ],
        "recommended_shelters": [],
        "recommended_facilities": [],
        "recommended_volunteers": [],
        "recommended_transports": [],
        "recommended_routes": [],
        "conflicts": [],
        "reasoning": "AI multi-depot optimal routing recommendation",
        "status": CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
        "generated_at": datetime.now(timezone.utc),
        "state_fingerprint": "fp-flood-001",
    }
    helper.coordination_plans["PLAN-SIT-001"] = ai_plan_dict
    mock_db = helper.get_mock_db()

    # 2. Officer modifies allocation: Depot A = 70 L, Depot B = 30 L
    officer_actor = {
        "id": "OFFICER-44",
        "full_name": "Commander Sarah Jenkins",
        "role": "EMERGENCY_OFFICER",
    }

    modified_allocs = [
        PlanRecommendedResource(
            resource_type=ResourceType.WATER,
            quantity_required=100.0,
            allocated_quantity=70.0,
            unit="Liters",
            matched_resource_id="DEPOT-A-WTR",
            matched_resource_name="Central Water Depot",
            available_in_inventory=80.0,
            urgency=NeedUrgency.HIGH,
        ),
        PlanRecommendedResource(
            resource_type=ResourceType.WATER,
            quantity_required=100.0,
            allocated_quantity=30.0,
            unit="Liters",
            matched_resource_id="DEPOT-B-WTR",
            matched_resource_name="East Reserve Depot",
            available_in_inventory=50.0,
            urgency=NeedUrgency.HIGH,
        ),
    ]

    # Save modification candidate
    mod_result = await orchestrator.review_coordination_plan(
        plan_id="PLAN-SIT-001",
        action=PlanReviewAction.MODIFY,
        actor=officer_actor,
        notes="Adjusted Depot A allocation to 70L due to closer road clearance.",
        modified_allocations=modified_allocs,
        db=mock_db,
    )

    assert mod_result.status == CoordinationPlanStatus.MODIFIED
    assert mod_result.diff_summary is not None
    assert mod_result.diff_summary["allocations_changed"] == 2
    assert len(mod_result.diff_summary["changes"]) == 2

    # Verify Authoritative Need is untouched
    saved_plan = helper.coordination_plans["PLAN-SIT-001"]
    assert saved_plan["assessed_needs"][0]["requested_quantity"] == 100.0

    # Verify inventory was NOT consumed
    assert helper.resources["DEPOT-A-WTR"]["quantity_available"] == 80.0
    assert helper.resources["DEPOT-B-WTR"]["quantity_available"] == 50.0

    # 3. Explicit Officer Approval of Modified Plan -> ACTIVE
    approved_result = await orchestrator.review_coordination_plan(
        plan_id="PLAN-SIT-001",
        action=PlanReviewAction.APPROVE,
        actor=officer_actor,
        notes="Approved modified operational coordination plan.",
        modified_allocations=modified_allocs,
        db=mock_db,
    )

    assert approved_result.status == CoordinationPlanStatus.ACTIVE
    assert approved_result.officer_review.decision == PlanReviewAction.APPROVE
    assert approved_result.officer_review.reviewed_by_name == "Commander Sarah Jenkins"

    # Verify Timeline Audit Event
    assert len(helper.incident_timeline) > 0


@pytest.mark.asyncio
async def test_server_side_validation_rejects_overallocation():
    """
    Tests that server-side validation strictly prevents allocating more than available stock.
    """
    orchestrator = CentralOrchestrator()
    helper = MockDBHelper()

    helper.resources["DEPOT-LIMITED"] = {
        "resource_id": "DEPOT-LIMITED",
        "name": "Small Depot",
        "resource_type": "WATER",
        "quantity_total": 40.0,
        "quantity_available": 40.0,
        "unit": "Liters",
    }
    helper.situations["SIT-002"] = {
        "situation_id": "SIT-002",
        "state_fingerprint": "fp2",
        "computed_severity_level": "HIGH",
        "officer_override_severity": "HIGH",
    }

    helper.coordination_plans["PLAN-OVERALLOC"] = {
        "plan_id": "PLAN-OVERALLOC",
        "situation_id": "SIT-002",
        "assessed_priority": SeverityLevel.HIGH,
        "assessed_needs": [{"resource_type": "WATER", "requested_quantity": 100.0}],
        "recommended_allocations": [
            {
                "resource_type": ResourceType.WATER,
                "quantity_required": 100.0,
                "allocated_quantity": 40.0,
                "unit": "Liters",
                "matched_resource_id": "DEPOT-LIMITED",
                "available_in_inventory": 40.0,
                "urgency": NeedUrgency.HIGH,
            }
        ],
        "recommended_shelters": [],
        "recommended_facilities": [],
        "recommended_volunteers": [],
        "recommended_transports": [],
        "recommended_routes": [],
        "conflicts": [],
        "reasoning": "Test overallocation",
        "status": CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
        "generated_at": datetime.now(timezone.utc),
        "state_fingerprint": "fp2",
    }
    mock_db = helper.get_mock_db()

    # Officer attempts to allocate 60L from a depot with only 40L
    invalid_alloc = [
        PlanRecommendedResource(
            resource_type=ResourceType.WATER,
            quantity_required=100.0,
            allocated_quantity=60.0,
            unit="Liters",
            matched_resource_id="DEPOT-LIMITED",
            available_in_inventory=40.0,
            urgency=NeedUrgency.HIGH,
        )
    ]

    with pytest.raises(ValueError) as excinfo:
        await orchestrator.review_coordination_plan(
            plan_id="PLAN-OVERALLOC",
            action=PlanReviewAction.MODIFY,
            actor={"id": "OFFICER-1", "full_name": "Test Officer", "role": "EMERGENCY_OFFICER"},
            modified_allocations=invalid_alloc,
            db=mock_db,
        )

    assert "exceeds available stock (40 Liters)" in str(excinfo.value)

    # Verify no partial mutation occurred in DB
    plan_in_db = helper.coordination_plans["PLAN-OVERALLOC"]
    assert plan_in_db["status"] == CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value
    assert plan_in_db["recommended_allocations"][0]["allocated_quantity"] == 40.0


@pytest.mark.asyncio
async def test_shelter_and_healthcare_capacity_validation():
    """
    Tests server-side capacity validation for Shelters and Healthcare facilities.
    """
    orchestrator = CentralOrchestrator()
    helper = MockDBHelper()

    helper.shelters["SHELTER-NORTH"] = {
        "shelter_id": "SHELTER-NORTH",
        "shelter_name": "North High Shelter",
        "capacity": 200,
        "current_occupancy": 150,  # Remaining capacity = 50
    }

    helper.healthcare_facilities["HOSPITAL-CENTRAL"] = {
        "facility_id": "HOSPITAL-CENTRAL",
        "facility_name": "City General Hospital",
        "available_beds": 15,
        "capacity": 100,
    }
    helper.situations["SIT-003"] = {
        "situation_id": "SIT-003",
        "state_fingerprint": "fp3",
        "computed_severity_level": "HIGH",
        "officer_override_severity": "HIGH",
    }

    helper.coordination_plans["PLAN-CAPACITY-TEST"] = {
        "plan_id": "PLAN-CAPACITY-TEST",
        "situation_id": "SIT-003",
        "assessed_priority": SeverityLevel.HIGH,
        "recommended_allocations": [],
        "recommended_shelters": [
            {
                "shelter_id": "SHELTER-NORTH",
                "shelter_name": "North High Shelter",
                "recommended_occupancy": 40,
                "distance_km": 2.0,
                "total_capacity": 200,
                "current_occupancy": 150,
                "remaining_capacity": 50,
                "coverage_percentage": 100.0,
                "suitability_score": 90.0,
                "recommendation_reason": "Close proximity",
            }
        ],
        "recommended_facilities": [
            {
                "facility_id": "HOSPITAL-CENTRAL",
                "facility_name": "City General Hospital",
                "allocated_patients": 10,
                "available_beds": 15,
                "distance_km": 3.0,
                "total_beds": 100,
                "coverage_percentage": 100.0,
                "facility_type": "Hospital",
                "status": "AVAILABLE",
                "recommendation_reason": "Nearest trauma facility",
            }
        ],
        "recommended_volunteers": [],
        "recommended_transports": [],
        "recommended_routes": [],
        "conflicts": [],
        "reasoning": "Capacity test",
        "status": CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
        "generated_at": datetime.now(timezone.utc),
        "state_fingerprint": "fp3",
    }
    mock_db = helper.get_mock_db()

    # 1. Test shelter capacity breach (requested 80 > remaining 50)
    invalid_shelter = [
        RecommendedShelter(
            shelter_id="SHELTER-NORTH",
            shelter_name="North High Shelter",
            recommended_occupancy=80,
            distance_km=2.0,
            total_capacity=200,
            current_occupancy=150,
            remaining_capacity=50,
            coverage_percentage=100.0,
            suitability_score=90.0,
            recommendation_reason="Close proximity",
        )
    ]
    with pytest.raises(ValueError) as exc_sh:
        await orchestrator.review_coordination_plan(
            plan_id="PLAN-CAPACITY-TEST",
            action=PlanReviewAction.MODIFY,
            actor={"id": "OFFICER-1", "full_name": "Officer", "role": "EMERGENCY_OFFICER"},
            modified_shelters=invalid_shelter,
            db=mock_db,
        )
    assert "exceeds remaining capacity (50)" in str(exc_sh.value)

    # 2. Test hospital beds breach (requested 25 > available 15)
    invalid_fac = [
        RecommendedHealthcareFacility(
            facility_id="HOSPITAL-CENTRAL",
            facility_name="City General Hospital",
            allocated_patients=25,
            available_beds=15,
            distance_km=3.0,
            total_beds=100,
            coverage_percentage=100.0,
            facility_type="Hospital",
            recommendation_reason="Nearest trauma facility",
        )
    ]
    with pytest.raises(ValueError) as exc_fac:
        await orchestrator.review_coordination_plan(
            plan_id="PLAN-CAPACITY-TEST",
            action=PlanReviewAction.MODIFY,
            actor={"id": "OFFICER-1", "full_name": "Officer", "role": "EMERGENCY_OFFICER"},
            modified_facilities=invalid_fac,
            db=mock_db,
        )
    assert "exceeds available beds (15)" in str(exc_fac.value)


@pytest.mark.asyncio
async def test_plan_rejection_leaves_plan_inactive():
    """
    Tests that rejecting a plan sets status to REJECTED and does not activate it.
    """
    orchestrator = CentralOrchestrator()
    helper = MockDBHelper()

    helper.situations["SIT-004"] = {
        "situation_id": "SIT-004",
        "state_fingerprint": "fp4",
        "computed_severity_level": "MEDIUM",
        "officer_override_severity": "MEDIUM",
    }
    helper.coordination_plans["PLAN-REJECT-TEST"] = {
        "plan_id": "PLAN-REJECT-TEST",
        "situation_id": "SIT-004",
        "assessed_priority": SeverityLevel.MEDIUM,
        "recommended_allocations": [],
        "recommended_shelters": [],
        "recommended_facilities": [],
        "recommended_volunteers": [],
        "recommended_transports": [],
        "recommended_routes": [],
        "conflicts": [],
        "reasoning": "Test rejection",
        "status": CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
        "generated_at": datetime.now(timezone.utc),
        "state_fingerprint": "fp4",
    }
    mock_db = helper.get_mock_db()

    rejected_plan = await orchestrator.review_coordination_plan(
        plan_id="PLAN-REJECT-TEST",
        action=PlanReviewAction.REJECT,
        actor={"id": "OFFICER-1", "full_name": "Commander Miller", "role": "EMERGENCY_OFFICER"},
        notes="Hazard zone inaccessible via planned corridor.",
        db=mock_db,
    )

    assert rejected_plan.status == CoordinationPlanStatus.REJECTED
    assert rejected_plan.officer_review.decision == PlanReviewAction.REJECT

    # Verify in DB
    doc = helper.coordination_plans["PLAN-REJECT-TEST"]
    assert doc["status"] == CoordinationPlanStatus.REJECTED.value
