import pytest
from datetime import datetime, timezone
from app.models.enums import (
    CoordinationPlanStatus,
    ResourceType,
    NeedUrgency,
    ConflictType,
    ConflictStatus,
    SeverityLevel,
    DiffChangeType,
    OperationalDomain,
    AgentName,
)
from app.models.agent import (
    CoordinationPlan,
    PlanRecommendedResource,
    RecommendedShelter,
    RecommendedHealthcareFacility,
    RecommendedVolunteerAssignment,
    RecommendedTransport,
    RecommendedRoute,
    DetectedConflict,
    ConflictResolutionSummary,
)
from app.services.monitoring.replanning_service import DynamicReplanningService


def build_sample_baseline_plan() -> CoordinationPlan:
    """Builds a deterministic baseline coordination plan for testing diff calculations."""
    return CoordinationPlan(
        plan_id="PLN-BASE-001-V1",
        situation_id="SIT-TEST-001",
        version=1,
        state_fingerprint="fp-base-001",
        generated_at=datetime.now(timezone.utc),
        status=CoordinationPlanStatus.ACTIVE,
        assessed_priority=SeverityLevel.HIGH,
        reasoning="Baseline operational coordination plan.",
        constraints=["Standard regional emergency constraints applied."],
        recommended_allocations=[
            PlanRecommendedResource(
                resource_type=ResourceType.WATER,
                quantity_required=100.0,
                unit="Liters",
                urgency=NeedUrgency.HIGH,
                matched_resource_id="RES-WATER-01",
                matched_resource_name="Potable Water Depot Central",
                available_in_inventory=100.0,
                allocated_quantity=70.0,
            ),
            PlanRecommendedResource(
                resource_type=ResourceType.BLANKETS,
                quantity_required=50.0,
                unit="Units",
                urgency=NeedUrgency.MEDIUM,
                matched_resource_id="RES-BLANKET-01",
                matched_resource_name="Thermal Blankets Depot North",
                available_in_inventory=50.0,
                allocated_quantity=50.0,
            ),
        ],
        recommended_shelters=[
            RecommendedShelter(
                shelter_id="SHL-001",
                shelter_name="Central Community Hall",
                distance_km=2.5,
                total_capacity=500.0,
                current_occupancy=358.0,
                remaining_capacity=142.0,
                recommended_occupancy=142.0,
                coverage_percentage=100.0,
                suitability_score=95.0,
                recommendation_reason="Primary regional evacuation center.",
                status="AVAILABLE",
            )
        ],
        recommended_facilities=[
            RecommendedHealthcareFacility(
                facility_id="HCF-001",
                facility_name="District General Hospital",
                distance_km=3.1,
                total_beds=200.0,
                available_beds=50.0,
                allocated_patients=20.0,
                icu_available=5,
                status="AVAILABLE",
                recommendation_reason="Trauma and emergency ready.",
            )
        ],
        recommended_volunteers=[
            RecommendedVolunteerAssignment(
                volunteer_id="VOL-001",
                volunteer_name="Manish Sharma",
                role_or_skill="Medical First Responder",
                assigned_operation="Triage Support at Central Hall",
                availability_status="Available Immediately",
                recommendation_reason="Closest certified medic.",
            )
        ],
        recommended_transports=[
            RecommendedTransport(
                transport_id="TRN-001",
                vehicle_name="Ambulance Fleet Unit 4",
                vehicle_type="Ambulance",
                capacity=4.0,
                allocated_load_or_passengers=2.0,
                current_status="AVAILABLE",
                assigned_mission="Medical Evacuation Route A",
                recommendation_reason="High speed trauma transit.",
            )
        ],
        recommended_routes=[
            RecommendedRoute(
                route_id="RTE-001",
                origin_name="Incident Site",
                destination_name="District General Hospital",
                origin_coordinates={"latitude": 16.24, "longitude": 80.64},
                destination_coordinates={"latitude": 16.26, "longitude": 80.66},
                distance_km=4.2,
                estimated_duration_minutes=20.0,
                road_condition_status="PASSABLE",
                transport_id="TRN-001",
                assigned_mission="Medical Evacuation Corridor Alpha",
                recommendation_reason="Clear main arterial highway.",
            )
        ],
        conflicts=[],
        conflict_summary=ConflictResolutionSummary(
            conflicts_detected=[],
            conflicts_count=0,
            resolved_conflicts=0,
            unresolved_conflicts=0,
        ),
    )


def test_unchanged_plan_diff_preserves_allocations():
    """Verify an identical revised plan generates UNCHANGED diffs without false 0s or false removals."""
    plan_v1 = build_sample_baseline_plan()
    plan_v2 = build_sample_baseline_plan()
    plan_v2.version = 2
    plan_v2.plan_id = "PLN-BASE-001-V2"

    diff = DynamicReplanningService.compute_plan_diff(plan_v1, plan_v2)
    assert not diff.is_material_change
    assert all(item.diff_type == DiffChangeType.UNCHANGED.value for item in diff.items)

    water_diff = next(item for item in diff.items if item.category == "Resource" and "Water" in item.entity_name)
    assert water_diff.diff_type == DiffChangeType.UNCHANGED.value
    assert water_diff.previous_value == 70.0
    assert water_diff.new_value == 70.0
    assert not water_diff.requires_officer_attention


def test_genuine_resource_reduction_diff():
    """Verify available inventory decrease generates CHANGED diff with accurate shortfall explanation."""
    plan_v1 = build_sample_baseline_plan()
    plan_v2 = build_sample_baseline_plan()
    plan_v2.version = 2
    plan_v2.plan_id = "PLN-BASE-001-V2"

    # Reduce water allocation from 70 to 40 due to stock drop
    plan_v2.recommended_allocations[0].allocated_quantity = 40.0

    diff = DynamicReplanningService.compute_plan_diff(plan_v1, plan_v2)
    assert diff.is_material_change

    water_diff = next(item for item in diff.items if item.category == "Resource" and "Water" in item.entity_name)
    assert water_diff.diff_type == DiffChangeType.CHANGED.value
    assert water_diff.previous_value == 70.0
    assert water_diff.new_value == 40.0
    assert water_diff.requires_officer_attention is True
    assert "shortfall" in water_diff.reason.lower()


def test_shelter_occupancy_change_diff():
    """Verify shelter occupancy change updates remaining capacity and generates clear diff explanation."""
    plan_v1 = build_sample_baseline_plan()
    plan_v2 = build_sample_baseline_plan()
    plan_v2.version = 2
    plan_v2.plan_id = "PLN-BASE-001-V2"

    # Shelter occupancy increases from 358 to 420 (capacity 500), remaining drops from 142 to 80
    plan_v2.recommended_shelters[0].current_occupancy = 420.0
    plan_v2.recommended_shelters[0].remaining_capacity = 80.0
    plan_v2.recommended_shelters[0].recommended_occupancy = 80.0

    diff = DynamicReplanningService.compute_plan_diff(plan_v1, plan_v2)
    assert diff.is_material_change

    shelter_diff = next(item for item in diff.items if item.category == "Shelter")
    assert shelter_diff.diff_type == DiffChangeType.CHANGED.value
    assert shelter_diff.previous_value["occupancy"] == 142.0
    assert shelter_diff.new_value["occupancy"] == 80.0
    assert "occupancy" in shelter_diff.reason.lower()


def test_route_blockage_and_rerouting_diff():
    """Verify route condition PASSABLE -> BLOCKED and ETA delta generates accurate Route diff."""
    plan_v1 = build_sample_baseline_plan()
    plan_v2 = build_sample_baseline_plan()
    plan_v2.version = 2
    plan_v2.plan_id = "PLN-BASE-001-V2"

    # Route blocked, detour increases ETA from 20 to 35 min
    plan_v2.recommended_routes[0].road_condition_status = "BLOCKED"
    plan_v2.recommended_routes[0].estimated_duration_minutes = 35.0

    diff = DynamicReplanningService.compute_plan_diff(plan_v1, plan_v2)
    assert diff.is_material_change

    route_diff = next(item for item in diff.items if item.category == "Route")
    assert route_diff.diff_type == DiffChangeType.CHANGED.value
    assert route_diff.previous_value["status"] == "PASSABLE"
    assert route_diff.new_value["status"] == "BLOCKED"
    assert route_diff.previous_value["eta_minutes"] == 20.0
    assert route_diff.new_value["eta_minutes"] == 35.0
    assert route_diff.requires_officer_attention is True


def test_healthcare_icu_reduction_diff():
    """Verify ICU bed reduction generates CHANGED Healthcare diff with attention flag."""
    plan_v1 = build_sample_baseline_plan()
    plan_v2 = build_sample_baseline_plan()
    plan_v2.version = 2
    plan_v2.plan_id = "PLN-BASE-001-V2"

    # ICU drops from 5 to 2
    plan_v2.recommended_facilities[0].icu_available = 2

    diff = DynamicReplanningService.compute_plan_diff(plan_v1, plan_v2)
    assert diff.is_material_change

    hosp_diff = next(item for item in diff.items if item.category == "Healthcare")
    assert hosp_diff.diff_type == DiffChangeType.CHANGED.value
    assert hosp_diff.previous_value["icu_available"] == 5
    assert hosp_diff.new_value["icu_available"] == 2
    assert hosp_diff.requires_officer_attention is True


def test_conflict_deterministic_diff_keying():
    """Verify conflict additions and updates are tracked by conflict type and resource, not volatile UUIDs."""
    plan_v1 = build_sample_baseline_plan()
    plan_v2 = build_sample_baseline_plan()
    plan_v2.version = 2
    plan_v2.plan_id = "PLN-BASE-001-V2"

    # Add a shortfall conflict for water
    cnf = DetectedConflict(
        conflict_id="CNF-NEW-UUID-999",
        conflict_type=ConflictType.RESOURCE_SHORTAGE,
        severity=SeverityLevel.HIGH,
        description="Shortfall of 30 Liters for Water",
        affected_resource="Water",
        shortfall=30.0,
        resolution_status=ConflictStatus.UNRESOLVED,
        officer_attention_required=True,
        explanation="Inventory reduced to 40 against 70 required.",
    )
    plan_v2.conflicts = [cnf]

    diff = DynamicReplanningService.compute_plan_diff(plan_v1, plan_v2)
    assert diff.is_material_change

    conflict_diff = next(item for item in diff.items if item.category == "Conflict")
    assert conflict_diff.diff_type == DiffChangeType.ADDED.value
    assert conflict_diff.requires_officer_attention is True
    assert "Shortfall: 30" in conflict_diff.reason
