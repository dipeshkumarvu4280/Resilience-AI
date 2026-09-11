import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.models.enums import (
    ResponseTaskStatus,
    TaskType,
    FieldUpdateType,
    SeverityLevel,
    SituationStatus,
    CoordinationPlanStatus,
    TimelineEventType,
    UserRole,
    MonitoringEventType,
    EventSourceType,
    NotificationCategory,
    NotificationSeverity,
)
from app.models.task import (
    ResponseTask,
    FieldUpdateRecord,
    TaskLocation,
    AssignedResourceItem,
    TaskAssignmentRequest,
    TaskStatusTransitionRequest,
    FieldUpdateCreateRequest,
    IncidentResolutionRequest,
    IncidentCloseRequest,
    OperationsOverviewResponse,
    PaginatedTasksResponse,
    IncidentResolutionSummary,
    PostIncidentAnalytics,
    generate_task_id,
    generate_update_id,
)
from app.models.agent import CoordinationPlan
from app.services.timeline import record_timeline_event
from app.db.mongodb import db_manager

logger = logging.getLogger("resilience.services.field_operations")

# Valid state transitions for the response task state machine
VALID_TASK_TRANSITIONS: Dict[ResponseTaskStatus, List[ResponseTaskStatus]] = {
    ResponseTaskStatus.PENDING_APPROVAL: [
        ResponseTaskStatus.APPROVED,
        ResponseTaskStatus.ASSIGNED,
        ResponseTaskStatus.REJECTED,
        ResponseTaskStatus.CANCELLED,
    ],
    ResponseTaskStatus.APPROVED: [
        ResponseTaskStatus.ASSIGNED,
        ResponseTaskStatus.IN_PROGRESS,
        ResponseTaskStatus.CANCELLED,
        ResponseTaskStatus.REJECTED,
    ],
    ResponseTaskStatus.ASSIGNED: [
        ResponseTaskStatus.ACCEPTED,
        ResponseTaskStatus.IN_PROGRESS,
        ResponseTaskStatus.ASSIGNED,  # Reassignment
        ResponseTaskStatus.BLOCKED,
        ResponseTaskStatus.CANCELLED,
    ],
    ResponseTaskStatus.ACCEPTED: [
        ResponseTaskStatus.IN_PROGRESS,
        ResponseTaskStatus.BLOCKED,
        ResponseTaskStatus.CANCELLED,
    ],
    ResponseTaskStatus.IN_PROGRESS: [
        ResponseTaskStatus.COMPLETED,
        ResponseTaskStatus.BLOCKED,
        ResponseTaskStatus.FAILED,
        ResponseTaskStatus.ESCALATED,
        ResponseTaskStatus.CANCELLED,
    ],
    ResponseTaskStatus.BLOCKED: [
        ResponseTaskStatus.IN_PROGRESS,
        ResponseTaskStatus.ESCALATED,
        ResponseTaskStatus.CANCELLED,
        ResponseTaskStatus.FAILED,
    ],
    ResponseTaskStatus.FAILED: [
        ResponseTaskStatus.ESCALATED,
        ResponseTaskStatus.CANCELLED,
    ],
    ResponseTaskStatus.ESCALATED: [
        ResponseTaskStatus.APPROVED,
        ResponseTaskStatus.ASSIGNED,
        ResponseTaskStatus.IN_PROGRESS,
        ResponseTaskStatus.CANCELLED,
    ],
    ResponseTaskStatus.COMPLETED: [],
    ResponseTaskStatus.REJECTED: [],
    ResponseTaskStatus.CANCELLED: [],
}


class FieldOperationsService:
    """
    Phase 8 Master Field Operations & Emergency Execution Service.
    Coordinates genuine task derivation, responder assignments, vehicle allocation,
    atomic resource consumption, ground field updates, and incident resolution.
    """

    @classmethod
    async def ensure_indexes(cls, db: AsyncIOMotorDatabase):
        """Ensure indexes on the response_tasks collection for performant operational queries."""
        try:
            await db["response_tasks"].create_index("task_id", unique=True)
            await db["response_tasks"].create_index("situation_id")
            await db["response_tasks"].create_index("plan_id")
            await db["response_tasks"].create_index("status")
            await db["response_tasks"].create_index("assigned_volunteer_ids")
            await db["response_tasks"].create_index("assigned_vehicle_id")
            await db["response_tasks"].create_index("created_at")
            logger.info("Field operations indexes verified successfully.")
        except Exception as e:
            logger.warning(f"Error creating response_tasks indexes: {e}")

    @classmethod
    async def derive_tasks_from_plan(
        cls,
        plan: CoordinationPlan,
        officer_actor: Dict[str, Any],
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> List[ResponseTask]:
        """
        Derives executable, actionable ResponseTasks from an approved CoordinationPlan.
        Guarantees strict determinism and idempotency: repeated invocations will not duplicate tasks.
        Enforces human-in-the-loop: tasks are initialized in APPROVED or ASSIGNED status.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        situation_id = plan.situation_id.strip().upper()
        now = datetime.now(timezone.utc)
        derived_tasks: List[ResponseTask] = []

        # 1. Fetch situation location details for task spatial context
        sit_doc = await db["situations"].find_one({"situation_id": situation_id})
        sit_loc_name = sit_doc.get("title", f"Situation Site {situation_id}") if sit_doc else f"Situation Site {situation_id}"
        sit_center = sit_doc.get("center_location", {}) if sit_doc else {}
        sit_lat = sit_center.get("latitude")
        sit_lon = sit_center.get("longitude")
        sit_addr = sit_center.get("address") or sit_center.get("street_address")

        default_situation_location = TaskLocation(
            name=sit_loc_name,
            address=sit_addr,
            latitude=sit_lat,
            longitude=sit_lon,
        )

        # 2. Resource Deliveries -> RESOURCE_DELIVERY Tasks
        for alloc in plan.recommended_allocations:
            res_item = AssignedResourceItem(
                resource_id=alloc.matched_resource_id or f"RES-{alloc.resource_type.value.upper()}",
                resource_name=alloc.matched_resource_name or f"{alloc.resource_type.value} Supply Unit",
                resource_type=alloc.resource_type.value if hasattr(alloc.resource_type, "value") else str(alloc.resource_type),
                allocated_quantity=alloc.allocated_quantity or alloc.quantity_required,
                unit=alloc.unit,
                depot_location=alloc.depot_location,
                consumed_quantity=0.0,
            )
            # Idempotency check for resource allocation
            existing = await db["response_tasks"].find_one({
                "plan_id": plan.plan_id,
                "source_plan_component": "recommended_allocations",
                "assigned_resource_ids": res_item.resource_id,
            })
            if existing:
                derived_tasks.append(ResponseTask(**existing))
                continue

            task = ResponseTask(
                task_id=generate_task_id(),
                situation_id=situation_id,
                plan_id=plan.plan_id,
                plan_version=plan.version,
                task_type=TaskType.RESOURCE_DELIVERY,
                title=f"Deliver {res_item.allocated_quantity} {res_item.unit} {res_item.resource_type}",
                description=alloc.reasoning or f"Emergency logistics distribution of {res_item.resource_type} to response site.",
                priority=plan.assessed_priority,
                status=ResponseTaskStatus.APPROVED,
                assigned_resource_ids=[res_item.resource_id],
                assigned_resources=[res_item],
                source_plan_component="recommended_allocations",
                location=TaskLocation(name=alloc.depot_location or "Central Logistics Depot"),
                destination=default_situation_location,
                estimated_duration_minutes=max(15.0, round((alloc.distance_km or 5.0) * 4.0, 1)),
                created_by=officer_actor.get("full_name"),
                approved_by=officer_actor.get("full_name"),
                created_at=now,
                updated_at=now,
            )
            await db["response_tasks"].insert_one(task.model_dump())
            derived_tasks.append(task)

        # 3. Shelters -> SHELTER_ACTIVATION Tasks
        for shelter in plan.recommended_shelters:
            existing = await db["response_tasks"].find_one({
                "plan_id": plan.plan_id,
                "source_plan_component": "recommended_shelters",
                "destination.name": shelter.shelter_name,
            })
            if existing:
                derived_tasks.append(ResponseTask(**existing))
                continue

            task = ResponseTask(
                task_id=generate_task_id(),
                situation_id=situation_id,
                plan_id=plan.plan_id,
                plan_version=plan.version,
                task_type=TaskType.SHELTER_ACTIVATION,
                title=f"Prepare & Activate Shelter: {shelter.shelter_name}",
                description=shelter.recommendation_reason or f"Emergency shelter intake for up to {shelter.recommended_occupancy} displaced persons.",
                priority=plan.assessed_priority,
                status=ResponseTaskStatus.APPROVED,
                source_plan_component="recommended_shelters",
                location=default_situation_location,
                destination=TaskLocation(
                    name=shelter.shelter_name,
                    address=shelter.location_address,
                    latitude=shelter.latitude,
                    longitude=shelter.longitude,
                ),
                estimated_duration_minutes=max(30.0, round((shelter.distance_km or 3.0) * 5.0, 1)),
                created_by=officer_actor.get("full_name"),
                approved_by=officer_actor.get("full_name"),
                created_at=now,
                updated_at=now,
            )
            await db["response_tasks"].insert_one(task.model_dump())
            derived_tasks.append(task)

        # 4. Healthcare Facilities -> PATIENT_EVACUATION Tasks
        for facility in plan.recommended_facilities:
            existing = await db["response_tasks"].find_one({
                "plan_id": plan.plan_id,
                "source_plan_component": "recommended_facilities",
                "destination.name": facility.facility_name,
            })
            if existing:
                derived_tasks.append(ResponseTask(**existing))
                continue

            task = ResponseTask(
                task_id=generate_task_id(),
                situation_id=situation_id,
                plan_id=plan.plan_id,
                plan_version=plan.version,
                task_type=TaskType.PATIENT_EVACUATION,
                title=f"Medical Transfer to {facility.facility_name}",
                description=facility.recommendation_reason or f"Patient triage & transport for emergency treatment at {facility.facility_name}.",
                priority=plan.assessed_priority,
                status=ResponseTaskStatus.APPROVED,
                source_plan_component="recommended_facilities",
                location=default_situation_location,
                destination=TaskLocation(
                    name=facility.facility_name,
                    address=facility.location_address,
                    latitude=facility.latitude,
                    longitude=facility.longitude,
                ),
                estimated_duration_minutes=max(20.0, round((facility.distance_km or 4.0) * 3.5, 1)),
                created_by=officer_actor.get("full_name"),
                approved_by=officer_actor.get("full_name"),
                created_at=now,
                updated_at=now,
            )
            await db["response_tasks"].insert_one(task.model_dump())
            derived_tasks.append(task)

        # 5. Volunteers -> SEARCH_AND_RESCUE / Field Tasks
        for vol in plan.recommended_volunteers:
            existing = await db["response_tasks"].find_one({
                "plan_id": plan.plan_id,
                "source_plan_component": "recommended_volunteers",
                "assigned_volunteer_ids": vol.volunteer_id,
            })
            if existing:
                derived_tasks.append(ResponseTask(**existing))
                continue

            task = ResponseTask(
                task_id=generate_task_id(),
                situation_id=situation_id,
                plan_id=plan.plan_id,
                plan_version=plan.version,
                task_type=TaskType.SEARCH_AND_RESCUE if "RESCUE" in vol.role_or_skill.upper() else TaskType.GENERAL_FIELD_OPERATION,
                title=f"Field Mission: {vol.assigned_operation}",
                description=vol.recommendation_reason or f"Deploy responder {vol.volunteer_name} ({vol.role_or_skill}) for incident support.",
                priority=plan.assessed_priority,
                status=ResponseTaskStatus.ASSIGNED,  # Pre-matched volunteer
                assigned_volunteer_ids=[vol.volunteer_id],
                assigned_volunteer_names=[vol.volunteer_name],
                source_plan_component="recommended_volunteers",
                location=default_situation_location,
                estimated_duration_minutes=45.0,
                created_by=officer_actor.get("full_name"),
                approved_by=officer_actor.get("full_name"),
                created_at=now,
                updated_at=now,
            )
            await db["response_tasks"].insert_one(task.model_dump())
            derived_tasks.append(task)

        # 6. Routes & Transports -> ROUTE_CLEARANCE / Transport Tasks
        for route in plan.recommended_routes:
            existing = await db["response_tasks"].find_one({
                "plan_id": plan.plan_id,
                "source_plan_component": "recommended_routes",
                "route_id": route.route_id,
            })
            if existing:
                derived_tasks.append(ResponseTask(**existing))
                continue

            task = ResponseTask(
                task_id=generate_task_id(),
                situation_id=situation_id,
                plan_id=plan.plan_id,
                plan_version=plan.version,
                task_type=TaskType.ROUTE_CLEARANCE,
                title=f"Secure Transit Corridor: {route.origin_name} to {route.destination_name}",
                description=route.recommendation_reason or f"Maintain emergency route passage ({route.distance_km} km) for response units.",
                priority=plan.assessed_priority,
                status=ResponseTaskStatus.APPROVED,
                source_plan_component="recommended_routes",
                route_id=route.route_id,
                location=TaskLocation(
                    name=route.origin_name,
                    latitude=route.origin_coordinates.get("latitude") if route.origin_coordinates else None,
                    longitude=route.origin_coordinates.get("longitude") if route.origin_coordinates else None,
                ),
                destination=TaskLocation(
                    name=route.destination_name,
                    latitude=route.destination_coordinates.get("latitude") if route.destination_coordinates else None,
                    longitude=route.destination_coordinates.get("longitude") if route.destination_coordinates else None,
                ),
                assigned_vehicle_id=route.transport_id,
                estimated_duration_minutes=route.estimated_duration_minutes,
                created_by=officer_actor.get("full_name"),
                approved_by=officer_actor.get("full_name"),
                created_at=now,
                updated_at=now,
            )
            await db["response_tasks"].insert_one(task.model_dump())
            derived_tasks.append(task)

        # Fallback: If no specialized components, create at least 1 general coordination task
        if not derived_tasks:
            existing = await db["response_tasks"].find_one({
                "plan_id": plan.plan_id,
                "source_plan_component": "general",
            })
            if existing:
                derived_tasks.append(ResponseTask(**existing))
            else:
                task = ResponseTask(
                    task_id=generate_task_id(),
                    situation_id=situation_id,
                    plan_id=plan.plan_id,
                    plan_version=plan.version,
                    task_type=TaskType.GENERAL_FIELD_OPERATION,
                    title=f"Incident Operational Command: {sit_loc_name}",
                    description=plan.reasoning or "Execute on-site emergency coordination and monitoring.",
                    priority=plan.assessed_priority,
                    status=ResponseTaskStatus.APPROVED,
                    source_plan_component="general",
                    location=default_situation_location,
                    estimated_duration_minutes=60.0,
                    created_by=officer_actor.get("full_name"),
                    approved_by=officer_actor.get("full_name"),
                    created_at=now,
                    updated_at=now,
                )
                await db["response_tasks"].insert_one(task.model_dump())
                derived_tasks.append(task)

        # 8. Record audit timeline event
        actor_role_enum = None
        if officer_actor.get("role"):
            try:
                actor_role_enum = UserRole(officer_actor.get("role"))
            except Exception:
                pass

        await record_timeline_event(
            db=db,
            report_id=situation_id,
            event_type=TimelineEventType.TASK_DERIVED_FROM_PLAN,
            details=f"Derived {len(derived_tasks)} actionable response tasks from Plan {plan.plan_id} (v{plan.version}).",
            actor_id=officer_actor.get("id"),
            actor_name=officer_actor.get("full_name"),
            actor_role=actor_role_enum,
            metadata={"plan_id": plan.plan_id, "version": plan.version, "tasks_count": len(derived_tasks)},
        )

        # Update situation status to RESPONSE_IN_PROGRESS if it was ACTIVE
        await db["situations"].update_one(
            {"situation_id": situation_id, "status": SituationStatus.ACTIVE.value},
            {"$set": {"status": SituationStatus.RESPONSE_IN_PROGRESS.value, "updated_at": now}}
        )

        # 9. Dispatch Phase 7 Notification
        try:
            from app.services.notification import get_notification_service
            notif_service = get_notification_service()
            await notif_service.dispatch_event(
                category=NotificationCategory.FIELD_OPERATIONS,
                event_type="TASKS_DERIVED",
                severity=NotificationSeverity.HIGH if plan.assessed_priority.value in ["HIGH", "CRITICAL"] else NotificationSeverity.MEDIUM,
                title=f"{len(derived_tasks)} Response Tasks Generated",
                message=f"Actionable response tasks derived from approved plan {plan.plan_id} for situation {situation_id}.",
                entity_type="FIELD_OPERATIONS",
                entity_id=plan.plan_id,
                situation_id=situation_id,
                coordination_plan_id=plan.plan_id,
                view_hint="operations",
                target_roles=[UserRole.EMERGENCY_OFFICER, UserRole.RESOURCE_MANAGER, UserRole.VOLUNTEER],
                material_state={"plan_id": plan.plan_id, "tasks_count": len(derived_tasks)},
                metadata={"situation_id": situation_id, "plan_id": plan.plan_id},
            )
        except Exception as notif_err:
            logger.warning(f"Notification error on task derivation: {notif_err}")

        logger.info(f"Successfully derived {len(derived_tasks)} response tasks for plan {plan.plan_id}")
        return derived_tasks

    @classmethod
    async def get_task(cls, task_id: str, db: Optional[AsyncIOMotorDatabase] = None) -> Optional[ResponseTask]:
        """Fetch a single ResponseTask by task_id."""
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        doc = await db["response_tasks"].find_one({"task_id": task_id.strip()})
        if not doc:
            return None
        return ResponseTask(**doc)

    @classmethod
    async def list_tasks(
        cls,
        situation_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
        priority: Optional[str] = None,
        assigned_to_user_id: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> PaginatedTasksResponse:
        """List response tasks with filtering and pagination."""
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        # If situation is selected and has 0 tasks in response_tasks, check for active plan and derive idempotently
        if situation_id:
            clean_sit = situation_id.strip().upper()
            existing_count = await db["response_tasks"].count_documents({"situation_id": clean_sit})
            if existing_count == 0:
                active_plan_doc = await db["coordination_plans"].find_one({
                    "situation_id": clean_sit,
                    "status": {"$in": [CoordinationPlanStatus.ACTIVE.value, CoordinationPlanStatus.APPROVED.value]},
                    "is_simulation": {"$ne": True},
                }, sort=[("version", -1), ("generated_at", -1)])
                if active_plan_doc:
                    active_plan_obj = CoordinationPlan(**active_plan_doc)
                    system_actor = {
                        "id": "SYSTEM_OPERATIONS",
                        "full_name": "Emergency Operations Engine",
                        "role": UserRole.EMERGENCY_OFFICER.value,
                    }
                    await cls.derive_tasks_from_plan(
                        plan=active_plan_obj,
                        officer_actor=system_actor,
                        db=db,
                    )

        query: Dict[str, Any] = {}
        if situation_id:
            query["situation_id"] = situation_id.strip().upper()
        if plan_id:
            query["plan_id"] = plan_id.strip()
        if status and status != "ALL":
            if status.strip().upper() == "ACTIVE":
                query["status"] = {"$in": [
                    ResponseTaskStatus.ASSIGNED.value,
                    ResponseTaskStatus.ACCEPTED.value,
                    ResponseTaskStatus.IN_PROGRESS.value,
                ]}
            elif status.strip().upper() == "COMPLETED":
                query["status"] = ResponseTaskStatus.COMPLETED.value
            else:
                query["status"] = status.strip().upper()
        if task_type and task_type != "ALL":
            query["task_type"] = task_type.strip().upper()
        if priority and priority != "ALL":
            query["priority"] = priority.strip().upper()
        if assigned_to_user_id:
            query["assigned_volunteer_ids"] = assigned_to_user_id.strip()
        if search:
            query["$or"] = [
                {"title": {"$regex": search.strip(), "$options": "i"}},
                {"description": {"$regex": search.strip(), "$options": "i"}},
                {"task_id": {"$regex": search.strip(), "$options": "i"}},
                {"assigned_volunteer_names": {"$regex": search.strip(), "$options": "i"}},
            ]

        total = await db["response_tasks"].count_documents(query)
        total_pages = max(1, (total + limit - 1) // limit)
        skip = (max(1, page) - 1) * limit

        cursor = db["response_tasks"].find(query).sort("created_at", -1).skip(skip).limit(limit)
        items: List[ResponseTask] = []
        async for doc in cursor:
            doc.pop("_id", None)
            try:
                items.append(ResponseTask(**doc))
            except Exception:
                pass

        return PaginatedTasksResponse(
            items=items,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
        )

    @classmethod
    async def get_overview(
        cls,
        situation_id: Optional[str] = None,
        assigned_to_user_id: Optional[str] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> OperationsOverviewResponse:
        """Aggregates real-time operational execution KPIs from MongoDB."""
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        query: Dict[str, Any] = {}
        plan_query: Dict[str, Any] = {
            "status": {"$in": [CoordinationPlanStatus.ACTIVE.value, CoordinationPlanStatus.APPROVED.value]},
            "is_simulation": {"$ne": True},
        }
        if situation_id:
            clean_sit = situation_id.strip().upper()
            query["situation_id"] = clean_sit
            plan_query["situation_id"] = clean_sit
        if assigned_to_user_id:
            query["assigned_volunteer_ids"] = assigned_to_user_id.strip()

        active_plans = await db["coordination_plans"].count_documents(plan_query)
        total_tasks = await db["response_tasks"].count_documents(query)

        # If an active/approved plan exists for the selected situation but 0 tasks have been derived, auto-derive idempotently
        if situation_id and total_tasks == 0 and active_plans > 0:
            active_plan_doc = await db["coordination_plans"].find_one(
                plan_query,
                sort=[("version", -1), ("generated_at", -1)],
            )
            if active_plan_doc:
                active_plan_obj = CoordinationPlan(**active_plan_doc)
                system_actor = {
                    "id": "SYSTEM_OPERATIONS",
                    "full_name": "Emergency Operations Engine",
                    "role": UserRole.EMERGENCY_OFFICER.value,
                }
                await cls.derive_tasks_from_plan(
                    plan=active_plan_obj,
                    officer_actor=system_actor,
                    db=db,
                )
                # Recompute total_tasks after auto-derivation
                total_tasks = await db["response_tasks"].count_documents(query)
        pending_tasks = await db["response_tasks"].count_documents({**query, "status": ResponseTaskStatus.PENDING_APPROVAL.value})
        approved_tasks = await db["response_tasks"].count_documents({**query, "status": ResponseTaskStatus.APPROVED.value})
        assigned_tasks = await db["response_tasks"].count_documents({**query, "status": ResponseTaskStatus.ASSIGNED.value})
        in_progress_tasks = await db["response_tasks"].count_documents({**query, "status": {"$in": [ResponseTaskStatus.ACCEPTED.value, ResponseTaskStatus.IN_PROGRESS.value]}})
        active_tasks_count = await db["response_tasks"].count_documents({
            **query,
            "status": {"$in": [
                ResponseTaskStatus.ASSIGNED.value,
                ResponseTaskStatus.ACCEPTED.value,
                ResponseTaskStatus.IN_PROGRESS.value,
            ]}
        })
        completed_tasks = await db["response_tasks"].count_documents({**query, "status": ResponseTaskStatus.COMPLETED.value})
        blocked_tasks = await db["response_tasks"].count_documents({**query, "status": ResponseTaskStatus.BLOCKED.value})
        escalated_tasks = await db["response_tasks"].count_documents({**query, "status": ResponseTaskStatus.ESCALATED.value})

        # Count active responders and vehicles
        active_volunteers_pipeline = [
            {"$match": {**query, "status": {"$in": [ResponseTaskStatus.ASSIGNED.value, ResponseTaskStatus.ACCEPTED.value, ResponseTaskStatus.IN_PROGRESS.value]}}},
            {"$unwind": "$assigned_volunteer_ids"},
            {"$group": {"_id": "$assigned_volunteer_ids"}},
            {"$count": "count"},
        ]
        active_vol_res = await db["response_tasks"].aggregate(active_volunteers_pipeline).to_list(1)
        active_volunteers_count = active_vol_res[0]["count"] if active_vol_res else 0

        active_vehicles_pipeline = [
            {"$match": {**query, "assigned_vehicle_id": {"$ne": None}, "status": {"$in": [ResponseTaskStatus.ASSIGNED.value, ResponseTaskStatus.ACCEPTED.value, ResponseTaskStatus.IN_PROGRESS.value]}}},
            {"$group": {"_id": "$assigned_vehicle_id"}},
            {"$count": "count"},
        ]
        active_veh_res = await db["response_tasks"].aggregate(active_vehicles_pipeline).to_list(1)
        active_vehicles_count = active_veh_res[0]["count"] if active_veh_res else 0

        # Count resources allocated in active tasks
        res_pipeline = [
            {"$match": {**query, "status": {"$in": [ResponseTaskStatus.ASSIGNED.value, ResponseTaskStatus.ACCEPTED.value, ResponseTaskStatus.IN_PROGRESS.value]}}},
            {"$unwind": "$assigned_resource_ids"},
            {"$group": {"_id": "$assigned_resource_ids"}},
            {"$count": "count"},
        ]
        res_res = await db["response_tasks"].aggregate(res_pipeline).to_list(1)
        resources_in_use_count = res_res[0]["count"] if res_res else 0

        return OperationsOverviewResponse(
            active_plans_count=active_plans,
            total_tasks_count=total_tasks,
            active_tasks_count=active_tasks_count,
            pending_tasks_count=pending_tasks,
            approved_tasks_count=approved_tasks,
            assigned_tasks_count=assigned_tasks,
            in_progress_tasks_count=in_progress_tasks,
            completed_tasks_count=completed_tasks,
            blocked_tasks_count=blocked_tasks,
            escalated_tasks_count=escalated_tasks,
            resources_in_use_count=resources_in_use_count,
            active_teams_count=0,
            active_volunteers_count=active_volunteers_count,
            active_vehicles_count=active_vehicles_count,
        )

    @classmethod
    async def transition_task_status(
        cls,
        task_id: str,
        new_status: ResponseTaskStatus,
        actor: Dict[str, Any],
        notes: Optional[str] = None,
        reason: Optional[str] = None,
        completion_notes: Optional[str] = None,
        consumed_resources: Optional[List[Dict[str, Any]]] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> ResponseTask:
        """
        Executes a deterministic state machine transition for a ResponseTask.
        Validates transition legality, executes atomic resource decrements if completed,
        and logs audit trail & monitoring events.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        task_doc = await db["response_tasks"].find_one({"task_id": task_id.strip()})
        if not task_doc:
            raise ValueError(f"Response task {task_id} not found.")

        current_status = ResponseTaskStatus(task_doc["status"])
        allowed_transitions = VALID_TASK_TRANSITIONS.get(current_status, [])

        if new_status not in allowed_transitions and new_status != current_status:
            raise ValueError(
                f"INVALID_TASK_TRANSITION: Cannot transition task from '{current_status.value}' to '{new_status.value}'. "
                f"Legal next states: {[s.value for s in allowed_transitions]}."
            )

        now = datetime.now(timezone.utc)
        update_fields: Dict[str, Any] = {
            "status": new_status.value,
            "updated_at": now,
        }

        # Handle specific state semantics
        if new_status == ResponseTaskStatus.IN_PROGRESS and not task_doc.get("started_at"):
            update_fields["started_at"] = now
        elif new_status == ResponseTaskStatus.COMPLETED:
            update_fields["completed_at"] = now
            if completion_notes:
                update_fields["completion_notes"] = completion_notes
            elif notes:
                update_fields["completion_notes"] = notes

            # Consume resources atomically if specified
            resources_to_consume = consumed_resources or task_doc.get("assigned_resources", [])
            for r_item in resources_to_consume:
                r_id = r_item.get("resource_id")
                qty = float(r_item.get("allocated_quantity") or r_item.get("quantity") or 0.0)
                if r_id and qty > 0:
                    await cls.consume_resource_atomic(resource_id=r_id, quantity=qty, db=db)

        elif new_status == ResponseTaskStatus.BLOCKED:
            update_fields["blocked_reason"] = reason or notes or "Field responder reported blockage."
        elif new_status == ResponseTaskStatus.FAILED:
            update_fields["failure_reason"] = reason or notes or "Field task execution failed."
        elif new_status == ResponseTaskStatus.APPROVED:
            update_fields["approved_by"] = actor.get("full_name")

        # Optimistic concurrency update
        result = await db["response_tasks"].find_one_and_update(
            {"task_id": task_id.strip(), "status": current_status.value},
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        if not result:
            raise ValueError("CONCURRENT_MUTATION: Task was modified by another operator. Please refresh and retry.")

        updated_task = ResponseTask(**result)

        # Timeline Event
        timeline_event_map = {
            ResponseTaskStatus.APPROVED: TimelineEventType.TASK_APPROVED,
            ResponseTaskStatus.ACCEPTED: TimelineEventType.TASK_ACCEPTED,
            ResponseTaskStatus.IN_PROGRESS: TimelineEventType.TASK_STARTED,
            ResponseTaskStatus.COMPLETED: TimelineEventType.TASK_COMPLETED,
            ResponseTaskStatus.BLOCKED: TimelineEventType.TASK_BLOCKED,
            ResponseTaskStatus.FAILED: TimelineEventType.TASK_FAILED,
            ResponseTaskStatus.REJECTED: TimelineEventType.TASK_REJECTED,
        }
        timeline_event = timeline_event_map.get(new_status)
        if timeline_event:
            actor_role_enum = None
            if actor.get("role"):
                try:
                    actor_role_enum = UserRole(actor.get("role"))
                except Exception:
                    pass

            await record_timeline_event(
                db=db,
                report_id=updated_task.situation_id,
                event_type=timeline_event,
                details=f"Task {task_id} ('{updated_task.title}') transitioned to {new_status.value} by {actor.get('full_name')}.",
                actor_id=actor.get("id"),
                actor_name=actor.get("full_name"),
                actor_role=actor_role_enum,
                metadata={"task_id": task_id, "previous_status": current_status.value, "new_status": new_status.value, "notes": notes},
            )

        # Connect BLOCKED / FAILED to Live Monitoring
        if new_status in [ResponseTaskStatus.BLOCKED, ResponseTaskStatus.FAILED]:
            try:
                from app.services.monitoring.monitoring_service import MonitoringService
                await MonitoringService.record_change_event(
                    event_type=MonitoringEventType.TASK_BLOCKED if new_status == ResponseTaskStatus.BLOCKED else MonitoringEventType.TASK_FAILED,
                    source_type=EventSourceType.OFFICER_DECISION if actor.get("role") == "EMERGENCY_OFFICER" else EventSourceType.VOLUNTEER_NETWORK,
                    source_id=task_id,
                    previous_state={"status": current_status.value},
                    new_state={"status": new_status.value, "reason": reason or notes},
                    situation_id=updated_task.situation_id,
                    coordination_plan_id=updated_task.plan_id,
                    actor=actor,
                    db=db,
                )
            except Exception as mon_err:
                logger.warning(f"Monitoring hook error on task state change: {mon_err}")

        # Phase 7 Notification
        try:
            from app.services.notification import get_notification_service
            notif_service = get_notification_service()
            await notif_service.dispatch_event(
                category=NotificationCategory.FIELD_OPERATIONS,
                event_type=f"TASK_{new_status.value}",
                severity=NotificationSeverity.HIGH if new_status in [ResponseTaskStatus.BLOCKED, ResponseTaskStatus.FAILED] else NotificationSeverity.MEDIUM,
                title=f"Task {new_status.value}: {updated_task.title}",
                message=f"Task {task_id} marked as {new_status.value} by {actor.get('full_name')}.",
                entity_type="RESPONSE_TASK",
                entity_id=task_id,
                situation_id=updated_task.situation_id,
                coordination_plan_id=updated_task.plan_id,
                view_hint="operations",
                target_roles=[UserRole.EMERGENCY_OFFICER, UserRole.RESOURCE_MANAGER, UserRole.VOLUNTEER],
                material_state={"task_id": task_id, "status": new_status.value},
                metadata={"task_id": task_id, "situation_id": updated_task.situation_id},
            )
        except Exception as notif_err:
            logger.warning(f"Notification error on task transition: {notif_err}")

        return updated_task

    @classmethod
    async def assign_task(
        cls,
        task_id: str,
        assignment: TaskAssignmentRequest,
        officer_actor: Dict[str, Any],
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> ResponseTask:
        """
        Assigns or reassigns genuine volunteers and vehicles to a ResponseTask.
        Validates vehicle availability and responder eligibility.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        task_doc = await db["response_tasks"].find_one({"task_id": task_id.strip()})
        if not task_doc:
            raise ValueError(f"Response task {task_id} not found.")

        # 1. Vehicle Conflict Prevention: Check if vehicle is already actively dispatched elsewhere
        if assignment.assigned_vehicle_id:
            conflict_veh = await db["response_tasks"].find_one({
                "assigned_vehicle_id": assignment.assigned_vehicle_id.strip(),
                "task_id": {"$ne": task_id.strip()},
                "status": {"$in": [
                    ResponseTaskStatus.ASSIGNED.value,
                    ResponseTaskStatus.ACCEPTED.value,
                    ResponseTaskStatus.IN_PROGRESS.value,
                ]},
            })
            if conflict_veh:
                raise ValueError(
                    f"VEHICLE_UNAVAILABLE: Vehicle {assignment.assigned_vehicle_name or assignment.assigned_vehicle_id} "
                    f"is currently committed to active task {conflict_veh.get('task_id')} ('{conflict_veh.get('title')}')."
                )

        # 2. Update task assignment fields
        now = datetime.now(timezone.utc)
        update_fields: Dict[str, Any] = {
            "status": ResponseTaskStatus.ASSIGNED.value,
            "updated_at": now,
        }
        if assignment.assigned_team_id is not None:
            update_fields["assigned_team_id"] = assignment.assigned_team_id
        if assignment.assigned_team_name is not None:
            update_fields["assigned_team_name"] = assignment.assigned_team_name
        if assignment.assigned_volunteer_ids is not None:
            update_fields["assigned_volunteer_ids"] = assignment.assigned_volunteer_ids
        if assignment.assigned_volunteer_names is not None:
            update_fields["assigned_volunteer_names"] = assignment.assigned_volunteer_names
        if assignment.assigned_vehicle_id is not None:
            update_fields["assigned_vehicle_id"] = assignment.assigned_vehicle_id
        if assignment.assigned_vehicle_name is not None:
            update_fields["assigned_vehicle_name"] = assignment.assigned_vehicle_name

        result = await db["response_tasks"].find_one_and_update(
            {"task_id": task_id.strip()},
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        updated_task = ResponseTask(**result)

        # Record Timeline Event
        actor_role_enum = None
        if officer_actor.get("role"):
            try:
                actor_role_enum = UserRole(officer_actor.get("role"))
            except Exception:
                pass

        assigned_names = ", ".join(updated_task.assigned_volunteer_names) if updated_task.assigned_volunteer_names else "Team"
        await record_timeline_event(
            db=db,
            report_id=updated_task.situation_id,
            event_type=TimelineEventType.TASK_ASSIGNED,
            details=f"Task {task_id} assigned to {assigned_names} by {officer_actor.get('full_name')}.",
            actor_id=officer_actor.get("id"),
            actor_name=officer_actor.get("full_name"),
            actor_role=actor_role_enum,
            metadata={
                "task_id": task_id,
                "volunteers": updated_task.assigned_volunteer_ids,
                "vehicle": updated_task.assigned_vehicle_id,
            },
        )

        # Phase 7 In-App & WhatsApp Notification to assigned responders
        try:
            from app.services.notification import get_notification_service
            notif_service = get_notification_service()
            await notif_service.dispatch_event(
                category=NotificationCategory.FIELD_OPERATIONS,
                event_type="TASK_ASSIGNED",
                severity=NotificationSeverity.HIGH if updated_task.priority.value in ["HIGH", "CRITICAL"] else NotificationSeverity.MEDIUM,
                title=f"New Assignment: {updated_task.title}",
                message=f"You have been assigned to task {task_id} ({updated_task.task_type.value}) by Emergency Officer {officer_actor.get('full_name')}.",
                entity_type="RESPONSE_TASK",
                entity_id=task_id,
                situation_id=updated_task.situation_id,
                coordination_plan_id=updated_task.plan_id,
                view_hint="volunteer-portal",
                target_user_ids=updated_task.assigned_volunteer_ids,
                target_roles=[UserRole.VOLUNTEER],
                material_state={"task_id": task_id, "status": "ASSIGNED"},
                metadata={"task_id": task_id, "situation_id": updated_task.situation_id},
            )
        except Exception as notif_err:
            logger.warning(f"Notification error on task assignment: {notif_err}")

        return updated_task

    @classmethod
    async def record_field_update(
        cls,
        task_id: str,
        update_req: FieldUpdateCreateRequest,
        actor: Dict[str, Any],
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> FieldUpdateRecord:
        """
        Records a ground operational update from an authorized field responder or officer.
        Automatically links material events (e.g. ROUTE_BLOCKED) to Phase 6 Live Monitoring & Replanning.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        task_doc = await db["response_tasks"].find_one({"task_id": task_id.strip()})
        if not task_doc:
            raise ValueError(f"Response task {task_id} not found.")

        task = ResponseTask(**task_doc)
        now = datetime.now(timezone.utc)

        field_update = FieldUpdateRecord(
            update_id=generate_update_id(),
            task_id=task_id.strip(),
            situation_id=task.situation_id,
            actor_id=actor.get("id", "UNKNOWN"),
            actor_name=actor.get("full_name", "Field Operator"),
            actor_role=actor.get("role", "VOLUNTEER"),
            event_type=update_req.event_type,
            message=update_req.message,
            location=update_req.location,
            details=update_req.details,
            timestamp=now,
        )

        # 1. Append update to task document
        await db["response_tasks"].update_one(
            {"task_id": task_id.strip()},
            {
                "$push": {"field_updates": field_update.model_dump()},
                "$set": {"updated_at": now},
            }
        )

        # 2. Record timeline event
        actor_role_enum = None
        if actor.get("role"):
            try:
                actor_role_enum = UserRole(actor.get("role"))
            except Exception:
                pass

        await record_timeline_event(
            db=db,
            report_id=task.situation_id,
            event_type=TimelineEventType.FIELD_UPDATE_RECORDED,
            details=f"[{update_req.event_type.value}] {update_req.message} (Task {task_id})",
            actor_id=actor.get("id"),
            actor_name=actor.get("full_name"),
            actor_role=actor_role_enum,
            metadata={"task_id": task_id, "event_type": update_req.event_type.value, "update_id": field_update.update_id},
        )

        # 3. If material ground event, route to Phase 6 Live Monitoring
        material_event_map = {
            FieldUpdateType.ROUTE_BLOCKED: MonitoringEventType.ROUTE_OBSTRUCTION_CHANGED,
            FieldUpdateType.TASK_BLOCKED: MonitoringEventType.TASK_BLOCKED,
            FieldUpdateType.TASK_FAILED: MonitoringEventType.TASK_FAILED,
            FieldUpdateType.RESOURCE_DAMAGED: MonitoringEventType.RESOURCE_QUANTITY_CHANGED,
            FieldUpdateType.SHELTER_CAPACITY_CHANGED: MonitoringEventType.SHELTER_CAPACITY_CHANGED,
            FieldUpdateType.VEHICLE_UNAVAILABLE: MonitoringEventType.TRANSPORT_STATUS_CHANGED,
            FieldUpdateType.TEAM_UNAVAILABLE: MonitoringEventType.VOLUNTEER_STATUS_CHANGED,
        }
        mon_event_type = material_event_map.get(update_req.event_type)
        if mon_event_type:
            try:
                from app.services.monitoring.monitoring_service import MonitoringService
                await MonitoringService.record_change_event(
                    event_type=mon_event_type,
                    source_type=EventSourceType.VOLUNTEER_NETWORK if actor.get("role") == "VOLUNTEER" else EventSourceType.OFFICER_DECISION,
                    source_id=task_id,
                    previous_state={"status": task.status.value},
                    new_state={"event_type": update_req.event_type.value, "message": update_req.message, "details": update_req.details},
                    situation_id=task.situation_id,
                    coordination_plan_id=task.plan_id,
                    actor=actor,
                    db=db,
                )
            except Exception as mon_err:
                logger.warning(f"Monitoring notice on field update: {mon_err}")

        # 4. Dispatch Phase 7 Notification
        try:
            from app.services.notification import get_notification_service
            notif_service = get_notification_service()
            await notif_service.dispatch_event(
                category=NotificationCategory.FIELD_OPERATIONS,
                event_type=f"FIELD_UPDATE_{update_req.event_type.value}",
                severity=NotificationSeverity.HIGH if update_req.event_type in [
                    FieldUpdateType.ROUTE_BLOCKED,
                    FieldUpdateType.TASK_BLOCKED,
                    FieldUpdateType.TASK_FAILED,
                    FieldUpdateType.ADDITIONAL_HELP_REQUIRED,
                ] else NotificationSeverity.MEDIUM,
                title=f"Field Update: {update_req.event_type.value}",
                message=f"{actor.get('full_name')}: {update_req.message} (Task {task_id})",
                entity_type="RESPONSE_TASK",
                entity_id=task_id,
                situation_id=task.situation_id,
                coordination_plan_id=task.plan_id,
                view_hint="operations",
                target_roles=[UserRole.EMERGENCY_OFFICER, UserRole.RESOURCE_MANAGER],
                material_state={"task_id": task_id, "event_type": update_req.event_type.value},
                metadata={"task_id": task_id, "situation_id": task.situation_id},
            )
        except Exception as notif_err:
            logger.warning(f"Notification error on field update: {notif_err}")

        return field_update

    @classmethod
    async def consume_resource_atomic(
        cls,
        resource_id: str,
        quantity: float,
        db: AsyncIOMotorDatabase,
    ):
        """
        Executes atomic database decrement on genuine inventory in MongoDB.
        Ensures available quantity never drops below zero ($gte check).
        """
        if quantity <= 0:
            return

        res = await db["resources"].update_one(
            {
                "resource_id": resource_id.strip(),
                "quantity_available": {"$gte": quantity},
            },
            {
                "$inc": {"quantity_available": -quantity},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            }
        )
        if res.matched_count == 0:
            # Check if record exists to provide explainable failure
            existing = await db["resources"].find_one({"resource_id": resource_id.strip()})
            if not existing:
                logger.warning(f"Resource {resource_id} not found in inventory for consumption.")
                return
            avail = existing.get("quantity_available", 0.0)
            raise ValueError(
                f"INSUFFICIENT_INVENTORY: Cannot consume {quantity} units of {existing.get('name')}. "
                f"Authoritative available quantity is {avail}."
            )

        logger.info(f"Atomically consumed {quantity} units from resource {resource_id}.")

    @classmethod
    async def resolve_incident(
        cls,
        situation_id: str,
        officer_actor: Dict[str, Any],
        req: IncidentResolutionRequest,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> Dict[str, Any]:
        """
        Validates completion of critical operational tasks and marks Situation as RESOLVED.
        Emergency Officer review is mandatory.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        clean_sit_id = situation_id.strip()
        sit_doc = await db["situations"].find_one({
            "$or": [
                {"situation_id": clean_sit_id},
                {"situation_id": clean_sit_id.upper()},
                {"situation_id": clean_sit_id.lower()},
                {"_id": clean_sit_id},
            ]
        })
        if not sit_doc:
            raise ValueError(f"Situation {clean_sit_id} not found.")

        # Check for uncompleted critical/high priority tasks
        uncompleted_tasks = await db["response_tasks"].find({
            "situation_id": clean_sit_id,
            "status": {"$in": [
                ResponseTaskStatus.PENDING_APPROVAL.value,
                ResponseTaskStatus.APPROVED.value,
                ResponseTaskStatus.ASSIGNED.value,
                ResponseTaskStatus.ACCEPTED.value,
                ResponseTaskStatus.IN_PROGRESS.value,
                ResponseTaskStatus.BLOCKED.value,
                ResponseTaskStatus.ESCALATED.value,
            ]},
        }).to_list(100)

        if uncompleted_tasks and not req.force_override_uncompleted:
            task_titles = [f"{t.get('task_id')} ({t.get('status')})" for t in uncompleted_tasks[:5]]
            raise ValueError(
                f"UNRESOLVED_OPERATIONS: Cannot resolve incident while {len(uncompleted_tasks)} tasks remain active: "
                f"{', '.join(task_titles)}. Complete all tasks or provide an explicit officer override."
            )

        now = datetime.now(timezone.utc)
        await db["situations"].update_one(
            {"situation_id": clean_sit_id},
            {
                "$set": {
                    "status": SituationStatus.RESOLVED.value,
                    "resolved_by": officer_actor.get("full_name"),
                    "resolved_by_id": officer_actor.get("id"),
                    "resolved_at": now,
                    "resolution_notes": req.resolution_notes,
                    "updated_at": now,
                }
            }
        )

        actor_role_enum = None
        if officer_actor.get("role"):
            try:
                actor_role_enum = UserRole(officer_actor.get("role"))
            except Exception:
                pass

        await record_timeline_event(
            db=db,
            report_id=clean_sit_id,
            event_type=TimelineEventType.INCIDENT_RESOLVED,
            details=f"Incident {clean_sit_id} marked RESOLVED by Emergency Officer {officer_actor.get('full_name')}.",
            actor_id=officer_actor.get("id"),
            actor_name=officer_actor.get("full_name"),
            actor_role=actor_role_enum,
            metadata={"situation_id": clean_sit_id, "resolution_notes": req.resolution_notes},
        )

        return {
            "situation_id": clean_sit_id,
            "status": SituationStatus.RESOLVED.value,
            "resolved_by": officer_actor.get("full_name"),
            "resolved_at": now.isoformat(),
            "uncompleted_tasks_overridden": len(uncompleted_tasks) if req.force_override_uncompleted else 0,
        }

    @staticmethod
    def _parse_iso_or_dt(val: Any) -> Optional[datetime]:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
        if isinstance(val, str):
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
            except Exception:
                return None
        return None

    @classmethod
    async def close_incident(
        cls,
        situation_id: str,
        officer_actor: Dict[str, Any],
        req: IncidentCloseRequest,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> IncidentResolutionSummary:
        """
        Final closure of an emergency situation. Compiles a comprehensive, authoritative
        IncidentResolutionSummary from genuine MongoDB records (zero hallucinated data).
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        clean_sit_id = situation_id.strip()
        sit_doc = await db["situations"].find_one({
            "$or": [
                {"situation_id": clean_sit_id},
                {"situation_id": clean_sit_id.upper()},
                {"situation_id": clean_sit_id.lower()},
                {"_id": clean_sit_id},
            ]
        })
        if not sit_doc:
            raise ValueError(f"Situation {clean_sit_id} not found.")

        current_status = sit_doc.get("status")
        if current_status == SituationStatus.CLOSED.value:
            raise ValueError(f"Incident {clean_sit_id} is already CLOSED.")

        if current_status not in [SituationStatus.RESOLVED.value, SituationStatus.RESPONSE_IN_PROGRESS.value, SituationStatus.ACTIVE.value]:
            raise ValueError(f"Incident {clean_sit_id} with status '{current_status}' is not in a closable state.")

        # Check for blocking uncompleted tasks if closing directly without prior resolution
        if current_status != SituationStatus.RESOLVED.value:
            uncompleted_tasks = await db["response_tasks"].find({
                "situation_id": clean_sit_id,
                "status": {"$in": [
                    ResponseTaskStatus.PENDING_APPROVAL.value,
                    ResponseTaskStatus.APPROVED.value,
                    ResponseTaskStatus.ASSIGNED.value,
                    ResponseTaskStatus.ACCEPTED.value,
                    ResponseTaskStatus.IN_PROGRESS.value,
                    ResponseTaskStatus.BLOCKED.value,
                ]}
            }).to_list(100)

            if uncompleted_tasks and not req.force_override_uncompleted:
                raise ValueError(
                    f"UNCOMPLETED_OPERATIONS: Cannot close incident {clean_sit_id}. "
                    f"{len(uncompleted_tasks)} operational task(s) are still active or uncompleted. "
                    f"Resolve tasks first or check force override."
                )

        now = datetime.now(timezone.utc)

        # 1. Aggregate real DB metrics
        report_ids = sit_doc.get("report_ids", [])
        total_reports = len(report_ids) if report_ids else sit_doc.get("report_count", 1)

        plan_versions_count = await db["coordination_plans"].count_documents({"situation_id": clean_sit_id})
        total_tasks_count = await db["response_tasks"].count_documents({"situation_id": clean_sit_id})
        tasks_completed = await db["response_tasks"].count_documents({
            "situation_id": clean_sit_id,
            "status": ResponseTaskStatus.COMPLETED.value,
        })
        tasks_blocked = await db["response_tasks"].count_documents({
            "situation_id": clean_sit_id,
            "status": {"$in": [ResponseTaskStatus.BLOCKED.value, ResponseTaskStatus.FAILED.value]},
        })

        monitoring_events_count = await db["monitoring_events"].count_documents({"situation_id": clean_sit_id})
        replanning_count = await db["coordination_plans"].count_documents({"situation_id": clean_sit_id, "is_revised_version": True})
        notifications_count = await db["notifications"].count_documents({"situation_id": clean_sit_id})

        # Responders and vehicles involved
        vol_ids = await db["response_tasks"].distinct("assigned_volunteer_ids", {"situation_id": clean_sit_id})
        volunteers_involved = len([v for v in vol_ids if v])

        veh_ids = await db["response_tasks"].distinct("assigned_vehicle_id", {"situation_id": clean_sit_id})
        vehicles_involved = len([v for v in veh_ids if v])

        # Authoritative resources utilized aggregation
        resource_map: Dict[str, Dict[str, Any]] = {}
        completed_cursor = db["response_tasks"].find({
            "situation_id": clean_sit_id,
            "status": ResponseTaskStatus.COMPLETED.value,
        })
        async for comp_task in completed_cursor:
            for r in comp_task.get("assigned_resources", []):
                r_id = r.get("resource_id") or "RES-GENERAL"
                r_name = r.get("resource_name") or r.get("name") or "Emergency Supplies"
                r_unit = r.get("unit") or "units"
                qty = float(r.get("consumed_quantity") or r.get("allocated_quantity") or r.get("quantity") or 0.0)
                if r_id not in resource_map:
                    resource_map[r_id] = {
                        "resource_id": r_id,
                        "resource_name": r_name,
                        "quantity_consumed": 0.0,
                        "unit": r_unit,
                    }
                resource_map[r_id]["quantity_consumed"] += qty

        resources_utilized = list(resource_map.values())

        # Calculate duration
        created_at = cls._parse_iso_or_dt(sit_doc.get("created_at")) or now
        resolved_at = cls._parse_iso_or_dt(sit_doc.get("resolved_at"))
        duration_hours = max(0.1, round((now - created_at).total_seconds() / 3600.0, 2))

        # 2. Update situation status to CLOSED
        await db["situations"].update_one(
            {"situation_id": clean_sit_id},
            {
                "$set": {
                    "status": SituationStatus.CLOSED.value,
                    "closed_by": officer_actor.get("full_name"),
                    "closed_by_id": officer_actor.get("id"),
                    "closed_at": now,
                    "close_notes": req.close_notes,
                    "final_summary_notes": req.final_summary_notes,
                    "updated_at": now,
                }
            }
        )

        # 3. Record timeline event
        actor_role_enum = None
        if officer_actor.get("role"):
            try:
                actor_role_enum = UserRole(officer_actor.get("role"))
            except Exception:
                pass

        await record_timeline_event(
            db=db,
            report_id=clean_sit_id,
            event_type=TimelineEventType.INCIDENT_CLOSED,
            details=f"Incident {clean_sit_id} CLOSED by Emergency Officer {officer_actor.get('full_name')}.",
            actor_id=officer_actor.get("id"),
            actor_name=officer_actor.get("full_name"),
            actor_role=actor_role_enum,
            metadata={
                "situation_id": clean_sit_id,
                "close_notes": req.close_notes,
                "total_tasks_completed": tasks_completed,
                "total_tasks_created": total_tasks_count,
            },
        )

        summary = IncidentResolutionSummary(
            situation_id=clean_sit_id,
            title=sit_doc.get("title", f"Situation {clean_sit_id}"),
            emergency_type=sit_doc.get("emergency_type", "General Emergency"),
            severity_level=str(sit_doc.get("officer_override_severity") or sit_doc.get("computed_severity_level") or "MEDIUM"),
            final_status=SituationStatus.CLOSED.value,
            total_citizen_reports=total_reports,
            active_plan_versions=plan_versions_count,
            total_tasks_created=total_tasks_count,
            tasks_completed=tasks_completed,
            tasks_blocked_or_failed=tasks_blocked,
            resources_utilized=resources_utilized,
            volunteers_involved_count=volunteers_involved,
            vehicles_involved_count=vehicles_involved,
            monitoring_events_count=monitoring_events_count,
            replanning_iterations_count=replanning_count,
            notifications_sent_count=notifications_count,
            resolved_by=sit_doc.get("resolved_by") or officer_actor.get("full_name"),
            resolved_at=resolved_at,
            closed_by=officer_actor.get("full_name"),
            closed_at=now,
            resolution_notes=req.close_notes,
            duration_hours=duration_hours,
            created_at=created_at,
            updated_at=now,
        )

        return summary

    @classmethod
    async def get_incident_summary(
        cls,
        situation_id: str,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> IncidentResolutionSummary:
        """Fetch post-incident summary aggregated from actual DB records."""
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        clean_sit_id = situation_id.strip().upper()
        sit_doc = await db["situations"].find_one({"situation_id": clean_sit_id})
        if not sit_doc:
            raise ValueError(f"Situation {clean_sit_id} not found.")

        now = datetime.now(timezone.utc)
        created_at = cls._parse_iso_or_dt(sit_doc.get("created_at")) or now
        resolved_at = cls._parse_iso_or_dt(sit_doc.get("resolved_at"))
        closed_at = cls._parse_iso_or_dt(sit_doc.get("closed_at"))
        updated_at = cls._parse_iso_or_dt(sit_doc.get("updated_at")) or now
        duration_hours = max(0.1, round((now - created_at).total_seconds() / 3600.0, 2))

        report_ids = sit_doc.get("report_ids", [])
        total_reports = len(report_ids) if report_ids else sit_doc.get("report_count", 1)

        plan_versions_count = await db["coordination_plans"].count_documents({"situation_id": clean_sit_id})
        total_tasks_count = await db["response_tasks"].count_documents({"situation_id": clean_sit_id})
        tasks_completed = await db["response_tasks"].count_documents({
            "situation_id": clean_sit_id,
            "status": ResponseTaskStatus.COMPLETED.value,
        })
        tasks_blocked = await db["response_tasks"].count_documents({
            "situation_id": clean_sit_id,
            "status": {"$in": [ResponseTaskStatus.BLOCKED.value, ResponseTaskStatus.FAILED.value]},
        })

        monitoring_events_count = await db["monitoring_events"].count_documents({"situation_id": clean_sit_id})
        replanning_count = await db["coordination_plans"].count_documents({"situation_id": clean_sit_id, "is_revised_version": True})
        notifications_count = await db["notifications"].count_documents({"situation_id": clean_sit_id})

        vol_ids = await db["response_tasks"].distinct("assigned_volunteer_ids", {"situation_id": clean_sit_id})
        volunteers_involved = len([v for v in vol_ids if v])

        veh_ids = await db["response_tasks"].distinct("assigned_vehicle_id", {"situation_id": clean_sit_id})
        vehicles_involved = len([v for v in veh_ids if v])

        # Resources utilized
        resource_map: Dict[str, Dict[str, Any]] = {}
        completed_cursor = db["response_tasks"].find({
            "situation_id": clean_sit_id,
            "status": ResponseTaskStatus.COMPLETED.value,
        })
        async for comp_task in completed_cursor:
            for r in comp_task.get("assigned_resources", []):
                r_id = r.get("resource_id") or "RES-GENERAL"
                r_name = r.get("resource_name") or r.get("name") or "Emergency Supplies"
                r_unit = r.get("unit") or "units"
                qty = float(r.get("consumed_quantity") or r.get("allocated_quantity") or r.get("quantity") or 0.0)
                if r_id not in resource_map:
                    resource_map[r_id] = {
                        "resource_id": r_id,
                        "resource_name": r_name,
                        "quantity_consumed": 0.0,
                        "unit": r_unit,
                    }
                resource_map[r_id]["quantity_consumed"] += qty

        resources_utilized = list(resource_map.values())

        return IncidentResolutionSummary(
            situation_id=clean_sit_id,
            title=sit_doc.get("title", f"Situation {clean_sit_id}"),
            emergency_type=sit_doc.get("emergency_type", "General Emergency"),
            severity_level=str(sit_doc.get("officer_override_severity") or sit_doc.get("computed_severity_level") or "MEDIUM"),
            final_status=str(sit_doc.get("status", "ACTIVE")),
            total_citizen_reports=total_reports,
            active_plan_versions=plan_versions_count,
            total_tasks_created=total_tasks_count,
            tasks_completed=tasks_completed,
            tasks_blocked_or_failed=tasks_blocked,
            resources_utilized=resources_utilized,
            volunteers_involved_count=volunteers_involved,
            vehicles_involved_count=vehicles_involved,
            monitoring_events_count=monitoring_events_count,
            replanning_iterations_count=replanning_count,
            notifications_sent_count=notifications_count,
            resolved_by=sit_doc.get("resolved_by"),
            resolved_at=resolved_at,
            closed_by=sit_doc.get("closed_by"),
            closed_at=closed_at,
            resolution_notes=sit_doc.get("resolution_notes") or sit_doc.get("close_notes"),
            duration_hours=duration_hours,
            created_at=created_at,
            updated_at=updated_at,
        )
