import logging
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.models.enums import (
    MonitoringEventType,
    EventSourceType,
    EventStatus,
    ImpactLevel,
    PlanValidityStatus,
    TimelineEventType,
    UserRole,
    CoordinationPlanStatus,
)
from app.models.monitoring import (
    MonitoringEvent,
    ChangeImpactResult,
    PaginatedMonitoringEventsResponse,
    MonitoringStatsResponse,
    AcknowledgeEventResponse,
)
from app.models.agent import CoordinationPlan
from app.services.monitoring.impact_analyzer import ChangeImpactAnalyzer
from app.services.monitoring.remediation_service import ConstraintRemediationService
from app.services.timeline import record_timeline_event

logger = logging.getLogger("resilience.monitoring.service")


def compute_event_fingerprint(
    source_type: EventSourceType,
    source_id: str,
    event_type: MonitoringEventType,
    previous_state: Dict[str, Any],
    new_state: Dict[str, Any],
    time_bucket_minutes: int = 5,
) -> str:
    """
    Computes a deterministic canonical fingerprint (SHA-256) of the state change.
    Groups events within a 5-minute window to avoid duplicate entries from UI polling/refreshes.
    """
    now = datetime.now(timezone.utc)
    # Align to time bucket
    bucket = int(now.timestamp() // (time_bucket_minutes * 60))

    payload = {
        "source_type": source_type.value,
        "source_id": str(source_id).strip().upper(),
        "event_type": event_type.value,
        "prev": previous_state,
        "new": new_state,
        "bucket": bucket,
    }
    canonical_json = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:24]


class MonitoringService:
    """
    Central Monitoring Service for Phase 6.
    Detects state transitions, normalizes events, correlates with situations and active plans,
    executes impact analysis, and maintains an immutable audit trail.
    """

    @classmethod
    async def record_change_event(
        cls,
        event_type: MonitoringEventType,
        source_type: EventSourceType,
        source_id: str,
        previous_state: Dict[str, Any],
        new_state: Dict[str, Any],
        situation_id: Optional[str] = None,
        coordination_plan_id: Optional[str] = None,
        location: Optional[Dict[str, Any]] = None,
        actor: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> Optional[MonitoringEvent]:
        """
        Main entry point for reporting any operational change in the system.
        """
        if db is None:
            db = get_database()

        # 1. Determine changed fields deterministically
        all_keys = set(previous_state.keys()) | set(new_state.keys())
        changed_fields = []
        for k in all_keys:
            prev_val = previous_state.get(k)
            new_val = new_state.get(k)
            if prev_val != new_val:
                changed_fields.append(k)

        # Zero-change invariant: if nothing changed, do not emit false positive event
        if not changed_fields and previous_state and new_state:
            logger.debug(f"Zero-change detected for {source_type.value}:{source_id}. Skipping event creation.")
            return None

        # 2. Compute canonical deduplication fingerprint
        fingerprint = compute_event_fingerprint(
            source_type=source_type,
            source_id=source_id,
            event_type=event_type,
            previous_state=previous_state,
            new_state=new_state,
        )

        # 3. Check for existing deduplicated event within the time window
        existing_doc = await db["monitoring_events"].find_one({"event_fingerprint": fingerprint})
        if existing_doc:
            logger.info(f"Deduplicated monitoring event with fingerprint {fingerprint} for {source_id}.")
            return MonitoringEvent(**existing_doc)

        event_id = f"EVT-{uuid.uuid4().hex[:10].upper()}"

        # 4. Situation Correlation: If situation_id not provided, attempt to resolve from DB
        correlated_sit_id = situation_id
        situation_doc = None
        if not correlated_sit_id:
            if source_type == EventSourceType.SITUATION_INTELLIGENCE:
                correlated_sit_id = source_id
            elif source_type == EventSourceType.CITIZEN_REPORT:
                sit = await db["situations"].find_one({
                    "$or": [
                        {"report_ids": source_id},
                        {"member_report_ids": source_id},
                        {"primary_report_id": source_id},
                    ],
                    "status": {"$in": ["ACTIVE", "MONITORING"]}
                })
                if sit:
                    correlated_sit_id = sit.get("situation_id")
            elif source_type in [
                EventSourceType.RESOURCE_INVENTORY,
                EventSourceType.SHELTER_FACILITY,
                EventSourceType.HEALTHCARE_FACILITY,
                EventSourceType.VOLUNTEER_NETWORK,
                EventSourceType.TRANSPORT_FLEET,
            ]:
                # Correlate with active situation if this entity is referenced in active plans
                plan_with_entity = await db["coordination_plans"].find_one({
                    "status": {"$in": [
                        CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
                        CoordinationPlanStatus.APPROVED.value,
                        CoordinationPlanStatus.MODIFIED.value,
                    ]},
                    "$or": [
                        {"recommended_allocations.matched_resource_id": source_id},
                        {"recommended_shelters.shelter_id": source_id},
                        {"recommended_facilities.facility_id": source_id},
                        {"recommended_volunteers.volunteer_id": source_id},
                        {"recommended_transports.transport_id": source_id},
                    ]
                }, sort=[("generated_at", -1)])
                if plan_with_entity:
                    correlated_sit_id = plan_with_entity.get("situation_id")
                    if not coordination_plan_id:
                        coordination_plan_id = plan_with_entity.get("plan_id")

        if correlated_sit_id:
            situation_doc = await db["situations"].find_one({"situation_id": correlated_sit_id})

        # 5. Active Plan Correlation
        active_plan_obj: Optional[CoordinationPlan] = None
        if correlated_sit_id and not coordination_plan_id:
            plan_doc = await db["coordination_plans"].find_one({
                "situation_id": correlated_sit_id,
                "status": {"$in": [
                    CoordinationPlanStatus.PENDING_OFFICER_REVIEW.value,
                    CoordinationPlanStatus.APPROVED.value,
                    CoordinationPlanStatus.MODIFIED.value,
                ]}
            }, sort=[("generated_at", -1)])
            if plan_doc:
                coordination_plan_id = plan_doc.get("plan_id")
                try:
                    active_plan_obj = CoordinationPlan(**plan_doc)
                except Exception as e:
                    logger.warning(f"Could not parse CoordinationPlan {coordination_plan_id}: {e}")
        elif coordination_plan_id:
            plan_doc = await db["coordination_plans"].find_one({"plan_id": coordination_plan_id})
            if plan_doc:
                try:
                    active_plan_obj = CoordinationPlan(**plan_doc)
                except Exception as e:
                    logger.warning(f"Could not parse CoordinationPlan {coordination_plan_id}: {e}")

        # Construct normalized MonitoringEvent
        event = MonitoringEvent(
            event_id=event_id,
            event_type=event_type,
            source_type=source_type,
            source_id=source_id,
            situation_id=correlated_sit_id,
            coordination_plan_id=coordination_plan_id,
            detected_at=datetime.now(timezone.utc),
            effective_at=datetime.now(timezone.utc),
            previous_state=previous_state,
            new_state=new_state,
            changed_fields=changed_fields,
            location=location,
            metadata=metadata or {},
            event_fingerprint=fingerprint,
            is_simulation=bool((metadata or {}).get("is_simulation", False)),
            actor_id=actor.get("id") if actor else None,
            actor_name=actor.get("full_name") or actor.get("name") if actor else None,
            actor_role=actor.get("role") if actor else None,
            status=EventStatus.DETECTED,
            impact_level=ImpactLevel.NONE,
        )

        # 6. Execute Deterministic Change Impact Analysis
        impact_result = await ChangeImpactAnalyzer.analyze_impact(
            event=event,
            situation=situation_doc,
            active_plan=active_plan_obj,
            db=db,
        )

        # Update event with assessed impact level and status
        event.impact_level = impact_result.impact_level
        if impact_result.officer_attention_required:
            event.status = EventStatus.REQUIRES_REVIEW
        else:
            event.status = EventStatus.ANALYZED

        # 7. Persist MonitoringEvent and ChangeImpactResult
        await db["monitoring_events"].insert_one(event.model_dump())
        await db["change_impacts"].insert_one(impact_result.model_dump())

        # 8. Record Immutable Timeline Audit Record
        audit_actor_role = None
        if actor and actor.get("role"):
            try:
                audit_actor_role = UserRole(actor["role"])
            except Exception:
                audit_actor_role = None

        await record_timeline_event(
            db=db,
            report_id=correlated_sit_id or source_id,
            event_type=TimelineEventType.MONITORING_EVENT_DETECTED,
            details=f"Live Monitoring Event {event_id} ({event_type.value}) detected on {source_type.value}:{source_id}. Impact: {impact_result.impact_level.value}. {impact_result.explanation}",
            actor_id=event.actor_id,
            actor_name=event.actor_name,
            actor_role=audit_actor_role,
        )

        if impact_result.officer_attention_required:
            await record_timeline_event(
                db=db,
                report_id=correlated_sit_id or source_id,
                event_type=TimelineEventType.OFFICER_ATTENTION_REQUIRED,
                details=f"Officer Review Required for situation {correlated_sit_id} / plan {coordination_plan_id}: {'; '.join(impact_result.violated_constraints)}",
                actor_id="SYSTEM",
                actor_name="Central Monitoring Engine",
                actor_role=None,
            )

        # 9. Phase 2: Live Citizen Safety Dynamic Guidance Re-evaluation Loop
        try:
            from app.services.agents.adapters.safety_guidance_agent import SafetyGuidanceAgent
            await SafetyGuidanceAgent.evaluate_and_update_guidance_for_event(
                event=event,
                impact=impact_result,
                db=db,
            )
        except Exception as sg_err:
            logger.warning(f"Error in dynamic citizen safety re-evaluation for event {event_id}: {sg_err}")

        # Phase 7: Event-Driven Notification Dispatch
        requires_replanning = impact_result.plan_status in [
            PlanValidityStatus.INVALIDATED,
            PlanValidityStatus.REQUIRES_OFFICER_REVIEW,
        ]
        if (
            impact_result.impact_level in [ImpactLevel.HIGH, ImpactLevel.CRITICAL]
            or impact_result.officer_attention_required
            or requires_replanning
        ):
            try:
                from app.services.notification import get_notification_service
                from app.models.enums import NotificationCategory, NotificationSeverity, UserRole

                notif_sev = (
                    NotificationSeverity.CRITICAL
                    if impact_result.impact_level == ImpactLevel.CRITICAL
                    else NotificationSeverity.HIGH
                )

                # Categorize based on domain or source
                category = NotificationCategory.LIVE_MONITORING
                if requires_replanning:
                    category = NotificationCategory.DYNAMIC_REPLANNING
                elif source_type == EventSourceType.RESOURCE_INVENTORY:
                    category = NotificationCategory.RESOURCE_LOGISTICS
                elif source_type == EventSourceType.SHELTER_FACILITY:
                    category = NotificationCategory.SHELTER_OPS
                elif source_type == EventSourceType.HEALTHCARE_FACILITY:
                    category = NotificationCategory.HEALTHCARE_OPS
                elif source_type == EventSourceType.VOLUNTEER_NETWORK:
                    category = NotificationCategory.VOLUNTEER_OPS
                elif source_type in [EventSourceType.TRANSPORT_FLEET, EventSourceType.ROUTE_NETWORK]:
                    category = NotificationCategory.TRANSPORT_ROUTE

                notif_service = get_notification_service()
                await notif_service.dispatch_event(
                    category=category,
                    event_type=event_type.value if hasattr(event_type, "value") else str(event_type),
                    severity=notif_sev,
                    title=f"Monitoring Alert [{impact_result.impact_level.value}]: {event_type.value if hasattr(event_type, 'value') else event_type}",
                    message=impact_result.explanation or f"Event detected on {source_type.value}:{source_id}",
                    event_id=event_id,
                    entity_type=source_type.value if hasattr(source_type, "value") else str(source_type),
                    entity_id=source_id,
                    situation_id=correlated_sit_id,
                    coordination_plan_id=coordination_plan_id,
                    view_hint="monitoring",
                    target_roles=[UserRole.EMERGENCY_OFFICER, UserRole.ADMIN],
                    is_simulation=bool(event.is_simulation),
                    material_state={
                        "event_id": event_id,
                        "impact_level": impact_result.impact_level.value,
                        "plan_status": impact_result.plan_status.value,
                        "violated_constraints": impact_result.violated_constraints,
                    },
                    metadata={
                        "event_id": event_id,
                        "source_type": source_type.value if hasattr(source_type, "value") else str(source_type),
                        "source_id": source_id,
                        "shortfall_details": "; ".join(impact_result.violated_constraints) if impact_result.violated_constraints else None,
                    },
                    db=db,
                )
            except Exception as notif_err:
                logger.warning(f"Notification dispatch notice on monitoring event {event_id}: {notif_err}")

        logger.info(
            f"Successfully logged MonitoringEvent {event_id} on {source_type.value}:{source_id} "
            f"(Impact: {event.impact_level.value}, Plan Status: {impact_result.plan_status.value})"
        )
        return event

    @classmethod
    async def get_monitoring_events(
        cls,
        page: int = 1,
        limit: int = 20,
        event_type: Optional[str] = None,
        source_type: Optional[str] = None,
        impact_level: Optional[str] = None,
        status: Optional[str] = None,
        situation_id: Optional[str] = None,
        coordination_plan_id: Optional[str] = None,
        is_impacted: Optional[bool] = None,
        search: Optional[str] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> PaginatedMonitoringEventsResponse:
        if db is None:
            db = get_database()

        # Proactively evaluate and reconcile unresolved constraints against current active plans
        try:
            await ConstraintRemediationService.reconcile_all_active_situations(db)
        except Exception as rec_err:
            logger.warning(f"Monitoring events auto-reconciliation non-fatal error: {rec_err}")

        query: Dict[str, Any] = {"is_simulation": {"$ne": True}}
        if event_type and event_type != "ALL":
            query["event_type"] = event_type
        if source_type and source_type != "ALL":
            query["source_type"] = source_type
        if impact_level and impact_level != "ALL":
            if "," in impact_level:
                query["impact_level"] = {"$in": [lvl.strip().upper() for lvl in impact_level.split(",")]}
            else:
                query["impact_level"] = impact_level.strip().upper()
        if status and status != "ALL":
            query["status"] = status.strip().upper()
        if situation_id:
            query["situation_id"] = situation_id.strip().upper()
        if coordination_plan_id:
            query["coordination_plan_id"] = coordination_plan_id.strip().upper()

        if is_impacted:
            query["status"] = {"$ne": EventStatus.RESOLVED.value}
            query["$or"] = [
                {"impact_level": {"$in": [ImpactLevel.CRITICAL.value, ImpactLevel.HIGH.value]}},
                {"status": EventStatus.REQUIRES_REVIEW.value},
            ]

        if search and search.strip():
            search_regex = {"$regex": search.strip(), "$options": "i"}
            search_clauses = [
                {"event_id": search_regex},
                {"source_id": search_regex},
                {"event_type": search_regex},
                {"situation_id": search_regex},
                {"coordination_plan_id": search_regex},
            ]
            if "$or" in query:
                query = {"$and": [query, {"$or": search_clauses}]}
            else:
                query["$or"] = search_clauses

        skip = (max(1, page) - 1) * limit
        total_count = await db["monitoring_events"].count_documents(query)
        cursor = db["monitoring_events"].find(query).sort("detected_at", -1).skip(skip).limit(limit)
        items_raw = await cursor.to_list(length=limit)

        items = [MonitoringEvent(**item) for item in items_raw]
        total_pages = max(1, (total_count + limit - 1) // limit)

        return PaginatedMonitoringEventsResponse(
            items=items,
            total_count=total_count,
            page=page,
            limit=limit,
            total_pages=total_pages,
        )

    @classmethod
    async def get_event_by_id(
        cls,
        event_id: str,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> Optional[MonitoringEvent]:
        if db is None:
            db = get_database()
        doc = await db["monitoring_events"].find_one({"event_id": event_id})
        return MonitoringEvent(**doc) if doc else None

    @classmethod
    async def get_event_impact(
        cls,
        event_id: str,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> Optional[ChangeImpactResult]:
        if db is None:
            db = get_database()
        doc = await db["change_impacts"].find_one({"event_id": event_id})
        return ChangeImpactResult(**doc) if doc else None

    @classmethod
    async def list_recent_impacts(
        cls,
        limit: int = 50,
        situation_id: Optional[str] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> List[ChangeImpactResult]:
        if db is None:
            db = get_database()
        query: Dict[str, Any] = {}
        if situation_id:
            query["situation_id"] = situation_id
        cursor = db["change_impacts"].find(query).sort("analyzed_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [ChangeImpactResult(**d) for d in docs]

    @classmethod
    async def acknowledge_event(
        cls,
        event_id: str,
        actor: Dict[str, Any],
        notes: Optional[str] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> AcknowledgeEventResponse:
        if db is None:
            db = get_database()

        now = datetime.now(timezone.utc)
        actor_name = actor.get("full_name") or actor.get("name") or "Emergency Officer"
        actor_id = actor.get("id") or "UNKNOWN_OFFICER"

        result = await db["monitoring_events"].update_one(
            {"event_id": event_id},
            {"$set": {
                "status": EventStatus.ACKNOWLEDGED.value,
                "metadata.acknowledged_at": now.isoformat(),
                "metadata.acknowledged_by_id": actor_id,
                "metadata.acknowledged_by_name": actor_name,
                "metadata.officer_notes": notes,
            }}
        )

        if result.matched_count == 0:
            raise ValueError(f"Monitoring event {event_id} not found.")

        await db["change_impacts"].update_one(
            {"event_id": event_id},
            {"$set": {
                "acknowledged_at": now,
                "acknowledged_by_id": actor_id,
                "acknowledged_by_name": actor_name,
            }}
        )

        actor_role_enum = None
        if actor.get("role"):
            try:
                actor_role_enum = UserRole(actor["role"])
            except Exception:
                pass

        await record_timeline_event(
            db=db,
            report_id=event_id,
            event_type=TimelineEventType.MONITORING_EVENT_ACKNOWLEDGED,
            details=f"Monitoring Alert {event_id} acknowledged by {actor_name}. Notes: {notes or 'No notes.'}",
            actor_id=actor_id,
            actor_name=actor_name,
            actor_role=actor_role_enum,
        )

        return AcknowledgeEventResponse(
            success=True,
            event_id=event_id,
            status=EventStatus.ACKNOWLEDGED,
            acknowledged_at=now,
            acknowledged_by_name=actor_name,
            message="Operational change event acknowledged.",
        )

    @classmethod
    async def get_monitoring_stats(
        cls,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> MonitoringStatsResponse:
        if db is None:
            db = get_database()

        # Proactively evaluate and reconcile unresolved constraints against current active plans
        try:
            await ConstraintRemediationService.reconcile_all_active_situations(db)
        except Exception as rec_err:
            logger.warning(f"Monitoring stats auto-reconciliation non-fatal error: {rec_err}")

        base_filter = {"is_simulation": {"$ne": True}}
        total_events = await db["monitoring_events"].count_documents(base_filter)
        active_alerts = await db["monitoring_events"].count_documents({
            **base_filter,
            "status": {"$in": [EventStatus.DETECTED.value, EventStatus.REQUIRES_REVIEW.value]}
        })
        critical_impacts = await db["monitoring_events"].count_documents({
            **base_filter,
            "status": {"$ne": EventStatus.RESOLVED.value},
            "impact_level": ImpactLevel.CRITICAL.value
        })
        high_impacts = await db["monitoring_events"].count_documents({
            **base_filter,
            "status": {"$ne": EventStatus.RESOLVED.value},
            "impact_level": ImpactLevel.HIGH.value
        })
        invalidated_plans = await db["change_impacts"].count_documents({
            **base_filter,
            "plan_status": "INVALIDATED",
            "remediation_status": {"$ne": "RESOLVED"}
        })
        plans_requiring_review = await db["change_impacts"].count_documents({
            **base_filter,
            "officer_attention_required": True,
            "remediation_status": {"$ne": "RESOLVED"}
        })
        impacted_operations_count = await db["monitoring_events"].count_documents({
            **base_filter,
            "status": {"$ne": EventStatus.RESOLVED.value},
            "$or": [
                {"impact_level": {"$in": [ImpactLevel.CRITICAL.value, ImpactLevel.HIGH.value]}},
                {"status": EventStatus.REQUIRES_REVIEW.value},
            ]
        })
        resolved = await db["monitoring_events"].count_documents({
            **base_filter,
            "status": EventStatus.RESOLVED.value
        })
        unack = await db["monitoring_events"].count_documents({
            **base_filter,
            "status": {"$nin": [EventStatus.ACKNOWLEDGED.value, EventStatus.RESOLVED.value]}
        })
        ack = await db["monitoring_events"].count_documents({
            **base_filter,
            "status": EventStatus.ACKNOWLEDGED.value
        })

        # Breakdown by source domain
        pipeline = [
            {"$match": base_filter},
            {"$group": {"_id": "$source_type", "count": {"$sum": 1}}}
        ]
        breakdown_cursor = db["monitoring_events"].aggregate(pipeline)
        domain_breakdown = {}
        async for doc in breakdown_cursor:
            domain_breakdown[doc["_id"]] = doc["count"]

        return MonitoringStatsResponse(
            total_events=total_events,
            active_alerts=active_alerts,
            critical_impacts=critical_impacts,
            high_impacts=high_impacts,
            invalidated_plans=invalidated_plans,
            plans_requiring_review=plans_requiring_review,
            impacted_operations_count=impacted_operations_count,
            unacknowledged_events=unack,
            acknowledged_events=ack,
            resolved_events=resolved,
            domain_breakdown=domain_breakdown,
        )
