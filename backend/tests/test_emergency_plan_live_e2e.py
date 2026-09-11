import pytest
from app.db.mongodb import get_database
from app.services.agents.orchestrator import CentralOrchestrator
from app.models.agent import (
    PlanReviewRequest,
    PlanRecommendedResource,
    RecommendedShelter,
    RecommendedHealthcareFacility,
)
from app.models.enums import PlanReviewAction, NeedUrgency


@pytest.mark.asyncio
async def test_complete_emergency_officer_hitl_lifecycle():
    db = get_database()
    orchestrator = CentralOrchestrator(db)

    # 1. Setup genuine test situation, inventory, shelter, and hospital
    sit_id = "sit_live_e2e_001"
    res_id = "res_live_e2e_water"
    shelter_id = "sh_live_e2e_001"
    hospital_id = "hosp_live_e2e_001"

    await db["situations"].delete_many({"situation_id": sit_id})
    await db["resources"].delete_many({"_id": res_id})
    await db["shelters"].delete_many({"_id": shelter_id})
    await db["healthcare_facilities"].delete_many({"_id": hospital_id})
    await db["coordination_plans"].delete_many({"situation_id": sit_id})

    # Initial inventory: 500 Liters available
    await db["resources"].insert_one({
        "_id": res_id,
        "name": "Central Depot Water Supplies",
        "category": "WATER",
        "quantity": 500.0,
        "unit": "Liters",
        "status": "AVAILABLE",
        "location": {"latitude": 28.6139, "longitude": 77.2090, "address": "Delhi Logistics Hub"},
    })

    # Initial shelter: capacity 200, occupancy 50, remaining 150
    await db["shelters"].insert_one({
        "_id": shelter_id,
        "name": "Civic Community Shelter",
        "capacity": 200,
        "current_occupancy": 50,
        "status": "ACTIVE",
        "location": {"latitude": 28.6140, "longitude": 77.2095},
    })

    # Initial hospital: total beds 100, available 40
    await db["healthcare_facilities"].insert_one({
        "_id": hospital_id,
        "name": "Metro Emergency Hospital",
        "total_beds": 100,
        "available_beds": 40,
        "status": "OPERATIONAL",
        "location": {"latitude": 28.6150, "longitude": 77.2100},
    })

    # Initial situation with authoritative need
    await db["situations"].insert_one({
        "situation_id": sit_id,
        "title": "Severe Urban Inundation Zone 4",
        "severity": "CRITICAL",
        "status": "ACTIVE",
        "location": {"latitude": 28.6139, "longitude": 77.2090},
        "assessed_needs": [
            {
                "category": "WATER",
                "quantity": 100.0,
                "unit": "Liters",
                "urgency": "CRITICAL",
                "reason": "Potable water contamination in residential block.",
            }
        ],
    })

    # 2. Generate initial AI Coordination Plan
    ai_plan = await orchestrator.coordinate_situation(situation_id=sit_id, force_refresh=True)
    assert ai_plan is not None
    assert ai_plan.plan_id.startswith("PLAN-")
    assert ai_plan.status == "PENDING_OFFICER_REVIEW"

    # Verify Need vs Allocation separation: authoritative need remains 100 L
    assert len(ai_plan.assessed_needs) == 1
    assert ai_plan.assessed_needs[0].quantity == 100.0

    # 3. Test Invalid Modification Rejection (Overallocation)
    invalid_mod_req = PlanReviewRequest(
        action=PlanReviewAction.MODIFY,
        officer_id="officer_commander_01",
        officer_notes="Over-allocating beyond available warehouse stock",
        modified_allocations=[
            PlanRecommendedResource(
                resource_type="WATER",
                quantity_required=100.0,
                allocated_quantity=9999.0,  # Far exceeds 500 L
                unit="Liters",
                urgency=NeedUrgency.CRITICAL,
                matched_resource_id=res_id,
                matched_resource_name="Central Depot Water Supplies",
                depot_location="Delhi Logistics Hub",
                available_in_inventory=500.0,
            )
        ],
    )

    with pytest.raises(ValueError) as excinfo:
        await orchestrator.review_coordination_plan(ai_plan.plan_id, invalid_mod_req)
    assert "exceeds available stock" in str(excinfo.value)

    # 4. Test Valid Emergency Officer Modification
    # Officer changes allocation to 70 L
    valid_mod_req = PlanReviewRequest(
        action=PlanReviewAction.MODIFY,
        officer_id="officer_commander_01",
        officer_notes="Adjusted allocation to 70L based on forward scout report.",
        modified_allocations=[
            PlanRecommendedResource(
                resource_type="WATER",
                quantity_required=100.0,
                allocated_quantity=70.0,
                unit="Liters",
                urgency=NeedUrgency.CRITICAL,
                matched_resource_id=res_id,
                matched_resource_name="Central Depot Water Supplies",
                depot_location="Delhi Logistics Hub",
                available_in_inventory=500.0,
            )
        ],
        modified_shelters=[
            RecommendedShelter(
                shelter_id=shelter_id,
                shelter_name="Civic Community Shelter",
                recommended_occupancy=60,
                current_occupancy=50,
                total_capacity=200,
                remaining_capacity=150,
                evacuation_route="Corridor Beta",
                recommendation_reason="Safe higher-ground facility.",
            )
        ],
        modified_facilities=[
            RecommendedHealthcareFacility(
                facility_id=hospital_id,
                facility_name="Metro Emergency Hospital",
                allocated_patients=15,
                available_beds=40,
                total_beds=100,
                trauma_capable=True,
                recommendation_reason="Primary trauma center.",
            )
        ],
    )

    modified_plan = await orchestrator.review_coordination_plan(ai_plan.plan_id, valid_mod_req)
    assert modified_plan.status == "MODIFIED"
    assert modified_plan.diff_summary is not None
    assert modified_plan.diff_summary.changed_items_count > 0

    # Verify inventory was NOT consumed by modification
    res_doc = await db["resources"].find_one({"_id": res_id})
    assert res_doc["quantity"] == 500.0

    # 5. Officer Reviews Diff and Approves Modified Plan
    approve_req = PlanReviewRequest(
        action=PlanReviewAction.APPROVE,
        officer_id="officer_commander_01",
        officer_notes="Approved modified plan for immediate operational dispatch.",
    )

    active_plan = await orchestrator.review_coordination_plan(ai_plan.plan_id, approve_req)
    assert active_plan.status == "ACTIVE"
    assert active_plan.approved_at is not None
    assert active_plan.approved_by == "officer_commander_01"

    # 6. Verify inventory was NOT consumed merely by approval (Phase 8 execution will consume)
    res_doc_after = await db["resources"].find_one({"_id": res_id})
    assert res_doc_after["quantity"] == 500.0

    # 7. Verify Timeline and Audit events recorded
    plan_doc = await db["coordination_plans"].find_one({"plan_id": ai_plan.plan_id})
    assert plan_doc["status"] == "ACTIVE"
    assert "officer_review" in plan_doc
    assert plan_doc["officer_review"]["action"] == "APPROVE"

    # Cleanup
    await db["situations"].delete_many({"situation_id": sit_id})
    await db["resources"].delete_many({"_id": res_id})
    await db["shelters"].delete_many({"_id": shelter_id})
    await db["healthcare_facilities"].delete_many({"_id": hospital_id})
    await db["coordination_plans"].delete_many({"situation_id": sit_id})
