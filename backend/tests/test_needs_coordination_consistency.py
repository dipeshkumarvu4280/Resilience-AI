import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.models.enums import (
    ResourceType,
    NeedUrgency,
    CoordinationPlanStatus,
    PlanReviewAction,
    TimelineEventType,
    UserRole,
    SeverityLevel,
    AgentRunStatus,
    ConflictType,
    ResolutionStrategy,
    ConflictStatus,
)
from app.models.agent import (
    AgentContext,
    PlanRecommendedResource,
    CoordinationPlan,
    ConflictResolutionSummary,
)
from app.models.monitoring import PlanModifyRequest, PlanRejectRequest, PlanApprovalRequest
from app.services.agents.adapters.needs_agent import NeedsAgent
from app.services.agents.adapters.resource_agent import ResourceCoordinationAgent
from app.services.agents.adapters.conflict_agent import ConflictResolutionAgent
from app.services.agents.orchestrator import CentralOrchestrator


@pytest.mark.asyncio
async def test_needs_agent_preserves_officer_assessed_needs_verbatim():
    """
    Test 1: NeedsAgent must preserve officer-assessed needs verbatim and not overwrite them with heuristic defaults.
    """
    agent = NeedsAgent()
    officer_needs = [
        {
            "resource_type": "WATER",
            "quantity": 100.0,
            "requested_quantity": 100.0,
            "unit": "liters",
            "urgency": "CRITICAL",
            "source": "OFFICER_NEEDS_ASSESSMENT",
            "officer_assessed": True,
            "ai_inferred": False,
            "reasoning": "Officer defined 100L pure drinking water",
        },
        {
            "resource_type": "BLANKETS",
            "quantity": 50.0,
            "requested_quantity": 50.0,
            "unit": "pieces",
            "urgency": "MEDIUM",
            "source": "OFFICER_NEEDS_ASSESSMENT",
            "officer_assessed": True,
            "ai_inferred": False,
            "reasoning": "Officer defined 50 thermal blankets",
        },
    ]

    context = AgentContext(
        situation_id="SIT-TEST-001",
        situation_title="Flood in Sector 4",
        emergency_type="FLOOD",
        description="Severe flooding reported by field team.",
        location_summary="Sector 4",
        center_latitude=12.9716,
        center_longitude=77.5946,
        existing_needs=officer_needs,
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    needs = result.structured_output.get("needs", [])
    assert len(needs) >= 2

    # Verify water need was preserved verbatim
    water_need = next((n for n in needs if n["resource_type"].upper() == "WATER"), None)
    assert water_need is not None
    assert float(water_need["quantity"]) == 100.0
    assert water_need["officer_assessed"] is True
    assert water_need["source"] == "OFFICER_NEEDS_ASSESSMENT"

    # Verify blankets need was preserved verbatim
    blanket_need = next((n for n in needs if n["resource_type"].upper() == "BLANKETS"), None)
    assert blanket_need is not None
    assert float(blanket_need["quantity"]) == 50.0
    assert blanket_need["officer_assessed"] is True
    assert blanket_need["source"] == "OFFICER_NEEDS_ASSESSMENT"


@pytest.mark.asyncio
async def test_resource_agent_distinguishes_required_from_allocated():
    """
    Test 2: ResourceCoordinationAgent must assign quantity_required from need and cap allocated_quantity to available stock.
    """
    agent = ResourceCoordinationAgent()
    needs = [
        {
            "resource_type": "WATER",
            "quantity": 500.0,
            "requested_quantity": 500.0,
            "unit": "liters",
            "urgency": "CRITICAL",
            "officer_assessed": True,
            "source": "OFFICER_NEEDS_ASSESSMENT",
        },
    ]

    # Candidate with only 200L available
    mock_candidate = AsyncMock()
    mock_candidate.resource_id = "depot-001"
    mock_candidate.name = "Central Depot"
    mock_candidate.quantity_available = 200.0
    mock_candidate.recommended_allocation = 200.0
    mock_candidate.location = AsyncMock(address="Main Hub", city="Capital City")
    mock_candidate.distance_km = 3.5

    mock_match = AsyncMock()
    mock_match.resource_type = ResourceType.WATER
    mock_match.requested_quantity = 500.0
    mock_match.unit = "liters"
    mock_match.urgency = NeedUrgency.CRITICAL
    mock_match.candidates = [mock_candidate]

    mock_matching_res = AsyncMock()
    mock_matching_res.needs_matches = [mock_match]

    with patch("app.services.agents.adapters.resource_agent.match_resources_for_needs", return_value=mock_matching_res):
        context = AgentContext(
            situation_id="SIT-TEST-002",
            situation_title="Flood Situation",
            emergency_type="FLOOD",
            description="Water requirement",
            location_summary="Downtown",
            center_latitude=12.9716,
            center_longitude=77.5946,
            existing_needs=needs,
            parameters={"assessed_needs": needs},
        )

        result = await agent.execute(context)
        assert result.status == AgentRunStatus.COMPLETED
        allocations = result.structured_output.get("recommended_allocations", [])
        assert len(allocations) >= 1
        water_alloc = next((a for a in allocations if a.get("resource_type") == "WATER" or a.get("resource_type") == ResourceType.WATER.value), None)
        assert water_alloc is not None
        assert water_alloc["quantity_required"] == 500.0
        assert water_alloc["allocated_quantity"] == 200.0


@pytest.mark.asyncio
async def test_conflict_resolution_agent_computes_shortfall_against_requirement():
    """
    Test 3: ConflictResolutionAgent calculates shortfall as quantity_required - available_stock.
    """
    agent = ConflictResolutionAgent()
    needs = [
        {
            "resource_type": "Water",
            "quantity": 500.0,
            "requested_quantity": 500.0,
            "unit": "liters",
            "urgency": "CRITICAL",
        }
    ]
    allocations = [
        {
            "resource_type": "Water",
            "quantity_required": 500.0,
            "allocated_quantity": 200.0,
            "available_in_inventory": 200.0,
            "matched_resource_id": "depot-001",
            "matched_resource_name": "Central Depot",
            "unit": "liters",
            "urgency": "CRITICAL",
        }
    ]

    context = AgentContext(
        situation_id="SIT-TEST-003",
        situation_title="Conflict Test",
        emergency_type="FLOOD",
        description="Testing shortfall",
        location_summary="North District",
        center_latitude=12.9716,
        center_longitude=77.5946,
        parameters={"assessed_needs": needs, "recommended_allocations": allocations},
    )

    result = await agent.execute(context)
    assert result.status == AgentRunStatus.COMPLETED
    summary = ConflictResolutionSummary(**result.structured_output)
    assert summary.conflicts_count >= 1
    conf = summary.conflicts_detected[0]
    assert conf.shortfall == 300.0
    assert conf.conflict_type == ConflictType.INSUFFICIENT_QUANTITY
    assert conf.resolution_strategy == ResolutionStrategy.PARTIAL_ALLOCATION


@pytest.mark.asyncio
async def test_orchestrator_plan_modification_validation():
    """
    Test 4: Orchestrator review_coordination_plan with action=MODIFY validates against depot stock.
    """
    orchestrator = CentralOrchestrator()

    mock_plan = {
        "plan_id": "PLAN-SIT-004-V1",
        "situation_id": "SIT-004",
        "status": CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
        "version": 1,
        "state_fingerprint": "fp123",
        "reasoning": "Test coordination plan reasoning",
        "recommended_allocations": [
            {
                "resource_type": ResourceType.WATER,
                "quantity_required": 100.0,
                "allocated_quantity": 50.0,
                "matched_resource_id": "DEPOT-01",
                "matched_resource_name": "North Hub",
                "unit": "liters",
                "urgency": NeedUrgency.CRITICAL,
            }
        ],
        "assessed_priority": SeverityLevel.CRITICAL,
        "assessed_needs": [],
        "recommended_shelters": [],
        "recommended_facilities": [],
        "recommended_volunteers": [],
        "recommended_transports": [],
        "recommended_routes": [],
        "conflicts": [],
        "created_at": datetime.now(timezone.utc),
        "generated_at": datetime.now(timezone.utc),
    }

    mock_depot = {
        "_id": "DEPOT-01",
        "name": "North Hub",
        "quantity_available": 80.0,
        "inventory": [
            {
                "resource_type": "WATER",
                "item_name": "Potable Water",
                "quantity": 80.0,
                "unit": "liters",
            }
        ],
    }

    async def mock_update_one(filter_query, update_doc):
        if "$set" in update_doc:
            mock_plan.update(update_doc["$set"])
        return AsyncMock(matched_count=1)

    mock_db = {
        "coordination_plans": AsyncMock(
            find_one=AsyncMock(side_effect=lambda q: mock_plan),
            update_one=AsyncMock(side_effect=mock_update_one),
            update_many=AsyncMock(return_value=AsyncMock(matched_count=1)),
        ),
        "resources": AsyncMock(
            find_one=AsyncMock(return_value=mock_depot)
        ),
        "situations": AsyncMock(
            find_one=AsyncMock(return_value={"situation_id": "SIT-004", "state_fingerprint": "fp123"})
        ),
        "citizen_reports": AsyncMock(
            update_one=AsyncMock(return_value=AsyncMock(matched_count=1))
        ),
        "audit_logs": AsyncMock(
            insert_one=AsyncMock(return_value=AsyncMock())
        ),
        "timeline_events": AsyncMock(
            insert_one=AsyncMock(return_value=AsyncMock())
        ),
        "response_tasks": AsyncMock(
            insert_one=AsyncMock(return_value=AsyncMock()),
            insert_many=AsyncMock(return_value=AsyncMock()),
        ),
    }

    mod_allocations_valid = [
        PlanRecommendedResource(
            resource_type=ResourceType.WATER,
            quantity_required=100.0,
            allocated_quantity=70.0,
            matched_resource_id="DEPOT-01",
            matched_resource_name="North Hub",
            unit="liters",
            urgency=NeedUrgency.CRITICAL,
        )
    ]

    actor = {"id": "OFFICER-01", "full_name": "Commander Vance", "role": "EMERGENCY_OFFICER"}

    updated_plan = await orchestrator.review_coordination_plan(
        db=mock_db,
        plan_id="PLAN-SIT-004-V1",
        action=PlanReviewAction.MODIFY,
        actor=actor,
        notes="Increased priority allocation for flood victims",
        modified_allocations=mod_allocations_valid,
    )
    assert updated_plan.status == CoordinationPlanStatus.MODIFIED

    # Reset plan status to PENDING_OFFICER_REVIEW for Case B
    mock_plan["status"] = CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value

    # Case B: Officer modifies allocation to 120 (> 80 stock) -> Raises ValueError (422 in API)
    mod_allocations_invalid = [
        PlanRecommendedResource(
            resource_type=ResourceType.WATER,
            quantity_required=100.0,
            allocated_quantity=120.0,
            matched_resource_id="DEPOT-01",
            matched_resource_name="North Hub",
            unit="liters",
            urgency=NeedUrgency.CRITICAL,
        )
    ]

    with pytest.raises(ValueError) as excinfo:
        await orchestrator.review_coordination_plan(
            db=mock_db,
            plan_id="PLAN-SIT-004-V1",
            action=PlanReviewAction.MODIFY,
            actor=actor,
            notes="Exceeding available stock",
            modified_allocations=mod_allocations_invalid,
        )
    assert "exceeds available stock" in str(excinfo.value)
