import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.api.deps import require_officer, get_current_user
from app.models.user import UserResponse
from app.models.enums import TimelineEventType, AllocationStatus, ResourceStatus, ResourceType
from app.models.resource import (
    EmergencyNeedItem,
    NeedsAssessmentCreate,
    NeedsAssessmentResponse,
    AINeedsSuggestionResponse,
    ResourceMatchingResponse,
    AllocationCreateRequest,
    AllocationActionRequest,
    AllocationResponse,
    generate_allocation_id,
)
from app.services.timeline import record_timeline_event
from app.services.resource_matching import match_resources_for_needs
from app.services.ai_coordinator import generate_ai_needs_assessment

logger = logging.getLogger("resilience.needs_allocations")
router = APIRouter()


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
    return dt


def parse_allocation_doc(doc: dict) -> AllocationResponse:
    return AllocationResponse(
        allocation_id=doc["allocation_id"],
        report_id=doc["report_id"],
        need_id=doc["need_id"],
        resource_id=doc["resource_id"],
        resource_name=doc.get("resource_name", "Emergency Resource"),
        resource_type=ResourceType(doc["resource_type"]),
        requested_quantity=float(doc["requested_quantity"]),
        approved_quantity=float(doc.get("approved_quantity", 0.0)),
        unit=doc.get("unit", "units"),
        status=AllocationStatus(doc.get("status", AllocationStatus.PROPOSED.value)),
        proposed_by=doc["proposed_by"],
        proposed_by_id=doc["proposed_by_id"],
        approved_by=doc.get("approved_by"),
        approved_by_id=doc.get("approved_by_id"),
        notes=doc.get("notes"),
        created_at=ensure_utc(doc.get("created_at")),
        updated_at=ensure_utc(doc.get("updated_at")),
    )


# --- Needs Assessment ---

@router.get("/reports/{report_id}/needs", response_model=Optional[NeedsAssessmentResponse])
async def get_report_needs(
    report_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get structured needs assessment for an emergency report.
    """
    clean_id = report_id.strip().upper()
    doc = await db["needs_assessments"].find_one({"report_id": clean_id})
    if not doc:
        return None

    return NeedsAssessmentResponse(
        report_id=doc["report_id"],
        needs=[EmergencyNeedItem(**n) for n in doc.get("needs", [])],
        assessed_by=doc.get("assessed_by", "Officer"),
        assessed_by_id=doc.get("assessed_by_id", ""),
        assessed_at=ensure_utc(doc.get("assessed_at")),
        updated_at=ensure_utc(doc.get("updated_at")),
    )


@router.post("/reports/{report_id}/needs", response_model=NeedsAssessmentResponse)
async def create_or_update_report_needs(
    report_id: str,
    payload: NeedsAssessmentCreate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Create or update structured emergency needs assessment for a report.
    Human-in-the-loop review by authenticated officer.
    """
    clean_id = report_id.strip().upper()
    report = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report '{report_id}' not found.",
        )

    now = datetime.now(timezone.utc)
    needs_data = [n.model_dump() for n in payload.needs]

    assessment_doc = {
        "report_id": clean_id,
        "needs": needs_data,
        "assessed_by": current_user.full_name,
        "assessed_by_id": current_user.id,
        "assessed_at": now,
        "updated_at": now,
    }

    await db["needs_assessments"].update_one(
        {"report_id": clean_id},
        {"$set": assessment_doc},
        upsert=True
    )

    # Record in report timeline & central audit log
    needs_summary = ", ".join([f"{n.requested_quantity} {n.unit} {n.resource_type.value}" for n in payload.needs[:3]])
    await record_timeline_event(
        db=db,
        report_id=clean_id,
        event_type=TimelineEventType.NEEDS_ASSESSED,
        details=f"Emergency needs assessed by {current_user.full_name}: {needs_summary}.",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
    )

    return NeedsAssessmentResponse(
        report_id=clean_id,
        needs=payload.needs,
        assessed_by=current_user.full_name,
        assessed_by_id=current_user.id,
        assessed_at=now,
        updated_at=now,
    )


@router.post("/reports/{report_id}/ai/needs-suggestion", response_model=AINeedsSuggestionResponse)
async def get_ai_needs_suggestion(
    report_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get advisory AI suggestions for emergency needs based on report metadata and description.
    Advisory only; never creates an automatic allocation.
    """
    clean_id = report_id.strip().upper()
    report = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report '{report_id}' not found.",
        )

    loc = report.get("location", {})
    loc_str = f"{loc.get('city', '')} {loc.get('zone_or_district', '')} {loc.get('address', '')}"

    suggestion_res = await generate_ai_needs_assessment(
        report_id=clean_id,
        emergency_type=report.get("emergency_type", "Other"),
        description=report.get("description", ""),
        location_summary=loc_str,
    )

    # Audit log
    now = datetime.now(timezone.utc)
    await db["audit_logs"].insert_one({
        "event_id": f"EVT-AI-{clean_id[-6:]}",
        "report_id": clean_id,
        "action": TimelineEventType.AI_NEEDS_SUGGESTION_GENERATED.value,
        "actor_id": current_user.id,
        "actor_name": current_user.full_name,
        "actor_role": current_user.role.value,
        "details": f"AI needs advisory recommendations generated for '{clean_id}' ({len(suggestion_res.suggestions)} suggestions).",
        "timestamp": now,
    })

    return suggestion_res


# --- Deterministic Resource Matching ---

@router.post("/reports/{report_id}/resource-matching", response_model=ResourceMatchingResponse)
async def run_resource_matching(
    report_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Execute deterministic resource matching engine matching report location & needs to live inventory.
    """
    clean_id = report_id.strip().upper()
    report = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report '{report_id}' not found.",
        )

    assessment = await db["needs_assessments"].find_one({"report_id": clean_id})
    if not assessment or not assessment.get("needs"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No needs assessment found for this report. Please assess needs first.",
        )

    needs_list = [EmergencyNeedItem(**n) for n in assessment["needs"]]
    matching_result = await match_resources_for_needs(
        db=db,
        report_id=clean_id,
        report_location=report.get("location", {}),
        needs=needs_list,
    )

    # Audit log
    now = datetime.now(timezone.utc)
    await db["audit_logs"].insert_one({
        "event_id": f"EVT-MCH-{clean_id[-6:]}",
        "report_id": clean_id,
        "action": TimelineEventType.RESOURCE_MATCHING_GENERATED.value,
        "actor_id": current_user.id,
        "actor_name": current_user.full_name,
        "actor_role": current_user.role.value,
        "details": f"Deterministic resource matching executed for '{clean_id}' by {current_user.full_name}.",
        "timestamp": now,
    })

    return matching_result


# --- Allocations ---

@router.get("/allocations", response_model=List[AllocationResponse])
async def list_all_allocations(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(get_current_user),
):
    """
    List resource allocations across all reports with optional status filter for Resource Managers and Officers.
    """
    query = {}
    if status and status.strip() and status.strip().upper() != "ALL":
        query["status"] = status.strip().upper()
    cursor = db["resource_allocations"].find(query).sort("created_at", -1).limit(limit)
    allocations = []
    async for doc in cursor:
        allocations.append(parse_allocation_doc(doc))
    return allocations


@router.get("/reports/{report_id}/allocations", response_model=List[AllocationResponse])
async def list_report_allocations(
    report_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    List all resource allocations for a report.
    """
    clean_id = report_id.strip().upper()
    cursor = db["resource_allocations"].find({"report_id": clean_id}).sort("created_at", -1)
    allocations = []
    async for doc in cursor:
        allocations.append(parse_allocation_doc(doc))
    return allocations


@router.post("/reports/{report_id}/allocations", response_model=AllocationResponse, status_code=status.HTTP_201_CREATED)
async def propose_allocation(
    report_id: str,
    payload: AllocationCreateRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Propose a resource allocation for a specific need item.
    """
    clean_id = report_id.strip().upper()
    report = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report '{report_id}' not found.",
        )

    res_doc = await db["resources"].find_one({"resource_id": payload.resource_id})
    if not res_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{payload.resource_id}' not found.",
        )

    if float(res_doc.get("quantity_available", 0.0)) < payload.requested_quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Requested allocation ({payload.requested_quantity}) exceeds available stock ({res_doc.get('quantity_available')}).",
        )

    alloc_id = generate_allocation_id()
    now = datetime.now(timezone.utc)

    alloc_doc = {
        "allocation_id": alloc_id,
        "report_id": clean_id,
        "need_id": payload.need_id,
        "resource_id": payload.resource_id,
        "resource_name": res_doc["name"],
        "resource_type": res_doc["resource_type"],
        "requested_quantity": float(payload.requested_quantity),
        "approved_quantity": 0.0,
        "unit": res_doc.get("unit", "units"),
        "status": AllocationStatus.PROPOSED.value,
        "proposed_by": current_user.full_name,
        "proposed_by_id": current_user.id,
        "approved_by": None,
        "approved_by_id": None,
        "notes": payload.notes.strip() if payload.notes else None,
        "created_at": now,
        "updated_at": now,
    }

    await db["resource_allocations"].insert_one(alloc_doc)

    await record_timeline_event(
        db=db,
        report_id=clean_id,
        event_type=TimelineEventType.ALLOCATION_PROPOSED,
        details=f"Allocation proposed for {payload.requested_quantity} {res_doc.get('unit')} of '{res_doc['name']}' by {current_user.full_name}.",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
    )

    return parse_allocation_doc(alloc_doc)


@router.post("/allocations/{allocation_id}/approve", response_model=AllocationResponse)
async def approve_allocation(
    allocation_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Approve proposed allocation with ATOMIC inventory decrement.
    Prevents race conditions and over-allocation.
    """
    clean_id = allocation_id.strip().upper()
    alloc_doc = await db["resource_allocations"].find_one({"allocation_id": clean_id})
    if not alloc_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation '{allocation_id}' not found.",
        )

    if alloc_doc.get("status") == AllocationStatus.APPROVED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Allocation has already been approved.",
        )

    qty_to_allocate = float(alloc_doc["requested_quantity"])
    res_id = alloc_doc["resource_id"]
    now = datetime.now(timezone.utc)

    # CRITICAL: Atomic inventory decrement in MongoDB
    # Only decrements if available stock is >= requested quantity
    res_update = await db["resources"].update_one(
        {
            "resource_id": res_id,
            "quantity_available": {"$gte": qty_to_allocate},
        },
        {
            "$inc": {"quantity_available": -qty_to_allocate},
            "$set": {"updated_at": now, "updated_by": current_user.id, "updated_by_name": current_user.full_name},
        }
    )

    if res_update.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient inventory available to approve allocation of {qty_to_allocate} units.",
        )

    # Update resource status if stock reaches 0
    updated_resource = await db["resources"].find_one({"resource_id": res_id})
    if updated_resource and float(updated_resource.get("quantity_available", 0.0)) == 0:
        await db["resources"].update_one(
            {"resource_id": res_id},
            {"$set": {"status": ResourceStatus.UNAVAILABLE.value}}
        )

    # Update allocation status to APPROVED
    await db["resource_allocations"].update_one(
        {"allocation_id": clean_id},
        {
            "$set": {
                "status": AllocationStatus.APPROVED.value,
                "approved_quantity": qty_to_allocate,
                "approved_by": current_user.full_name,
                "approved_by_id": current_user.id,
                "updated_at": now,
            }
        }
    )

    # Timeline event
    rep_id = alloc_doc["report_id"]
    await record_timeline_event(
        db=db,
        report_id=rep_id,
        event_type=TimelineEventType.ALLOCATION_APPROVED,
        details=f"Allocation approved: {qty_to_allocate} {alloc_doc.get('unit')} of '{alloc_doc.get('resource_name')}' allocated by {current_user.full_name}.",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
    )

    # Inventory update audit
    await db["audit_logs"].insert_one({
        "event_id": f"EVT-INV-{clean_id[-6:]}",
        "report_id": rep_id,
        "action": TimelineEventType.INVENTORY_UPDATED.value,
        "actor_id": current_user.id,
        "actor_name": current_user.full_name,
        "actor_role": current_user.role.value,
        "resource_id": res_id,
        "details": f"Inventory for '{res_id}' decremented by {qty_to_allocate} upon allocation approval.",
        "timestamp": now,
    })

    # Dispatch Phase 6 Monitoring Event
    try:
        from app.services.monitoring.monitoring_service import MonitoringService
        from app.models.enums import MonitoringEventType, EventSourceType
        
        # Get associated situation
        rep_doc = await db["citizen_reports"].find_one({"report_id": rep_id})
        sit_id = rep_doc.get("situation_id") if rep_doc else None

        prev_qty = float(res_doc.get("quantity_available", 0.0))
        new_qty = float(updated_resource.get("quantity_available", 0.0)) if updated_resource else max(0.0, prev_qty - qty_to_allocate)

        await MonitoringService.record_change_event(
            event_type=MonitoringEventType.RESOURCE_ALLOCATED,
            source_type=EventSourceType.RESOURCE_INVENTORY,
            source_id=res_id,
            previous_state={
                "quantity_available": prev_qty,
                "status": res_doc.get("status"),
            },
            new_state={
                "quantity_available": new_qty,
                "allocated_quantity": qty_to_allocate,
                "allocation_id": clean_id,
                "report_id": rep_id,
                "status": updated_resource.get("status") if updated_resource else res_doc.get("status"),
            },
            situation_id=sit_id,
            location=res_doc.get("location"),
            actor={
                "id": current_user.id,
                "full_name": current_user.full_name,
                "role": current_user.role.value,
            },
            db=db,
        )
    except Exception as mon_err:
        logger.warning(f"Monitoring notice on allocation approval {clean_id}: {mon_err}")

    updated_alloc = await db["resource_allocations"].find_one({"allocation_id": clean_id})
    return parse_allocation_doc(updated_alloc)


@router.post("/allocations/{allocation_id}/reject", response_model=AllocationResponse)
async def reject_allocation(
    allocation_id: str,
    payload: AllocationActionRequest = AllocationActionRequest(),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Reject proposed allocation.
    """
    clean_id = allocation_id.strip().upper()
    alloc_doc = await db["resource_allocations"].find_one({"allocation_id": clean_id})
    if not alloc_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation '{allocation_id}' not found.",
        )

    if alloc_doc.get("status") == AllocationStatus.APPROVED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reject already approved allocation. Use cancellation instead.",
        )

    now = datetime.now(timezone.utc)
    reason_str = f" Reason: {payload.reason}" if payload.reason else ""

    await db["resource_allocations"].update_one(
        {"allocation_id": clean_id},
        {
            "$set": {
                "status": AllocationStatus.REJECTED.value,
                "notes": (alloc_doc.get("notes") or "") + f" [Rejected: {payload.reason}]" if payload.reason else alloc_doc.get("notes"),
                "updated_at": now,
            }
        }
    )

    rep_id = alloc_doc["report_id"]
    await record_timeline_event(
        db=db,
        report_id=rep_id,
        event_type=TimelineEventType.ALLOCATION_REJECTED,
        details=f"Allocation '{clean_id}' rejected by {current_user.full_name}.{reason_str}",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
    )

    updated_alloc = await db["resource_allocations"].find_one({"allocation_id": clean_id})
    return parse_allocation_doc(updated_alloc)


@router.patch("/allocations/{allocation_id}/status", response_model=AllocationResponse)
async def update_allocation_status(
    allocation_id: str,
    status_to_set: AllocationStatus,
    payload: AllocationActionRequest = AllocationActionRequest(),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Update dispatch/completion/cancellation status of an allocation.
    If cancelled after approval, safely restores inventory stock.
    """
    clean_id = allocation_id.strip().upper()
    alloc_doc = await db["resource_allocations"].find_one({"allocation_id": clean_id})
    if not alloc_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation '{allocation_id}' not found.",
        )

    current_status = AllocationStatus(alloc_doc.get("status", AllocationStatus.PROPOSED.value))
    now = datetime.now(timezone.utc)

    # If cancelling an already approved allocation, restore stock
    if status_to_set == AllocationStatus.CANCELLED and current_status == AllocationStatus.APPROVED:
        approved_qty = float(alloc_doc.get("approved_quantity", 0.0))
        res_id = alloc_doc["resource_id"]
        if approved_qty > 0:
            await db["resources"].update_one(
                {"resource_id": res_id},
                {
                    "$inc": {"quantity_available": approved_qty},
                    "$set": {"status": ResourceStatus.AVAILABLE.value, "updated_at": now},
                }
            )

    await db["resource_allocations"].update_one(
        {"allocation_id": clean_id},
        {
            "$set": {
                "status": status_to_set.value,
                "updated_at": now,
            }
        }
    )

    rep_id = alloc_doc["report_id"]
    await record_timeline_event(
        db=db,
        report_id=rep_id,
        event_type=TimelineEventType.ALLOCATION_MODIFIED,
        details=f"Allocation '{clean_id}' transitioned to {status_to_set.value} by {current_user.full_name}.",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
    )

    updated_alloc = await db["resource_allocations"].find_one({"allocation_id": clean_id})
    return parse_allocation_doc(updated_alloc)
