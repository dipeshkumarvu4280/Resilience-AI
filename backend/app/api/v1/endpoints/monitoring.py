import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.api.deps import require_officer
from app.models.user import UserResponse
from app.models.monitoring import (
    MonitoringEvent,
    ChangeImpactResult,
    PaginatedMonitoringEventsResponse,
    MonitoringStatsResponse,
    AcknowledgeEventRequest,
    AcknowledgeEventResponse,
    PlanDiffResult,
    PlanApprovalRequest,
    PlanModifyRequest,
    PlanRejectRequest,
    PlanActivationResponse,
)
from app.services.monitoring.monitoring_service import MonitoringService
from app.services.monitoring.impact_analyzer import ChangeImpactAnalyzer
from app.models.agent import CoordinationPlan

logger = logging.getLogger("resilience.api.monitoring")
router = APIRouter()


@router.get(
    "/events",
    response_model=PaginatedMonitoringEventsResponse,
    summary="List paginated live monitoring events",
)
async def list_monitoring_events(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    event_type: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    impact_level: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    situation_id: Optional[str] = Query(None),
    coordination_plan_id: Optional[str] = Query(None),
    is_impacted: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Returns paginated, chronologically sorted live monitoring events.
    Supports filtering by domain, impact severity, lifecycle status, impacted status, and search query.
    """
    return await MonitoringService.get_monitoring_events(
        page=page,
        limit=limit,
        event_type=event_type,
        source_type=source_type,
        impact_level=impact_level,
        status=status,
        situation_id=situation_id,
        coordination_plan_id=coordination_plan_id,
        is_impacted=is_impacted,
        search=search,
        db=db,
    )


@router.get(
    "/events/{event_id}",
    response_model=MonitoringEvent,
    summary="Get single monitoring event by ID",
)
async def get_monitoring_event_by_id(
    event_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Fetches detailed metadata and before/after state diff for a discrete event.
    """
    event = await MonitoringService.get_event_by_id(event_id, db=db)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring event '{event_id}' not found.",
        )
    return event


@router.get(
    "/events/{event_id}/impact",
    response_model=ChangeImpactResult,
    summary="Get change impact assessment for an event",
)
async def get_event_impact(
    event_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Returns the deterministic ChangeImpactResult associated with a specific monitoring event.
    """
    impact = await MonitoringService.get_event_impact(event_id, db=db)
    if not impact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Change impact assessment for event '{event_id}' not found.",
        )
    return impact


@router.get(
    "/impacts",
    response_model=List[ChangeImpactResult],
    summary="List recent change impact assessments",
)
async def list_recent_impacts(
    limit: int = Query(50, ge=1, le=100),
    situation_id: Optional[str] = Query(None),
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Returns recent change impact assessment results.
    """
    return await MonitoringService.list_recent_impacts(
        limit=limit,
        situation_id=situation_id,
        db=db,
    )


@router.get(
    "/stats",
    response_model=MonitoringStatsResponse,
    summary="Get live monitoring telemetry statistics",
)
async def get_monitoring_stats(
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Returns real-time KPI metrics for the Live Monitoring dashboard.
    """
    return await MonitoringService.get_monitoring_stats(db=db)


@router.get(
    "/situations/{situation_id}",
    response_model=PaginatedMonitoringEventsResponse,
    summary="Get monitoring events for a specific situation",
)
async def get_situation_monitoring_events(
    situation_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Fetches all monitoring events correlated with a specific situation cluster.
    """
    return await MonitoringService.get_monitoring_events(
        page=page,
        limit=limit,
        situation_id=situation_id,
        db=db,
    )


@router.get(
    "/plans/{plan_id}",
    response_model=PaginatedMonitoringEventsResponse,
    summary="Get monitoring events for a specific coordination plan",
)
async def get_plan_monitoring_events(
    plan_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Fetches all monitoring events affecting a specific active coordination plan.
    """
    return await MonitoringService.get_monitoring_events(
        page=page,
        limit=limit,
        coordination_plan_id=plan_id,
        db=db,
    )


@router.post(
    "/events/{event_id}/acknowledge",
    response_model=AcknowledgeEventResponse,
    summary="Acknowledge a monitoring alert",
)
async def acknowledge_monitoring_event(
    event_id: str,
    payload: AcknowledgeEventRequest,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Records an authenticated Emergency Officer acknowledgement of an operational alert.
    Does NOT approve replanning or mutate operational allocations.
    """
    try:
        actor_dict = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
        }
        return await MonitoringService.acknowledge_event(
            event_id=event_id,
            actor=actor_dict,
            notes=payload.notes,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/reprocess/{event_id}",
    response_model=ChangeImpactResult,
    summary="Reprocess change impact analysis for an event",
)
async def reprocess_event_impact(
    event_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Re-evaluates deterministic change impact analysis for a specified event against current state.
    """
    event = await MonitoringService.get_event_by_id(event_id, db=db)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring event '{event_id}' not found.",
        )

    situation_doc = None
    if event.situation_id:
        situation_doc = await db["situations"].find_one({"situation_id": event.situation_id})

    active_plan_obj = None
    if event.coordination_plan_id:
        plan_doc = await db["coordination_plans"].find_one({"plan_id": event.coordination_plan_id})
        if plan_doc:
            try:
                active_plan_obj = CoordinationPlan(**plan_doc)
            except Exception:
                pass

    impact = await ChangeImpactAnalyzer.analyze_impact(
        event=event,
        situation=situation_doc,
        active_plan=active_plan_obj,
        db=db,
    )

    await db["change_impacts"].update_one(
        {"event_id": event_id},
        {"$set": impact.model_dump()},
        upsert=True,
    )
    return impact


# =========================================================================
# PHASE 6.3 & 6.4 DYNAMIC RE-PLANNING & ACTIVATION ENDPOINTS
# =========================================================================

@router.post(
    "/events/{event_id}/replan",
    response_model=Optional[CoordinationPlan],
    summary="Trigger impact-aware dynamic re-planning for an event",
)
async def trigger_event_replanning(
    event_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Executes selective agent re-planning strictly for affected domains triggered by an operational event.
    Preserves unaffected plan components and creates an immutable revised plan in PENDING_OFFICER_REVIEW.
    """
    event = await MonitoringService.get_event_by_id(event_id, db=db)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring event '{event_id}' not found.",
        )

    impact = await MonitoringService.get_event_impact(event_id, db=db)
    if not impact:
        # Reprocess impact first
        situation_doc = None
        if event.situation_id:
            situation_doc = await db["situations"].find_one({"situation_id": event.situation_id})
        active_plan_obj = None
        if event.coordination_plan_id:
            p_doc = await db["coordination_plans"].find_one({"plan_id": event.coordination_plan_id})
            if p_doc:
                active_plan_obj = CoordinationPlan(**p_doc)

        impact = await ChangeImpactAnalyzer.analyze_impact(
            event=event,
            situation=situation_doc,
            active_plan=active_plan_obj,
            db=db,
        )

    actor_dict = {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
    }

    from app.services.monitoring.replanning_service import DynamicReplanningService
    revised_plan = await DynamicReplanningService.replan_from_impact(
        impact=impact,
        event=event,
        actor=actor_dict,
        db=db,
    )

    return revised_plan


@router.get(
    "/plans/{plan_id}/diff",
    response_model=PlanDiffResult,
    summary="Get deterministic plan diff for a revised response plan",
)
async def get_plan_diff(
    plan_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Fetches the deterministic component-level diff (ADDED, REMOVED, CHANGED, UNCHANGED)
    between a revised plan and its previous active baseline.
    """
    plan_doc = await db["coordination_plans"].find_one({"plan_id": plan_id})
    if not plan_doc:
        plan_doc = await db["simulated_coordination_plans"].find_one({"plan_id": plan_id})
    if not plan_doc:
        sim_doc = await db["simulations"].find_one({"result_plan.plan_id": plan_id})
        if sim_doc and sim_doc.get("result_plan"):
            plan_doc = sim_doc["result_plan"]
            if sim_doc.get("diff_result"):
                return PlanDiffResult(**sim_doc["diff_result"])
    if not plan_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coordination plan '{plan_id}' not found.",
        )

    plan = CoordinationPlan(**plan_doc)
    if plan.diff_summary:
        return PlanDiffResult(**plan.diff_summary)

    # Compute dynamically if not stored
    prev_plan_id = plan.previous_plan_id
    if not prev_plan_id:
        # Fallback to version - 1
        prev_doc = await db["coordination_plans"].find_one({
            "situation_id": plan.situation_id,
            "version": plan.version - 1,
        })
        if prev_doc:
            prev_plan_id = prev_doc.get("plan_id")

    if not prev_plan_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No previous plan version available for comparison.",
        )

    prev_doc = await db["coordination_plans"].find_one({"plan_id": prev_plan_id})
    if not prev_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Previous coordination plan '{prev_plan_id}' not found.",
        )

    prev_plan = CoordinationPlan(**prev_doc)
    from app.services.monitoring.replanning_service import DynamicReplanningService
    return DynamicReplanningService.compute_plan_diff(prev_plan, plan)


@router.get(
    "/situations/{situation_id}/plan-history",
    response_model=List[CoordinationPlan],
    summary="Get immutable version history of plans for a situation",
)
async def get_situation_plan_history(
    situation_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Fetches the full chronological version lineage of response plans for a situation.
    """
    clean_sit_id = situation_id.strip().upper()
    cursor = db["coordination_plans"].find({"situation_id": clean_sit_id}).sort("version", 1)
    plans_raw = await cursor.to_list(length=100)
    return [CoordinationPlan(**p) for p in plans_raw]


@router.post(
    "/plans/{plan_id}/approve",
    response_model=PlanActivationResponse,
    summary="Approve and activate a response plan with stale-plan protection",
)
async def approve_and_activate_plan(
    plan_id: str,
    payload: PlanApprovalRequest,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Performs authenticated server-side validation, verifies stale-plan protection,
    supersedes previous active plan, and activates the revised plan.
    """
    actor_dict = {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
    }

    from app.services.monitoring.plan_activation_service import PlanActivationService
    try:
        return await PlanActivationService.approve_and_activate_plan(
            plan_id=plan_id,
            officer_actor=actor_dict,
            officer_notes=payload.officer_notes,
            expected_state_fingerprint=payload.expected_state_fingerprint,
            db=db,
        )
    except ValueError as e:
        err_msg = str(e)
        if "STALE_PLAN_DETECTED" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=err_msg,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )


@router.post(
    "/plans/{plan_id}/modify",
    response_model=CoordinationPlan,
    summary="Modify operational allocations in a revised response plan",
)
async def modify_revised_plan(
    plan_id: str,
    payload: PlanModifyRequest,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Modifies specific operational allocation values in a revised response plan.
    Keeps the plan in PENDING_OFFICER_REVIEW until explicitly approved.
    """
    actor_dict = {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
    }

    from app.services.monitoring.plan_activation_service import PlanActivationService
    try:
        return await PlanActivationService.modify_revised_plan(
            plan_id=plan_id,
            modify_req=payload,
            officer_actor=actor_dict,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/plans/{plan_id}/reject",
    response_model=CoordinationPlan,
    summary="Reject a revised response plan",
)
async def reject_revised_plan(
    plan_id: str,
    payload: PlanRejectRequest,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Rejects a revised response plan with a mandatory explanation.
    The previous active plan remains active.
    """
    actor_dict = {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
    }

    from app.services.monitoring.plan_activation_service import PlanActivationService
    try:
        return await PlanActivationService.reject_revised_plan(
            plan_id=plan_id,
            reject_req=payload,
            officer_actor=actor_dict,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

