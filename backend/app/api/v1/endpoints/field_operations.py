import logging
import math
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user, require_roles
from app.db.mongodb import get_database
from app.models.enums import (
    UserRole,
    ResponseTaskStatus,
    TaskType,
    SeverityLevel,
)
from app.models.task import (
    ResponseTask,
    FieldUpdateRecord,
    TaskAssignmentRequest,
    TaskStatusTransitionRequest,
    FieldUpdateCreateRequest,
    IncidentResolutionRequest,
    IncidentCloseRequest,
    OperationsOverviewResponse,
    PaginatedTasksResponse,
    IncidentResolutionSummary,
)
from app.models.user import UserResponse
from app.services.field_operations_service import FieldOperationsService

logger = logging.getLogger("resilience.api.field_operations")

router = APIRouter()


@router.get("/overview", response_model=OperationsOverviewResponse)
async def get_operations_overview(
    situation_id: Optional[str] = Query(None, description="Optional situation filter"),
    assigned_to_me: bool = Query(False, description="Filter only tasks assigned to the authenticated user"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> OperationsOverviewResponse:
    """
    Get aggregated real-time operational execution KPIs.
    """
    assigned_user_filter = current_user.id if assigned_to_me else None
    if current_user.role == UserRole.VOLUNTEER and not situation_id:
        assigned_user_filter = current_user.id

    return await FieldOperationsService.get_overview(
        situation_id=situation_id,
        assigned_to_user_id=assigned_user_filter,
        db=db,
    )


@router.get("/tasks", response_model=PaginatedTasksResponse)
async def list_tasks(
    situation_id: Optional[str] = Query(None, description="Filter by situation ID"),
    plan_id: Optional[str] = Query(None, description="Filter by response plan ID"),
    status: Optional[str] = Query(None, description="Filter by status (PENDING_APPROVAL, APPROVED, ASSIGNED, IN_PROGRESS, COMPLETED, BLOCKED, etc.)"),
    task_type: Optional[str] = Query(None, description="Filter by task type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    assigned_to_me: bool = Query(False, description="Filter only tasks assigned to the authenticated user"),
    search: Optional[str] = Query(None, description="Search query across task titles and descriptions"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> PaginatedTasksResponse:
    """
    List response tasks with filtering and pagination.
    Volunteers automatically scope to their assigned tasks or active incident tasks.
    """
    assigned_user_filter = current_user.id if assigned_to_me else None
    
    # If user is a volunteer and didn't specify assigned_to_me, default to their assignments unless they are querying
    if current_user.role == UserRole.VOLUNTEER and not assigned_to_me and not situation_id:
        assigned_user_filter = current_user.id

    return await FieldOperationsService.list_tasks(
        situation_id=situation_id,
        plan_id=plan_id,
        status=status,
        task_type=task_type,
        priority=priority,
        assigned_to_user_id=assigned_user_filter,
        search=search,
        page=page,
        limit=limit,
        db=db,
    )


@router.get("/tasks/{task_id}", response_model=ResponseTask)
async def get_task(
    task_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ResponseTask:
    """
    Fetch detailed response task with field update stream and assignments.
    """
    task = await FieldOperationsService.get_task(task_id=task_id, db=db)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Response task '{task_id}' not found.",
        )
    return task


@router.post("/tasks/{task_id}/approve", response_model=ResponseTask)
async def approve_task(
    task_id: str,
    current_user: UserResponse = Depends(require_roles([UserRole.EMERGENCY_OFFICER, UserRole.ADMIN])),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ResponseTask:
    """
    Officer approval of a pending response task.
    """
    try:
        actor_dict = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
        }
        return await FieldOperationsService.transition_task_status(
            task_id=task_id,
            new_status=ResponseTaskStatus.APPROVED,
            actor=actor_dict,
            db=db,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post("/tasks/{task_id}/assign", response_model=ResponseTask)
async def assign_task(
    task_id: str,
    assignment_req: TaskAssignmentRequest,
    current_user: UserResponse = Depends(require_roles([UserRole.EMERGENCY_OFFICER, UserRole.ADMIN])),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ResponseTask:
    """
    Assign or reassign volunteers, teams, or vehicles to a response task.
    Enforces vehicle availability and conflict prevention.
    """
    try:
        actor_dict = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
        }
        return await FieldOperationsService.assign_task(
            task_id=task_id,
            assignment=assignment_req,
            officer_actor=actor_dict,
            db=db,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post("/tasks/{task_id}/reassign", response_model=ResponseTask)
async def reassign_task(
    task_id: str,
    assignment_req: TaskAssignmentRequest,
    current_user: UserResponse = Depends(require_roles([UserRole.EMERGENCY_OFFICER, UserRole.ADMIN])),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ResponseTask:
    """
    Reassign volunteers or vehicles to an existing task.
    """
    return await assign_task(task_id=task_id, assignment_req=assignment_req, current_user=current_user, db=db)


@router.post("/tasks/{task_id}/accept", response_model=ResponseTask)
async def accept_task(
    task_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ResponseTask:
    """
    Assigned volunteer or officer accepts the response task assignment.
    """
    task = await FieldOperationsService.get_task(task_id=task_id, db=db)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")

    # IDOR Check: Volunteer can only accept tasks assigned to them
    if current_user.role == UserRole.VOLUNTEER and current_user.id not in task.assigned_volunteer_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only accept tasks explicitly assigned to you.",
        )

    try:
        actor_dict = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
        }
        return await FieldOperationsService.transition_task_status(
            task_id=task_id,
            new_status=ResponseTaskStatus.ACCEPTED,
            actor=actor_dict,
            db=db,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post("/tasks/{task_id}/start", response_model=ResponseTask)
async def start_task(
    task_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ResponseTask:
    """
    Transition task to IN_PROGRESS.
    """
    task = await FieldOperationsService.get_task(task_id=task_id, db=db)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")

    if current_user.role == UserRole.VOLUNTEER and current_user.id not in task.assigned_volunteer_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only start tasks explicitly assigned to you.",
        )

    try:
        actor_dict = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
        }
        return await FieldOperationsService.transition_task_status(
            task_id=task_id,
            new_status=ResponseTaskStatus.IN_PROGRESS,
            actor=actor_dict,
            db=db,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post("/tasks/{task_id}/complete", response_model=ResponseTask)
async def complete_task(
    task_id: str,
    req: TaskStatusTransitionRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ResponseTask:
    """
    Mark task as COMPLETED and atomically decrement consumed resources.
    """
    task = await FieldOperationsService.get_task(task_id=task_id, db=db)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")

    if current_user.role == UserRole.VOLUNTEER and current_user.id not in task.assigned_volunteer_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only complete tasks explicitly assigned to you.",
        )

    try:
        actor_dict = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
        }
        return await FieldOperationsService.transition_task_status(
            task_id=task_id,
            new_status=ResponseTaskStatus.COMPLETED,
            actor=actor_dict,
            notes=req.notes,
            completion_notes=req.completion_notes,
            consumed_resources=req.consumed_resources,
            db=db,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post("/tasks/{task_id}/block", response_model=ResponseTask)
async def block_task(
    task_id: str,
    req: TaskStatusTransitionRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ResponseTask:
    """
    Report task as BLOCKED. Automatically logs Live Monitoring event for dynamic impact analysis.
    """
    try:
        actor_dict = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
        }
        return await FieldOperationsService.transition_task_status(
            task_id=task_id,
            new_status=ResponseTaskStatus.BLOCKED,
            actor=actor_dict,
            reason=req.reason or req.notes,
            db=db,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post("/tasks/{task_id}/fail", response_model=ResponseTask)
async def fail_task(
    task_id: str,
    req: TaskStatusTransitionRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ResponseTask:
    """
    Report task as FAILED.
    """
    try:
        actor_dict = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
        }
        return await FieldOperationsService.transition_task_status(
            task_id=task_id,
            new_status=ResponseTaskStatus.FAILED,
            actor=actor_dict,
            reason=req.reason or req.notes,
            db=db,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post("/tasks/{task_id}/field-update", response_model=FieldUpdateRecord)
async def submit_field_update(
    task_id: str,
    req: FieldUpdateCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> FieldUpdateRecord:
    """
    Submit ground operational update (ARRIVED, TASK_STARTED, ROUTE_BLOCKED, etc.).
    """
    try:
        actor_dict = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
        }
        return await FieldOperationsService.record_field_update(
            task_id=task_id,
            update_req=req,
            actor=actor_dict,
            db=db,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.get("/tasks/{task_id}/timeline")
async def get_task_timeline(
    task_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> List[Dict[str, Any]]:
    """
    Get audit timeline and field update stream for a specific task.
    """
    task = await FieldOperationsService.get_task(task_id=task_id, db=db)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")

    events = await db["timeline_events"].find({
        "report_id": task.situation_id,
        "metadata.task_id": task_id.strip(),
    }).sort("timestamp", -1).to_list(100)

    # Convert _id to string
    for ev in events:
        if "_id" in ev:
            ev["_id"] = str(ev["_id"])
    return events


@router.post("/incidents/{situation_id}/resolve")
async def resolve_incident(
    situation_id: str,
    req: IncidentResolutionRequest,
    current_user: UserResponse = Depends(require_roles([UserRole.EMERGENCY_OFFICER, UserRole.ADMIN])),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    """
    Emergency Officer verifies operational completion and marks Situation as RESOLVED.
    Validates that critical tasks are completed or explicitly overridden.
    """
    try:
        actor_dict = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
        }
        return await FieldOperationsService.resolve_incident(
            situation_id=situation_id,
            officer_actor=actor_dict,
            req=req,
            db=db,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.post("/incidents/{situation_id}/close", response_model=IncidentResolutionSummary)
async def close_incident(
    situation_id: str,
    req: IncidentCloseRequest,
    current_user: UserResponse = Depends(require_roles([UserRole.EMERGENCY_OFFICER, UserRole.ADMIN])),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> IncidentResolutionSummary:
    """
    Final closure of an emergency incident. Compiles comprehensive post-incident summary from real DB records.
    """
    try:
        actor_dict = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
        }
        return await FieldOperationsService.close_incident(
            situation_id=situation_id,
            officer_actor=actor_dict,
            req=req,
            db=db,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.get("/incidents/{situation_id}/summary", response_model=IncidentResolutionSummary)
async def get_incident_summary(
    situation_id: str,
    current_user: UserResponse = Depends(require_roles([UserRole.EMERGENCY_OFFICER, UserRole.RESOURCE_MANAGER, UserRole.ADMIN])),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> IncidentResolutionSummary:
    """
    Fetch comprehensive post-incident summary aggregated from actual MongoDB records.
    """
    try:
        return await FieldOperationsService.get_incident_summary(situation_id=situation_id, db=db)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


# =====================================================================
# Phase C: Field Officer Live Verification & Incident Evolution Timeline
# =====================================================================

from app.models.field_verification import (
    FieldVerificationCreateRequest,
    FieldVerificationRecord,
    PaginatedFieldVerificationsResponse,
)
from app.models.incident_evolution import (
    IncidentEvolutionTimelineResponse,
)
from app.services.field_verification_service import FieldVerificationService
from app.services.incident_evolution_service import IncidentEvolutionService


@router.post("/verify", response_model=FieldVerificationRecord, status_code=status.HTTP_201_CREATED)
@router.post("/verifications", response_model=FieldVerificationRecord, status_code=status.HTTP_201_CREATED)
async def submit_field_verification(
    req: FieldVerificationCreateRequest,
    current_user: UserResponse = Depends(require_roles([UserRole.EMERGENCY_OFFICER, UserRole.VOLUNTEER, UserRole.ADMIN])),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> FieldVerificationRecord:
    """
    Submit ground-truth field verification for an incident or situation cluster.
    Enforces server-side RBAC, GPS spatial verification, and multi-source corroboration integration.
    """
    try:
        actor_dict = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
        }
        return await FieldVerificationService.verify_ground_truth(
            req=req,
            actor=actor_dict,
            db=db,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@router.get("/verifications", response_model=PaginatedFieldVerificationsResponse)
async def list_field_verifications(
    target_id: Optional[str] = Query(None, description="Filter by report or situation ID"),
    situation_id: Optional[str] = Query(None, description="Filter by situation ID"),
    responder_id: Optional[str] = Query(None, description="Filter by responder ID"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> PaginatedFieldVerificationsResponse:
    """
    List field verifications with filtering and pagination.
    """
    items, total = await FieldVerificationService.list_verifications(
        target_id=target_id,
        situation_id=situation_id,
        responder_id=responder_id,
        page=page,
        limit=limit,
        db=db,
    )
    total_pages = max(1, math.ceil(total / limit)) if total > 0 else 1
    return PaginatedFieldVerificationsResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get("/incidents/{situation_id}/evolution-timeline", response_model=IncidentEvolutionTimelineResponse)
async def get_incident_evolution_timeline(
    situation_id: str,
    order: str = Query("asc", description="Sort order: 'asc' (chronological) or 'desc' (reverse)"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> IncidentEvolutionTimelineResponse:
    """
    Fetch comprehensive chronological incident evolution timeline aggregated from genuine operational records.
    """
    return await IncidentEvolutionService.get_evolution_timeline(
        target_id=situation_id,
        db=db,
        order=order,
    )

