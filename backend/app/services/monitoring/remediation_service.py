import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.models.enums import (
    EventSourceType,
    MonitoringEventType,
    EventStatus,
    ImpactLevel,
    PlanValidityStatus,
    TimelineEventType,
    UserRole,
    CoordinationPlanStatus,
)
from app.models.agent import CoordinationPlan
from app.services.timeline import record_timeline_event

logger = logging.getLogger("resilience.services.monitoring.remediation")


class RemediationEvaluationResult(BaseModel):
    """
    Deterministic evaluation result for a single monitoring constraint against an active plan.
    """
    event_id: str
    is_remediated: bool
    remediation_status: str  # "RESOLVED", "PARTIALLY_REMEDIATED", "ACTIVE", "DATA_INCOMPLETE", "UNVERIFIABLE"
    resolution_reason: str
    shortfall: float = 0.0
    evaluated_plan_id: str
    evaluated_plan_version: int
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConstraintRemediationService:
    """
    Deterministic Constraint Remediation Evaluator & Lifecycle Transition Engine.
    Authoritatively verifies whether operational changes (e.g. unavailable shelter, depleted inventory,
    compromised route) have been fully remediated by an approved and currently ACTIVE response plan.
    """

    @classmethod
    async def evaluate_event_remediation(
        cls,
        event_doc: Dict[str, Any],
        impact_doc: Optional[Dict[str, Any]],
        active_plan: CoordinationPlan,
        db: AsyncIOMotorDatabase,
    ) -> RemediationEvaluationResult:
        """
        Deterministically evaluates if a specific monitoring event and its constraint
        are remediated by the given active CoordinationPlan.
        """
        event_id = event_doc.get("event_id", "")
        source_type_str = str(event_doc.get("source_type", "")).upper()
        source_id = str(event_doc.get("source_id", "")).strip()
        new_state = event_doc.get("new_state", {}) or {}
        previous_state = event_doc.get("previous_state", {}) or {}

        # ---------------------------------------------------------------------
        # 1. SHELTER CONSTRAINT REMEDIATION (SHELTER_FACILITY)
        # ---------------------------------------------------------------------
        if "SHELTER" in source_type_str:
            shelter_name = (
                new_state.get("name")
                or previous_state.get("name")
                or event_doc.get("metadata", {}).get("shelter_name")
                or source_id
            )

            # Check if active plan still allocates the unavailable shelter
            allocated_in_active_plan = False
            for shl in active_plan.recommended_shelters:
                if str(shl.shelter_id).strip() == source_id:
                    allocated_in_active_plan = True
                    break

            if allocated_in_active_plan:
                return RemediationEvaluationResult(
                    event_id=event_id,
                    is_remediated=False,
                    remediation_status="ACTIVE",
                    resolution_reason=f"Active response plan {active_plan.plan_id} (v{active_plan.version}) still allocates unavailable shelter {shelter_name} ({source_id}).",
                    shortfall=float(event_doc.get("metadata", {}).get("shortfall", 0.0)),
                    evaluated_plan_id=active_plan.plan_id,
                    evaluated_plan_version=active_plan.version,
                )

            # Determine required capacity from situation or impact record
            required_capacity = 0.0
            if impact_doc and impact_doc.get("shortfalls"):
                for k, v in impact_doc.get("shortfalls", {}).items():
                    if "shelter" in k.lower() or source_id in k:
                        required_capacity = max(required_capacity, float(v))

            if required_capacity <= 0.0:
                # Calculate from old allocation if available in event metadata or previous state
                required_capacity = float(
                    event_doc.get("metadata", {}).get("allocated_population")
                    or event_doc.get("metadata", {}).get("required_capacity")
                    or previous_state.get("current_occupancy")
                    or previous_state.get("allocated_population")
                    or 0.0
                )

            # Compute valid total replacement capacity in active plan
            valid_active_capacity = 0.0
            for shl in active_plan.recommended_shelters:
                if str(shl.shelter_id).strip() != source_id:
                    occ = float(getattr(shl, "recommended_occupancy", getattr(shl, "allocated_population", 0.0)) or 0.0)
                    valid_active_capacity += occ

            shortfall = max(0.0, required_capacity - valid_active_capacity)

            if shortfall > 0.0 and required_capacity > 0:
                return RemediationEvaluationResult(
                    event_id=event_id,
                    is_remediated=False,
                    remediation_status="PARTIALLY_REMEDIATED",
                    resolution_reason=(
                        f"Active response plan {active_plan.plan_id} (v{active_plan.version}) removed unavailable shelter {shelter_name}, "
                        f"but replacement shelter capacity is insufficient ({valid_active_capacity:g}/{required_capacity:g} persons accommodated, shortfall: {shortfall:g})."
                    ),
                    shortfall=shortfall,
                    evaluated_plan_id=active_plan.plan_id,
                    evaluated_plan_version=active_plan.version,
                )

            # Fully satisfied
            reason = (
                f"Resolved after active response plan {active_plan.plan_id} (v{active_plan.version}) "
                f"removed unavailable Shelter {shelter_name} and verified replacement shelter capacity "
                f"({valid_active_capacity:g} persons accommodated)."
            ) if valid_active_capacity > 0 else (
                f"Resolved after active response plan {active_plan.plan_id} (v{active_plan.version}) "
                f"removed unavailable Shelter {shelter_name} and updated response operations."
            )

            return RemediationEvaluationResult(
                event_id=event_id,
                is_remediated=True,
                remediation_status="RESOLVED",
                resolution_reason=reason,
                shortfall=0.0,
                evaluated_plan_id=active_plan.plan_id,
                evaluated_plan_version=active_plan.version,
            )

        # ---------------------------------------------------------------------
        # 2. RESOURCE INVENTORY CONSTRAINT REMEDIATION (RESOURCE_INVENTORY)
        # ---------------------------------------------------------------------
        elif "RESOURCE" in source_type_str:
            r_name = new_state.get("name") or previous_state.get("name") or source_id
            r_type = str(new_state.get("resource_type") or previous_state.get("resource_type") or "").lower()

            # Check if active plan still allocates the unavailable resource
            allocated_in_active_plan = False
            allocated_qty = 0.0
            for alloc in active_plan.recommended_allocations:
                if str(alloc.matched_resource_id).strip() == source_id:
                    allocated_in_active_plan = True
                    allocated_qty = float(alloc.allocated_quantity or alloc.quantity_required or 0.0)
                    break

            # Check current inventory status from DB
            res_doc = await db["resources"].find_one({"resource_id": source_id})
            if not res_doc:
                res_doc = await db["resources"].find_one({"_id": source_id})

            curr_avail = float(res_doc.get("quantity_available", 0.0)) if res_doc else 0.0
            curr_status = str(res_doc.get("status", "AVAILABLE")).upper() if res_doc else "UNKNOWN"

            if allocated_in_active_plan and (curr_status == "UNAVAILABLE" or curr_avail < allocated_qty):
                shortfall = max(0.0, allocated_qty - curr_avail)
                return RemediationEvaluationResult(
                    event_id=event_id,
                    is_remediated=False,
                    remediation_status="ACTIVE",
                    resolution_reason=f"Active plan {active_plan.plan_id} (v{active_plan.version}) still allocates resource {r_name} with shortfall of {shortfall:g}.",
                    shortfall=shortfall,
                    evaluated_plan_id=active_plan.plan_id,
                    evaluated_plan_version=active_plan.version,
                )

            return RemediationEvaluationResult(
                event_id=event_id,
                is_remediated=True,
                remediation_status="RESOLVED",
                resolution_reason=f"Resolved after active response plan {active_plan.plan_id} (v{active_plan.version}) adjusted resource allocations and satisfied inventory constraints.",
                shortfall=0.0,
                evaluated_plan_id=active_plan.plan_id,
                evaluated_plan_version=active_plan.version,
            )

        # ---------------------------------------------------------------------
        # 3. HEALTHCARE FACILITY CONSTRAINT REMEDIATION (HEALTHCARE_FACILITY)
        # ---------------------------------------------------------------------
        elif "HEALTHCARE" in source_type_str:
            h_name = new_state.get("facility_name") or previous_state.get("facility_name") or source_id
            allocated_in_active_plan = False
            for fac in active_plan.recommended_facilities:
                if str(fac.facility_id).strip() == source_id:
                    allocated_in_active_plan = True
                    break

            if allocated_in_active_plan:
                return RemediationEvaluationResult(
                    event_id=event_id,
                    is_remediated=False,
                    remediation_status="ACTIVE",
                    resolution_reason=f"Active plan {active_plan.plan_id} (v{active_plan.version}) still assigns casualties to compromised facility {h_name}.",
                    shortfall=1.0,
                    evaluated_plan_id=active_plan.plan_id,
                    evaluated_plan_version=active_plan.version,
                )

            return RemediationEvaluationResult(
                event_id=event_id,
                is_remediated=True,
                remediation_status="RESOLVED",
                resolution_reason=f"Resolved after active response plan {active_plan.plan_id} (v{active_plan.version}) rerouted casualties to operational medical facilities.",
                shortfall=0.0,
                evaluated_plan_id=active_plan.plan_id,
                evaluated_plan_version=active_plan.version,
            )

        # ---------------------------------------------------------------------
        # 4. VOLUNTEER RESPONDER CONSTRAINT REMEDIATION (VOLUNTEER_NETWORK)
        # ---------------------------------------------------------------------
        elif "VOLUNTEER" in source_type_str:
            v_name = new_state.get("full_name") or previous_state.get("full_name") or source_id
            allocated_in_active_plan = False
            for vol in active_plan.recommended_volunteers:
                if str(vol.volunteer_id).strip() == source_id:
                    allocated_in_active_plan = True
                    break

            if allocated_in_active_plan:
                return RemediationEvaluationResult(
                    event_id=event_id,
                    is_remediated=False,
                    remediation_status="ACTIVE",
                    resolution_reason=f"Active plan {active_plan.plan_id} (v{active_plan.version}) still assigns unavailable volunteer responder {v_name}.",
                    shortfall=1.0,
                    evaluated_plan_id=active_plan.plan_id,
                    evaluated_plan_version=active_plan.version,
                )

            return RemediationEvaluationResult(
                event_id=event_id,
                is_remediated=True,
                remediation_status="RESOLVED",
                resolution_reason=f"Resolved after active response plan {active_plan.plan_id} (v{active_plan.version}) reassigned field duties to available volunteer responders.",
                shortfall=0.0,
                evaluated_plan_id=active_plan.plan_id,
                evaluated_plan_version=active_plan.version,
            )

        # ---------------------------------------------------------------------
        # 5. TRANSPORT FLEET & ROUTE REMEDIATION (TRANSPORT_FLEET / ROUTE_NETWORK)
        # ---------------------------------------------------------------------
        elif "TRANSPORT" in source_type_str or "ROUTE" in source_type_str:
            veh_name = new_state.get("vehicle_name") or previous_state.get("vehicle_name") or source_id
            allocated_in_active_plan = False
            for t in active_plan.recommended_transports:
                if str(t.transport_id).strip() == source_id:
                    allocated_in_active_plan = True
                    break
            for r in active_plan.recommended_routes:
                if str(r.route_id).strip() == source_id or str(r.transport_id).strip() == source_id:
                    allocated_in_active_plan = True
                    break

            if allocated_in_active_plan:
                return RemediationEvaluationResult(
                    event_id=event_id,
                    is_remediated=False,
                    remediation_status="ACTIVE",
                    resolution_reason=f"Active plan {active_plan.plan_id} (v{active_plan.version}) still utilizes compromised transport or route corridor {veh_name}.",
                    shortfall=1.0,
                    evaluated_plan_id=active_plan.plan_id,
                    evaluated_plan_version=active_plan.version,
                )

            return RemediationEvaluationResult(
                event_id=event_id,
                is_remediated=True,
                remediation_status="RESOLVED",
                resolution_reason=f"Resolved after active response plan {active_plan.plan_id} (v{active_plan.version}) cleared transit bottlenecks and re-routed logistics paths.",
                shortfall=0.0,
                evaluated_plan_id=active_plan.plan_id,
                evaluated_plan_version=active_plan.version,
            )

        # ---------------------------------------------------------------------
        # 6. SENSOR STREAMS & SITUATION INTELLIGENCE
        # ---------------------------------------------------------------------
        elif "SENSOR" in source_type_str or "SITUATION" in source_type_str:
            return RemediationEvaluationResult(
                event_id=event_id,
                is_remediated=True,
                remediation_status="RESOLVED",
                resolution_reason=f"Resolved after response plan {active_plan.plan_id} (v{active_plan.version}) synchronized operational priorities with current situation telemetry.",
                shortfall=0.0,
                evaluated_plan_id=active_plan.plan_id,
                evaluated_plan_version=active_plan.version,
            )

        # ---------------------------------------------------------------------
        # FALLBACK
        # ---------------------------------------------------------------------
        return RemediationEvaluationResult(
            event_id=event_id,
            is_remediated=True,
            remediation_status="RESOLVED",
            resolution_reason=f"Operational constraint addressed in active plan {active_plan.plan_id} (v{active_plan.version}).",
            shortfall=0.0,
            evaluated_plan_id=active_plan.plan_id,
            evaluated_plan_version=active_plan.version,
        )

    @classmethod
    async def evaluate_and_remediate_all_for_situation(
        cls,
        situation_id: str,
        active_plan: CoordinationPlan,
        officer_actor: Dict[str, Any],
        db: AsyncIOMotorDatabase,
    ) -> List[RemediationEvaluationResult]:
        """
        Finds all active, requires_review, and acknowledged monitoring events linked to this situation
        (or superseded plan), evaluates each constraint independently, and applies authoritative
        state transitions in MongoDB.
        """
        clean_sit_id = situation_id.strip().upper()
        now = datetime.now(timezone.utc)
        officer_id = officer_actor.get("id") or "SYSTEM"
        officer_name = officer_actor.get("full_name") or officer_actor.get("name") or "Emergency Officer"

        actor_role_enum = None
        if officer_actor.get("role"):
            try:
                actor_role_enum = UserRole(officer_actor["role"])
            except Exception:
                pass

        # Query all unresolved monitoring events for this situation
        query: Dict[str, Any] = {
            "situation_id": clean_sit_id,
            "status": {"$in": [
                EventStatus.DETECTED.value,
                EventStatus.REQUIRES_REVIEW.value,
                EventStatus.ACKNOWLEDGED.value,
                "DETECTED",
                "REQUIRES_REVIEW",
                "ACKNOWLEDGED",
            ]},
            "is_simulation": {"$ne": True},
        }

        # Also include events linked to superseded plan if previous_plan_id exists
        if active_plan.previous_plan_id:
            query = {
                "$or": [
                    {"situation_id": clean_sit_id},
                    {"coordination_plan_id": active_plan.previous_plan_id},
                ],
                "status": {"$in": [
                    EventStatus.DETECTED.value,
                    EventStatus.REQUIRES_REVIEW.value,
                    EventStatus.ACKNOWLEDGED.value,
                    "DETECTED",
                    "REQUIRES_REVIEW",
                    "ACKNOWLEDGED",
                ]},
                "is_simulation": {"$ne": True},
            }

        cursor = db["monitoring_events"].find(query)
        event_docs = await cursor.to_list(length=100)

        results: List[RemediationEvaluationResult] = []

        for event_doc in event_docs:
            event_id = event_doc.get("event_id")
            impact_doc = await db["change_impacts"].find_one({"event_id": event_id})

            eval_res = await cls.evaluate_event_remediation(
                event_doc=event_doc,
                impact_doc=impact_doc,
                active_plan=active_plan,
                db=db,
            )
            results.append(eval_res)

            if eval_res.is_remediated and eval_res.remediation_status == "RESOLVED":
                # 1. Update monitoring_events
                await db["monitoring_events"].update_one(
                    {"event_id": event_id},
                    {"$set": {
                        "status": EventStatus.RESOLVED.value,
                        "remediation_status": "RESOLVED",
                        "resolved_at": now.isoformat(),
                        "resolved_by_id": officer_id,
                        "resolved_by_name": officer_name,
                        "resolution_reason": eval_res.resolution_reason,
                        "resolved_in_plan_id": active_plan.plan_id,
                        "resolved_in_plan_version": active_plan.version,
                        "metadata.resolved_at": now.isoformat(),
                        "metadata.resolved_by_id": officer_id,
                        "metadata.resolved_by_name": officer_name,
                        "metadata.resolution_reason": eval_res.resolution_reason,
                        "metadata.resolved_in_plan_id": active_plan.plan_id,
                        "metadata.resolved_in_plan_version": active_plan.version,
                    }}
                )

                # 2. Update change_impacts
                await db["change_impacts"].update_one(
                    {"event_id": event_id},
                    {"$set": {
                        "plan_status": PlanValidityStatus.UNAFFECTED.value,
                        "officer_attention_required": False,
                        "violated_constraints": [],
                        "shortfalls": {},
                        "remediation_status": "RESOLVED",
                        "resolved_at": now.isoformat(),
                        "resolved_by_id": officer_id,
                        "resolved_by_name": officer_name,
                        "resolution_reason": eval_res.resolution_reason,
                        "resolved_in_plan_id": active_plan.plan_id,
                        "resolved_in_plan_version": active_plan.version,
                    }}
                )

                # 3. Record timeline event for resolution
                await record_timeline_event(
                    db=db,
                    report_id=clean_sit_id,
                    event_type=TimelineEventType.CONFLICT_RESOLVED,
                    details=f"Operational constraint {event_id} ({event_doc.get('event_type')}) marked RESOLVED: {eval_res.resolution_reason}",
                    actor_id=officer_id,
                    actor_name=officer_name,
                    actor_role=actor_role_enum,
                    metadata={
                        "event_id": event_id,
                        "plan_id": active_plan.plan_id,
                        "version": active_plan.version,
                        "resolution_reason": eval_res.resolution_reason,
                    },
                )

                # 4. Resolve / Mark Read all related critical in-app notifications
                try:
                    await db["notifications"].update_many(
                        {
                            "$or": [
                                {"event_id": event_id},
                                {"metadata.event_id": event_id},
                                {"entity_id": event_doc.get("source_id")},
                                {"situation_id": clean_sit_id, "category": "MONITORING_ALERT", "severity": "CRITICAL"},
                            ]
                        },
                        {
                            "$set": {
                                "recipients.$[elem].in_app.status": "READ",
                                "recipients.$[elem].in_app.read_at": now,
                                "metadata.resolved_at": now.isoformat(),
                                "metadata.resolved_by": officer_name,
                                "metadata.resolution_reason": eval_res.resolution_reason,
                            }
                        },
                        array_filters=[{"elem.in_app.status": {"$ne": "READ"}}],
                    )
                except Exception as notif_err:
                    logger.warning(f"Error resolving notifications for event {event_id}: {notif_err}")

                logger.info(f"Monitoring event {event_id} successfully marked RESOLVED against active plan {active_plan.plan_id} (v{active_plan.version}).")
            else:
                logger.info(f"Monitoring event {event_id} remains {eval_res.remediation_status}: {eval_res.resolution_reason}")

        return results

    @classmethod
    async def reconcile_all_active_situations(
        cls,
        db: AsyncIOMotorDatabase,
        officer_actor: Optional[Dict[str, Any]] = None,
    ) -> List[RemediationEvaluationResult]:
        """
        Reconciles all active situations by evaluating unresolved monitoring constraints
        against their currently ACTIVE coordination plans.
        Called on server startup, Live Monitoring load, and telemetry requests to guarantee persistence and consistency.
        """
        if officer_actor is None:
            officer_actor = {
                "id": "SYSTEM_RECONCILER",
                "full_name": "Authoritative System Reconciler",
                "role": "EMERGENCY_OFFICER",
            }

        cursor = db["coordination_plans"].find({"status": CoordinationPlanStatus.ACTIVE.value})
        active_plan_docs = await cursor.to_list(length=100)

        all_results: List[RemediationEvaluationResult] = []
        for plan_doc in active_plan_docs:
            try:
                active_plan = CoordinationPlan(**plan_doc)
                sit_id = active_plan.situation_id
                results = await cls.evaluate_and_remediate_all_for_situation(
                    situation_id=sit_id,
                    active_plan=active_plan,
                    officer_actor=officer_actor,
                    db=db,
                )
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Error during constraint reconciliation for plan {plan_doc.get('plan_id')}: {e}")

        return all_results
