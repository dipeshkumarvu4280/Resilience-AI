import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from app.models.enums import (
    CoordinationPlanStatus,
    PlanReviewAction,
    TimelineEventType,
    UserRole,
)
from app.models.agent import (
    CoordinationPlan,
    OfficerPlanReview,
    PlanRecommendedResource,
    RecommendedShelter,
    RecommendedHealthcareFacility,
    RecommendedVolunteerAssignment,
    RecommendedTransport,
    RecommendedRoute,
)
from app.models.monitoring import (
    PlanActivationResponse,
    PlanModifyRequest,
    PlanRejectRequest,
)
from app.services.agents.orchestrator import compute_situation_state_fingerprint
from app.services.timeline import record_timeline_event
from app.db.mongodb import db_manager

logger = logging.getLogger("resilience.services.monitoring.activation")


class PlanActivationService:
    """
    Phase 6.4 Human Approval + Plan Activation Service.
    Enforces the non-negotiable Human-in-the-Loop boundary:
    1. Server-side validation of officer identity and role.
    2. Stale-Plan Protection: verifies operational conditions haven't changed since plan synthesis.
    3. Optimistic concurrency locking to eliminate approval race conditions.
    4. Atomic supersession of previous plan versions and activation of approved revision.
    5. Immutable audit trail of officer decisions.
    """

    _approval_locks: Dict[str, asyncio.Lock] = {}

    @classmethod
    def _get_lock(cls, situation_id: str) -> asyncio.Lock:
        if situation_id not in cls._approval_locks:
            cls._approval_locks[situation_id] = asyncio.Lock()
        return cls._approval_locks[situation_id]

    @classmethod
    async def is_plan_stale(
        cls,
        plan: CoordinationPlan,
        db: AsyncIOMotorDatabase,
    ) -> tuple[bool, str]:
        """
        Evaluates whether a response plan is stale due to subsequent operational mutations.
        Returns (is_stale, reason).
        """
        clean_sit_id = plan.situation_id.strip().upper()

        # 1. Fetch current Situation
        sit_doc = await db["situations"].find_one({"situation_id": clean_sit_id})
        if not sit_doc:
            sit_doc = await db["situations"].find_one({"_id": clean_sit_id})

        if not sit_doc:
            return True, f"Associated situation {clean_sit_id} no longer exists."

        # 2. Check if a newer monitoring event occurred for this situation after plan generation
        plan_gen_time = plan.generated_at
        if plan_gen_time.tzinfo is None:
            plan_gen_time = plan_gen_time.replace(tzinfo=timezone.utc)

        newer_event = await db["monitoring_events"].find_one({
            "situation_id": clean_sit_id,
            "detected_at": {"$gt": plan_gen_time.isoformat()},
            "impact_level": {"$in": ["CRITICAL", "HIGH"]},
        })

        if newer_event:
            return True, f"New critical event {newer_event.get('event_id')} ({newer_event.get('event_type')}) detected after plan generation."

        # 3. Check if current situation fingerprint differs materially
        current_sit_fp = compute_situation_state_fingerprint(sit_doc)
        if plan.state_fingerprint and current_sit_fp != plan.state_fingerprint:
            # If the fingerprint changed, verify if severity or report count changed
            curr_sev = str(sit_doc.get("officer_override_severity") or sit_doc.get("computed_severity_level") or "MEDIUM").upper()
            if curr_sev != plan.assessed_priority.value:
                return True, f"Situation severity changed ({plan.assessed_priority.value} -> {curr_sev})."

        return False, "Plan is current."

    @classmethod
    async def approve_and_activate_plan(
        cls,
        plan_id: str,
        officer_actor: Dict[str, Any],
        officer_notes: Optional[str] = None,
        expected_state_fingerprint: Optional[str] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> PlanActivationResponse:
        """
        Approves and activates a revised or draft Coordination Plan with stale-plan protection
        and atomic version supersession.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        plan_data = await db["coordination_plans"].find_one({"plan_id": plan_id})
        if not plan_data:
            raise ValueError(f"Coordination Plan {plan_id} not found.")

        plan = CoordinationPlan(**plan_data)
        situation_id = plan.situation_id.strip().upper()

        # Concurrency Lock on situation
        lock = cls._get_lock(situation_id)
        async with lock:
            # Re-fetch inside lock to prevent race condition
            plan_data_current = await db["coordination_plans"].find_one({"plan_id": plan_id})
            if not plan_data_current:
                raise ValueError(f"Coordination Plan {plan_id} not found.")

            current_status = plan_data_current.get("status")
            if plan_data_current.get("is_simulation") or plan.is_simulation or current_status == CoordinationPlanStatus.SIMULATION_RESULT.value:
                raise ValueError("SIMULATION_CANNOT_ACTIVATE: Simulation results cannot be activated as operational response plans.")

            if current_status in [CoordinationPlanStatus.ACTIVE.value, CoordinationPlanStatus.APPROVED.value]:
                raise ValueError(f"Coordination Plan {plan_id} is already ACTIVE.")

            if current_status not in [
                CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
                CoordinationPlanStatus.MODIFIED.value,
                CoordinationPlanStatus.DRAFT.value,
            ]:
                raise ValueError(f"Coordination Plan {plan_id} cannot be approved from status '{current_status}'.")

            # 1. Stale Plan Protection
            is_stale, stale_reason = await cls.is_plan_stale(plan, db)
            actor_role_enum = None
            if officer_actor.get("role"):
                try:
                    actor_role_enum = UserRole(officer_actor.get("role"))
                except Exception:
                    pass

            if is_stale:
                # Record Stale Plan Blocked Audit Event
                await record_timeline_event(
                    db=db,
                    report_id=situation_id,
                    event_type=TimelineEventType.STALE_PLAN_DETECTED,
                    details=f"Plan {plan_id} (v{plan.version}) activation blocked: {stale_reason}",
                    actor_id=officer_actor.get("id"),
                    actor_name=officer_actor.get("full_name"),
                    actor_role=actor_role_enum,
                    metadata={"plan_id": plan_id, "version": plan.version, "stale_reason": stale_reason},
                )
                await record_timeline_event(
                    db=db,
                    report_id=situation_id,
                    event_type=TimelineEventType.PLAN_APPROVAL_BLOCKED,
                    details=f"Emergency Officer {officer_actor.get('full_name')} attempted to approve stale plan {plan_id}.",
                    actor_id=officer_actor.get("id"),
                    actor_name=officer_actor.get("full_name"),
                    actor_role=actor_role_enum,
                )
                raise ValueError(f"STALE_PLAN_DETECTED: This response plan is no longer current because operational conditions changed ({stale_reason}). Please review the newly generated plan.")

            # 2. Check Expected Fingerprint
            if expected_state_fingerprint and plan.state_fingerprint:
                if expected_state_fingerprint != plan.state_fingerprint:
                    raise ValueError("PLAN_FINGERPRINT_MISMATCH: Response plan state was modified concurrently.")

            now = datetime.now(timezone.utc)

            officer_review = OfficerPlanReview(
                decision=PlanReviewAction.APPROVE,
                reviewed_by_id=officer_actor["id"],
                reviewed_by_name=officer_actor["full_name"],
                reviewed_by_role=officer_actor.get("role", "OFFICER"),
                reviewed_at=now,
                officer_notes=officer_notes,
            )

            # 3. Atomic State Transition
            # A. Supersede any other active/approved plans for this situation
            await db["coordination_plans"].update_many(
                {
                    "situation_id": situation_id,
                    "plan_id": {"$ne": plan_id},
                    "status": {"$in": [CoordinationPlanStatus.ACTIVE.value, CoordinationPlanStatus.APPROVED.value]},
                },
                {"$set": {"status": CoordinationPlanStatus.SUPERSEDED.value}}
            )

            # B. Activate this revised plan
            await db["coordination_plans"].update_one(
                {"plan_id": plan_id},
                {
                    "$set": {
                        "status": CoordinationPlanStatus.ACTIVE.value,
                        "officer_review": {
                            "decision": officer_review.decision.value,
                            "reviewed_by_id": officer_review.reviewed_by_id,
                            "reviewed_by_name": officer_review.reviewed_by_name,
                            "reviewed_by_role": officer_review.reviewed_by_role,
                            "reviewed_at": officer_review.reviewed_at.isoformat(),
                            "officer_notes": officer_review.officer_notes,
                        },
                    }
                }
            )

            # 4. Record Timeline Audit Events
            await record_timeline_event(
                db=db,
                report_id=situation_id,
                event_type=TimelineEventType.PLAN_APPROVED,
                details=f"Response Plan {plan_id} (v{plan.version}) approved by Emergency Officer {officer_actor['full_name']}.",
                actor_id=officer_actor["id"],
                actor_name=officer_actor["full_name"],
                actor_role=actor_role_enum,
                metadata={"plan_id": plan_id, "version": plan.version, "notes": officer_notes},
            )

            await record_timeline_event(
                db=db,
                report_id=situation_id,
                event_type=TimelineEventType.PLAN_ACTIVATED,
                details=f"Response Plan {plan_id} (v{plan.version}) is now ACTIVE.",
                actor_id=officer_actor["id"],
                actor_name=officer_actor["full_name"],
                actor_role=actor_role_enum,
                metadata={"plan_id": plan_id, "version": plan.version},
            )

            if plan.previous_plan_id:
                await record_timeline_event(
                    db=db,
                    report_id=situation_id,
                    event_type=TimelineEventType.PLAN_SUPERSEDED,
                    details=f"Previous Response Plan {plan.previous_plan_id} (v{plan.previous_version}) superseded by {plan_id}.",
                    actor_id=officer_actor["id"],
                    actor_name=officer_actor["full_name"],
                    actor_role=actor_role_enum,
                    metadata={"previous_plan_id": plan.previous_plan_id, "activated_plan_id": plan_id},
                )

            # Dispatch Phase 6 Monitoring Events
            try:
                from app.services.monitoring.monitoring_service import MonitoringService
                from app.models.enums import MonitoringEventType, EventSourceType
                await MonitoringService.record_change_event(
                    event_type=MonitoringEventType.PLAN_ACTIVATED,
                    source_type=EventSourceType.OFFICER_DECISION,
                    source_id=plan_id,
                    previous_state={
                        "status": current_status,
                        "version": plan.version,
                    },
                    new_state={
                        "status": CoordinationPlanStatus.ACTIVE.value,
                        "version": plan.version,
                        "approved_by": officer_actor.get("full_name"),
                    },
                    situation_id=situation_id,
                    coordination_plan_id=plan_id,
                    actor=officer_actor,
                    db=db,
                )

                if plan.previous_plan_id:
                    await MonitoringService.record_change_event(
                        event_type=MonitoringEventType.PLAN_SUPERSEDED,
                        source_type=EventSourceType.OFFICER_DECISION,
                        source_id=plan.previous_plan_id,
                        previous_state={
                            "status": CoordinationPlanStatus.ACTIVE.value,
                            "version": plan.previous_version or (plan.version - 1),
                        },
                        new_state={
                            "status": CoordinationPlanStatus.SUPERSEDED.value,
                            "superseded_by": plan_id,
                        },
                        situation_id=situation_id,
                        coordination_plan_id=plan.previous_plan_id,
                        actor=officer_actor,
                        db=db,
                    )
            except Exception as mon_err:
                logger.warning(f"Monitoring notice on plan activation {plan_id}: {mon_err}")

            # Authoritative Constraint Remediation & Alert Resolution
            try:
                from app.services.monitoring.remediation_service import ConstraintRemediationService
                remediation_results = await ConstraintRemediationService.evaluate_and_remediate_all_for_situation(
                    situation_id=situation_id,
                    active_plan=plan,
                    officer_actor=officer_actor,
                    db=db,
                )
                logger.info(f"Evaluated {len(remediation_results)} constraints on plan activation {plan_id}: {[r.remediation_status for r in remediation_results]}")
            except Exception as rem_err:
                logger.warning(f"Error evaluating constraint remediation on plan activation {plan_id}: {rem_err}")

            # Phase 8: Derive Executable Tasks from Active Response Plan
            try:
                from app.services.field_operations_service import FieldOperationsService
                await FieldOperationsService.derive_tasks_from_plan(
                    plan=plan,
                    officer_actor=officer_actor,
                    db=db,
                )
            except Exception as task_err:
                logger.warning(f"Error deriving field tasks on plan activation {plan_id}: {task_err}")

            # Phase 7: Event-Driven Notification Dispatch
            try:
                from app.services.notification import get_notification_service
                from app.models.enums import NotificationCategory, NotificationSeverity, UserRole

                notif_service = get_notification_service()
                await notif_service.dispatch_event(
                    category=NotificationCategory.COORDINATION_PLAN,
                    event_type="PLAN_ACTIVATED",
                    severity=NotificationSeverity.HIGH,
                    title=f"Response Plan {plan_id} (v{plan.version}) Activated",
                    message=f"Plan approved and activated by Officer {officer_actor.get('full_name')}.",
                    entity_type="COORDINATION_PLAN",
                    entity_id=plan_id,
                    situation_id=situation_id,
                    coordination_plan_id=plan_id,
                    view_hint="plans",
                    target_roles=[UserRole.EMERGENCY_OFFICER, UserRole.RESOURCE_MANAGER, UserRole.ADMIN],
                    material_state={"plan_id": plan_id, "version": plan.version, "status": CoordinationPlanStatus.ACTIVE.value},
                    metadata={"plan_id": plan_id, "version": plan.version, "situation_id": situation_id},
                )
            except Exception as notif_err:
                logger.warning(f"Notification notice on plan activation {plan_id}: {notif_err}")

            logger.info(f"Response Plan {plan_id} (v{plan.version}) successfully approved and activated by {officer_actor['full_name']}.")

            return PlanActivationResponse(
                success=True,
                plan_id=plan_id,
                version=plan.version,
                status=CoordinationPlanStatus.ACTIVE.value,
                previous_plan_id=plan.previous_plan_id,
                previous_version=plan.previous_version,
                activated_at=now,
                officer_id=officer_actor["id"],
                officer_name=officer_actor["full_name"],
                message=f"Response Plan {plan_id} (v{plan.version}) successfully activated.",
            )

    @classmethod
    async def modify_revised_plan(
        cls,
        plan_id: str,
        modify_req: PlanModifyRequest,
        officer_actor: Dict[str, Any],
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> CoordinationPlan:
        """
        Modifies operational allocation values in a revised plan, preserves officer notes,
        and keeps the plan in PENDING_OFFICER_REVIEW for explicit approval.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        plan_data = await db["coordination_plans"].find_one({"plan_id": plan_id})
        if not plan_data:
            raise ValueError(f"Coordination Plan {plan_id} not found.")

        current_status = plan_data.get("status")
        if current_status not in [
            CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
            CoordinationPlanStatus.MODIFIED.value,
            CoordinationPlanStatus.DRAFT.value,
        ]:
            raise ValueError(f"Coordination Plan {plan_id} cannot be modified from status '{current_status}'.")

        now = datetime.now(timezone.utc)
        mod_dict: Dict[str, Any] = {}
        update_fields: Dict[str, Any] = {
            "status": CoordinationPlanStatus.MODIFIED.value,
        }

        if modify_req.modified_needs is not None:
            mod_dict["needs"] = modify_req.modified_needs
            update_fields["assessed_needs"] = modify_req.modified_needs

        if modify_req.modified_allocations is not None:
            mod_dict["allocations"] = modify_req.modified_allocations
            update_fields["recommended_allocations"] = modify_req.modified_allocations

        if modify_req.modified_shelters is not None:
            mod_dict["shelters"] = modify_req.modified_shelters
            update_fields["recommended_shelters"] = modify_req.modified_shelters

        if modify_req.modified_facilities is not None:
            mod_dict["facilities"] = modify_req.modified_facilities
            update_fields["recommended_facilities"] = modify_req.modified_facilities

        if modify_req.modified_volunteers is not None:
            mod_dict["volunteers"] = modify_req.modified_volunteers
            update_fields["recommended_volunteers"] = modify_req.modified_volunteers

        if modify_req.modified_transports is not None:
            mod_dict["transports"] = modify_req.modified_transports
            update_fields["recommended_transports"] = modify_req.modified_transports

        if modify_req.modified_routes is not None:
            mod_dict["routes"] = modify_req.modified_routes
            update_fields["recommended_routes"] = modify_req.modified_routes

        officer_review = OfficerPlanReview(
            decision=PlanReviewAction.MODIFY,
            reviewed_by_id=officer_actor["id"],
            reviewed_by_name=officer_actor["full_name"],
            reviewed_by_role=officer_actor.get("role", "OFFICER"),
            reviewed_at=now,
            officer_notes=modify_req.notes,
            modified_fields=mod_dict if mod_dict else None,
        )

        update_fields["officer_review"] = {
            "decision": officer_review.decision.value,
            "reviewed_by_id": officer_review.reviewed_by_id,
            "reviewed_by_name": officer_review.reviewed_by_name,
            "reviewed_by_role": officer_review.reviewed_by_role,
            "reviewed_at": officer_review.reviewed_at.isoformat(),
            "officer_notes": officer_review.officer_notes,
            "modified_fields": officer_review.modified_fields,
        }

        await db["coordination_plans"].update_one(
            {"plan_id": plan_id},
            {"$set": update_fields}
        )

        actor_role_enum = None
        if officer_actor.get("role"):
            try:
                actor_role_enum = UserRole(officer_actor.get("role"))
            except Exception:
                pass

        situation_id = plan_data.get("situation_id", plan_id)
        await record_timeline_event(
            db=db,
            report_id=situation_id,
            event_type=TimelineEventType.PLAN_MODIFIED,
            details=f"Response Plan {plan_id} modified by Emergency Officer {officer_actor['full_name']}.",
            actor_id=officer_actor["id"],
            actor_name=officer_actor["full_name"],
            actor_role=actor_role_enum,
            metadata={"plan_id": plan_id, "modified_categories": list(mod_dict.keys()), "notes": modify_req.notes},
        )

        # Dispatch Phase 6 Monitoring Event
        try:
            from app.services.monitoring.monitoring_service import MonitoringService
            from app.models.enums import MonitoringEventType, EventSourceType
            await MonitoringService.record_change_event(
                event_type=MonitoringEventType.PLAN_MODIFIED,
                source_type=EventSourceType.OFFICER_DECISION,
                source_id=plan_id,
                previous_state={"status": current_status},
                new_state={"status": CoordinationPlanStatus.MODIFIED.value, "modified_categories": list(mod_dict.keys())},
                situation_id=situation_id,
                coordination_plan_id=plan_id,
                actor=officer_actor,
                db=db,
            )
        except Exception as mon_err:
            logger.warning(f"Monitoring notice on plan modification {plan_id}: {mon_err}")

        updated = await db["coordination_plans"].find_one({"plan_id": plan_id})
        return CoordinationPlan(**updated)

    @classmethod
    async def reject_revised_plan(
        cls,
        plan_id: str,
        reject_req: PlanRejectRequest,
        officer_actor: Dict[str, Any],
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> CoordinationPlan:
        """
        Rejects a revised response plan with mandatory explanation.
        The previous active plan remains active.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        if not reject_req.rejection_reason or not reject_req.rejection_reason.strip():
            raise ValueError("Rejection reason is mandatory.")

        plan_data = await db["coordination_plans"].find_one({"plan_id": plan_id})
        if not plan_data:
            raise ValueError(f"Coordination Plan {plan_id} not found.")

        current_status = plan_data.get("status")
        if current_status not in [
            CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
            CoordinationPlanStatus.MODIFIED.value,
            CoordinationPlanStatus.DRAFT.value,
        ]:
            raise ValueError(f"Coordination Plan {plan_id} cannot be rejected from status '{current_status}'.")

        now = datetime.now(timezone.utc)
        officer_review = OfficerPlanReview(
            decision=PlanReviewAction.REJECT,
            reviewed_by_id=officer_actor["id"],
            reviewed_by_name=officer_actor["full_name"],
            reviewed_by_role=officer_actor.get("role", "OFFICER"),
            reviewed_at=now,
            officer_notes=f"{reject_req.rejection_reason} | Notes: {reject_req.officer_notes or 'None'}",
        )

        await db["coordination_plans"].update_one(
            {"plan_id": plan_id},
            {
                "$set": {
                    "status": CoordinationPlanStatus.REJECTED.value,
                    "officer_review": {
                        "decision": officer_review.decision.value,
                        "reviewed_by_id": officer_review.reviewed_by_id,
                        "reviewed_by_name": officer_review.reviewed_by_name,
                        "reviewed_by_role": officer_review.reviewed_by_role,
                        "reviewed_at": officer_review.reviewed_at.isoformat(),
                        "officer_notes": officer_review.officer_notes,
                    },
                }
            }
        )

        actor_role_enum = None
        if officer_actor.get("role"):
            try:
                actor_role_enum = UserRole(officer_actor.get("role"))
            except Exception:
                pass

        situation_id = plan_data.get("situation_id", plan_id)
        await record_timeline_event(
            db=db,
            report_id=situation_id,
            event_type=TimelineEventType.PLAN_REJECTED,
            details=f"Response Plan {plan_id} rejected by Emergency Officer {officer_actor['full_name']}. Reason: {reject_req.rejection_reason}",
            actor_id=officer_actor["id"],
            actor_name=officer_actor["full_name"],
            actor_role=actor_role_enum,
            metadata={"plan_id": plan_id, "rejection_reason": reject_req.rejection_reason},
        )

        # Dispatch Phase 6 Monitoring Event
        try:
            from app.services.monitoring.monitoring_service import MonitoringService
            from app.models.enums import MonitoringEventType, EventSourceType
            await MonitoringService.record_change_event(
                event_type=MonitoringEventType.PLAN_REJECTED,
                source_type=EventSourceType.OFFICER_DECISION,
                source_id=plan_id,
                previous_state={"status": current_status},
                new_state={"status": CoordinationPlanStatus.REJECTED.value, "reason": reject_req.rejection_reason},
                situation_id=situation_id,
                coordination_plan_id=plan_id,
                actor=officer_actor,
                db=db,
            )
        except Exception as mon_err:
            logger.warning(f"Monitoring notice on plan rejection {plan_id}: {mon_err}")

        updated = await db["coordination_plans"].find_one({"plan_id": plan_id})
        return CoordinationPlan(**updated)
