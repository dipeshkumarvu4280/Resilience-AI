import pytest
import asyncio
from datetime import datetime, timezone
from app.models.enums import (
    AgentName,
    ResourceType,
    NeedUrgency,
    ResourceStatus,
    ResourceCondition,
    SeverityLevel,
    ConflictType,
    DiffChangeType,
    CoordinationPlanStatus,
)
from app.models.agent import (
    AgentContext,
    CoordinationPlan,
    PlanRecommendedResource,
    DetectedConflict,
)
from app.services.agents.adapters.conflict_agent import ConflictResolutionAgent
from app.services.monitoring.replanning_service import DynamicReplanningService


@pytest.mark.asyncio
async def test_case_a_available_resource_preserved():
    """Case A: Water 70 available, 70 required -> 70 allocated, 0 shortfall, PRESERVED/UNCHANGED in diff."""
    plan_v1 = CoordinationPlan(
        plan_id="PLN-TEST-V1",
        situation_id="SIT-TEST-001",
        version=1,
        generated_at=datetime.now(timezone.utc),
        participating_agents=[AgentName.RESOURCE_COORDINATION_AGENT],
        assessed_priority=SeverityLevel.HIGH,
        assessed_needs=[{"resource_type": "Water", "quantity": 70.0, "unit": "Liters", "urgency": "HIGH"}],
        recommended_allocations=[
            PlanRecommendedResource(
                resource_type=ResourceType.WATER,
                quantity_required=70.0,
                unit="Liters",
                urgency=NeedUrgency.HIGH,
                matched_resource_id="RES-WATER-01",
                matched_resource_name="Regional Water Depot",
                available_in_inventory=70.0,
                allocated_quantity=70.0,
            )
        ],
        reasoning="Baseline plan v1",
        status=CoordinationPlanStatus.APPROVED,
    )

    plan_v2 = CoordinationPlan(
        plan_id="PLN-TEST-V2",
        situation_id="SIT-TEST-001",
        version=2,
        generated_at=datetime.now(timezone.utc),
        participating_agents=[AgentName.RESOURCE_COORDINATION_AGENT],
        assessed_priority=SeverityLevel.HIGH,
        assessed_needs=[{"resource_type": "Water", "quantity": 70.0, "unit": "Liters", "urgency": "HIGH"}],
        recommended_allocations=[
            PlanRecommendedResource(
                resource_type=ResourceType.WATER,
                quantity_required=70.0,
                unit="Liters",
                urgency=NeedUrgency.HIGH,
                matched_resource_id="RES-WATER-01",
                matched_resource_name="Regional Water Depot",
                available_in_inventory=70.0,
                allocated_quantity=70.0,
            )
        ],
        reasoning="Revised plan v2 with preserved inventory",
        status=CoordinationPlanStatus.PENDING_OFFICER_REVIEW,
    )

    diff = DynamicReplanningService.compute_plan_diff(plan_v1, plan_v2)
    assert len(diff.items) == 1
    item = diff.items[0]
    assert item.category == "Resource"
    assert item.diff_type == DiffChangeType.UNCHANGED.value
    assert item.previous_value == 70.0
    assert item.new_value == 70.0


@pytest.mark.asyncio
async def test_case_c_partial_allocation_and_shortfall():
    """Case C: Water 40 available, 100 required -> 40 allocated, 60 shortfall, CHANGED in diff."""
    plan_v1 = CoordinationPlan(
        plan_id="PLN-TEST-V1",
        situation_id="SIT-TEST-001",
        version=1,
        generated_at=datetime.now(timezone.utc),
        participating_agents=[AgentName.RESOURCE_COORDINATION_AGENT],
        assessed_priority=SeverityLevel.HIGH,
        assessed_needs=[{"resource_type": "Water", "quantity": 100.0, "unit": "Liters", "urgency": "HIGH"}],
        recommended_allocations=[
            PlanRecommendedResource(
                resource_type=ResourceType.WATER,
                quantity_required=100.0,
                unit="Liters",
                urgency=NeedUrgency.HIGH,
                matched_resource_id="RES-WATER-01",
                matched_resource_name="Regional Water Depot",
                available_in_inventory=100.0,
                allocated_quantity=100.0,
            )
        ],
        reasoning="Baseline plan v1",
        status=CoordinationPlanStatus.APPROVED,
    )

    # Replanned with reduced stock (40 available)
    plan_v2 = CoordinationPlan(
        plan_id="PLN-TEST-V2",
        situation_id="SIT-TEST-001",
        version=2,
        generated_at=datetime.now(timezone.utc),
        participating_agents=[AgentName.RESOURCE_COORDINATION_AGENT],
        assessed_priority=SeverityLevel.HIGH,
        assessed_needs=[{"resource_type": "Water", "quantity": 100.0, "unit": "Liters", "urgency": "HIGH"}],
        recommended_allocations=[
            PlanRecommendedResource(
                resource_type=ResourceType.WATER,
                quantity_required=100.0,
                unit="Liters",
                urgency=NeedUrgency.HIGH,
                matched_resource_id="RES-WATER-01",
                matched_resource_name="Regional Water Depot",
                available_in_inventory=40.0,
                allocated_quantity=40.0,
            )
        ],
        reasoning="Revised plan v2 with reduced inventory",
        status=CoordinationPlanStatus.PENDING_OFFICER_REVIEW,
    )

    diff = DynamicReplanningService.compute_plan_diff(plan_v1, plan_v2)
    assert len(diff.items) == 1
    item = diff.items[0]
    assert item.category == "Resource"
    assert item.diff_type == DiffChangeType.CHANGED.value
    assert item.previous_value == 100.0
    assert item.new_value == 40.0
    assert item.requires_officer_attention is True


@pytest.mark.asyncio
async def test_case_b_zero_inventory_shortage():
    """Case B: 0 available -> 0 allocated, 100 shortfall, REMOVED in diff."""
    plan_v1 = CoordinationPlan(
        plan_id="PLN-TEST-V1",
        situation_id="SIT-TEST-001",
        version=1,
        generated_at=datetime.now(timezone.utc),
        participating_agents=[AgentName.RESOURCE_COORDINATION_AGENT],
        assessed_priority=SeverityLevel.HIGH,
        assessed_needs=[{"resource_type": "Water", "quantity": 100.0, "unit": "Liters", "urgency": "HIGH"}],
        recommended_allocations=[
            PlanRecommendedResource(
                resource_type=ResourceType.WATER,
                quantity_required=100.0,
                unit="Liters",
                urgency=NeedUrgency.HIGH,
                matched_resource_id="RES-WATER-01",
                matched_resource_name="Regional Water Depot",
                available_in_inventory=100.0,
                allocated_quantity=100.0,
            )
        ],
        reasoning="Baseline plan v1",
        status=CoordinationPlanStatus.APPROVED,
    )

    # Depot is depleted completely
    plan_v2 = CoordinationPlan(
        plan_id="PLN-TEST-V2",
        situation_id="SIT-TEST-001",
        version=2,
        generated_at=datetime.now(timezone.utc),
        participating_agents=[AgentName.RESOURCE_COORDINATION_AGENT],
        assessed_priority=SeverityLevel.HIGH,
        assessed_needs=[{"resource_type": "Water", "quantity": 100.0, "unit": "Liters", "urgency": "HIGH"}],
        recommended_allocations=[],
        reasoning="Revised plan v2 with depleted inventory",
        status=CoordinationPlanStatus.PENDING_OFFICER_REVIEW,
    )

    diff = DynamicReplanningService.compute_plan_diff(plan_v1, plan_v2)
    assert len(diff.items) == 1
    item = diff.items[0]
    assert item.diff_type == DiffChangeType.REMOVED.value
    assert item.previous_value == 100.0
    assert item.new_value == 0.0


@pytest.mark.asyncio
async def test_case_d_full_requirement_preserved():
    """Case D: 100 required, 100 available -> 100 allocated, 0 shortfall, UNCHANGED in diff."""
    plan_v1 = CoordinationPlan(
        plan_id="PLN-TEST-V1",
        situation_id="SIT-TEST-001",
        version=1,
        generated_at=datetime.now(timezone.utc),
        participating_agents=[AgentName.RESOURCE_COORDINATION_AGENT],
        assessed_priority=SeverityLevel.HIGH,
        assessed_needs=[{"resource_type": "Blankets", "quantity": 50.0, "unit": "Pieces", "urgency": "HIGH"}],
        recommended_allocations=[
            PlanRecommendedResource(
                resource_type=ResourceType.BLANKETS,
                quantity_required=50.0,
                unit="Pieces",
                urgency=NeedUrgency.HIGH,
                matched_resource_id="RES-BLANKET-01",
                matched_resource_name="Central Depot Blankets",
                available_in_inventory=50.0,
                allocated_quantity=50.0,
            )
        ],
        reasoning="Baseline plan v1",
        status=CoordinationPlanStatus.APPROVED,
    )

    plan_v2 = CoordinationPlan(
        plan_id="PLN-TEST-V2",
        situation_id="SIT-TEST-001",
        version=2,
        generated_at=datetime.now(timezone.utc),
        participating_agents=[AgentName.RESOURCE_COORDINATION_AGENT],
        assessed_priority=SeverityLevel.HIGH,
        assessed_needs=[{"resource_type": "Blankets", "quantity": 50.0, "unit": "Pieces", "urgency": "HIGH"}],
        recommended_allocations=[
            PlanRecommendedResource(
                resource_type=ResourceType.BLANKETS,
                quantity_required=50.0,
                unit="Pieces",
                urgency=NeedUrgency.HIGH,
                matched_resource_id="RES-BLANKET-01",
                matched_resource_name="Central Depot Blankets",
                available_in_inventory=50.0,
                allocated_quantity=50.0,
            )
        ],
        reasoning="Revised plan v2",
        status=CoordinationPlanStatus.PENDING_OFFICER_REVIEW,
    )

    diff = DynamicReplanningService.compute_plan_diff(plan_v1, plan_v2)
    assert len(diff.items) == 1
    assert diff.items[0].diff_type == DiffChangeType.UNCHANGED.value
    assert diff.items[0].new_value == 50.0


@pytest.mark.asyncio
async def test_conflict_agent_receives_actual_availability():
    """Verify ConflictResolutionAgent correctly computes shortfall = max(required - available, 0)."""
    conflict_agent = ConflictResolutionAgent()
    actor = {"id": "USR-TEST", "full_name": "Test Officer", "role": "EMERGENCY_OFFICER"}
    
    # 70 available against 100 required -> shortfall 30
    ctx = AgentContext(
        situation_id="SIT-TEST",
        situation_title="Test Situation",
        emergency_type="Fire",
        description="Test",
        location_summary="Test",
        center_latitude=16.0,
        center_longitude=80.0,
        report_count=1,
        member_report_ids=["REP-1"],
        parameters={
            "assessed_needs": [
                {"resource_type": "Water", "requested_quantity": 100.0, "unit": "Liters", "urgency": "HIGH"}
            ],
            "recommended_allocations": [
                {
                    "resource_type": "Water",
                    "quantity_required": 100.0,
                    "unit": "Liters",
                    "urgency": "HIGH",
                    "matched_resource_id": "RES-WATER-01",
                    "matched_resource_name": "Water Depot",
                    "available_in_inventory": 70.0,
                    "allocated_quantity": 70.0,
                }
            ],
            "effective_priority": "HIGH",
        },
        actor_id=actor["id"],
        actor_name=actor["full_name"],
        actor_role=actor["role"],
    )

    res = await conflict_agent.execute(ctx)
    conflicts = res.structured_output.get("conflicts_detected", [])
    assert len(conflicts) == 1
    conf = conflicts[0]
    assert conf["conflict_type"] == ConflictType.INSUFFICIENT_QUANTITY.value
    assert conf["detected_quantity"] == 100.0
    assert conf["available_quantity"] == 70.0
    assert conf["shortfall"] == 30.0
