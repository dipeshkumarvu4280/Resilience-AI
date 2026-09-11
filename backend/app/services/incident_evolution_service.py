import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.enums import (
    IncidentEvolutionCategory,
    TimelineEventType,
    UserRole,
)
from app.models.incident_evolution import (
    IncidentEvolutionEvent,
    IncidentEvolutionTimelineResponse,
)

logger = logging.getLogger("resilience.incident_evolution")


def ensure_utc(dt: Any) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    if isinstance(dt, str):
        try:
            parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception:
            return None
    return None


def map_event_type_to_category(event_type: str) -> IncidentEvolutionCategory:
    et = str(event_type).upper()
    if "REPORT_RECEIVED" in et or "INTAKE" in et:
        return IncidentEvolutionCategory.REPORT
    elif "EVIDENCE" in et or "PHOTO" in et:
        return IncidentEvolutionCategory.EVIDENCE
    elif "SENSOR" in et:
        return IncidentEvolutionCategory.SENSOR
    elif "CONFLICT" in et:
        return IncidentEvolutionCategory.CONFLICT
    elif "CORROBORATION" in et:
        return IncidentEvolutionCategory.CORROBORATION
    elif "FIELD_VERIFICATION" in et or "FIELD_CONDITION" in et or "FIELD_OBSERVATION" in et:
        return IncidentEvolutionCategory.FIELD_VERIFICATION
    elif "ACKNOWLEDGE" in et or "PRIORITY" in et or "NOTE" in et or "ASSESSMENT_REVIEW" in et:
        return IncidentEvolutionCategory.OFFICER_ACTION
    elif "REPLAN" in et or "IMPACT_DETECTED" in et or "INVALIDATION" in et:
        return IncidentEvolutionCategory.REPLANNING
    elif "PLAN" in et or "ORCHESTRATION" in et or "COORDINATION" in et:
        return IncidentEvolutionCategory.RESPONSE_PLAN
    elif "TASK" in et or "RESOURCE_CONSUMED" in et or "VEHICLE" in et or "VOLUNTEER_ASSIGNED" in et or "FIELD_UPDATE" in et:
        return IncidentEvolutionCategory.FIELD_TASK
    elif "RESOLVED" in et or "CLOSED" in et:
        return IncidentEvolutionCategory.RESOLUTION
    else:
        return IncidentEvolutionCategory.OFFICER_ACTION


class IncidentEvolutionService:
    """
    Authoritative read-side aggregator compiling a complete, chronological
    Incident Evolution Timeline from genuine persisted database records.
    Zero fake records, zero duplicate competing collections.
    """

    @classmethod
    async def get_evolution_timeline(
        cls,
        target_id: str,
        db: AsyncIOMotorDatabase,
        order: str = "asc",  # "asc" for chronological, "desc" for reverse
    ) -> IncidentEvolutionTimelineResponse:
        clean_id = target_id.strip().upper()
        now = datetime.now(timezone.utc)
        events_list: List[IncidentEvolutionEvent] = []
        seen_event_ids: Set[str] = set()

        is_situation = clean_id.startswith("SIT-")
        situation_id: Optional[str] = clean_id if is_situation else None
        report_ids: List[str] = []

        if is_situation:
            sit_doc = await db["situations"].find_one({"situation_id": clean_id})
            if sit_doc:
                report_ids = sit_doc.get("report_ids", [])
        else:
            report_ids = [clean_id]
            rep_doc = await db["citizen_reports"].find_one({"report_id": clean_id})
            if rep_doc and rep_doc.get("situation_id"):
                situation_id = rep_doc.get("situation_id")

        # -------------------------------------------------------------
        # 1. Citizen Reports & Embedded Timeline Events
        # -------------------------------------------------------------
        if report_ids:
            reports_cursor = db["citizen_reports"].find({"report_id": {"$in": report_ids}})
            async for r in reports_cursor:
                r_id = r["report_id"]
                r_type = r.get("emergency_type", "Emergency")
                r_created = ensure_utc(r.get("created_at")) or now
                c_name = r.get("citizen_name", "Anonymous Submitter")

                # Intake event
                intake_id = f"EVT-INTAKE-{r_id}"
                if intake_id not in seen_event_ids:
                    seen_event_ids.add(intake_id)
                    events_list.append(IncidentEvolutionEvent(
                        event_id=intake_id,
                        target_id=r_id,
                        target_type="CITIZEN_REPORT",
                        category=IncidentEvolutionCategory.REPORT,
                        event_type="REPORT_RECEIVED",
                        timestamp=r_created,
                        actor_id=r.get("citizen_id"),
                        actor_name=c_name,
                        actor_role="CITIZEN",
                        summary=f"Emergency Report {r_id} ({r_type}) received from {c_name}",
                        details=r.get("description", ""),
                        severity="HIGH" if r.get("citizen_impact_level") in ["HIGH", "CRITICAL"] else "INFO",
                        source_reference=r_id,
                        metadata={
                            "emergency_type": r_type,
                            "impact_level": r.get("citizen_impact_level"),
                            "trust_state": r.get("trust_state"),
                            "location_address": (r.get("location") or {}).get("address"),
                        },
                    ))

                # Live Camera Evidence validation event
                ev_data = r.get("evidence")
                if ev_data:
                    ev_id = f"EVT-EV-{r_id}"
                    if ev_id not in seen_event_ids:
                        seen_event_ids.add(ev_id)
                        v_status = ev_data.get("validation_status", "VALIDATED")
                        events_list.append(IncidentEvolutionEvent(
                            event_id=ev_id,
                            target_id=r_id,
                            target_type="CITIZEN_REPORT",
                            category=IncidentEvolutionCategory.EVIDENCE,
                            event_type="EVIDENCE_VALIDATED",
                            timestamp=ensure_utc(ev_data.get("verified_at")) or r_created,
                            actor_id="SYSTEM_VALIDATOR",
                            actor_name="Evidence Verification Engine",
                            actor_role="SYSTEM",
                            summary=f"Live camera photo validation result: {v_status}",
                            details=f"Distance from report: {ev_data.get('distance_from_report_meters', 0.0):.1f}m. Trust signals: {', '.join(r.get('trust_signals', [])) or 'None'}.",
                            severity="INFO" if v_status in ["VALIDATED", "VERIFIED"] else "HIGH",
                            source_reference=ev_data.get("evidence_id"),
                            metadata={
                                "validation_status": v_status,
                                "content_hash": ev_data.get("content_hash"),
                                "distance_meters": ev_data.get("distance_from_report_meters"),
                            },
                        ))

                # Embedded timeline array
                for tl in r.get("timeline", []):
                    tl_id = tl.get("event_id") or f"EVT-TL-{r_id}-{len(seen_event_ids)}"
                    if tl_id not in seen_event_ids:
                        seen_event_ids.add(tl_id)
                        tl_type = tl.get("event_type", "REPORT_EVENT")
                        events_list.append(IncidentEvolutionEvent(
                            event_id=tl_id,
                            target_id=r_id,
                            target_type="CITIZEN_REPORT",
                            category=map_event_type_to_category(tl_type),
                            event_type=tl_type,
                            timestamp=ensure_utc(tl.get("timestamp")) or r_created,
                            actor_id=tl.get("actor_id"),
                            actor_name=tl.get("actor_name") or "Authorized Operator",
                            actor_role=tl.get("actor_role"),
                            summary=tl.get("details", f"Report updated: {tl_type}"),
                            details=tl.get("details"),
                            severity="INFO",
                            source_reference=r_id,
                            metadata=tl.get("metadata", {}),
                        ))

        # -------------------------------------------------------------
        # 2. Field Officer Live Verifications
        # -------------------------------------------------------------
        fv_query: Dict[str, Any] = {
            "$or": [
                {"target_id": clean_id},
                {"target_id": {"$in": report_ids}},
            ]
        }
        if situation_id:
            fv_query["$or"].append({"metadata.situation_id": situation_id})

        fv_cursor = db["field_verifications"].find(fv_query).sort("submitted_at", 1)
        async for fv in fv_cursor:
            fv_id = fv.get("verification_id", "FLV-UNKNOWN")
            if fv_id not in seen_event_ids:
                seen_event_ids.add(fv_id)
                f_status = fv.get("verification_status", "FIELD_VERIFIED")
                f_obs = fv.get("observation_category", "INCIDENT_CONFIRMED")
                f_actor = fv.get("responder_name", "Field Responder")
                f_role = fv.get("responder_role", "VOLUNTEER")
                dist_m = fv.get("distance_from_target_meters")
                dist_str = f" (~{dist_m:.1f}m from scene)" if dist_m is not None else ""

                events_list.append(IncidentEvolutionEvent(
                    event_id=fv_id,
                    target_id=fv.get("target_id", clean_id),
                    target_type=fv.get("target_type", "CITIZEN_REPORT"),
                    category=IncidentEvolutionCategory.FIELD_VERIFICATION,
                    event_type="FIELD_VERIFICATION_SUBMITTED" if f_status != "CONDITION_CHANGED" else "FIELD_CONDITION_CHANGED",
                    timestamp=ensure_utc(fv.get("submitted_at")) or now,
                    actor_id=fv.get("responder_id"),
                    actor_name=f_actor,
                    actor_role=f_role,
                    summary=f"Field verification by {f_actor} ({f_role}): {f_status} - {f_obs}{dist_str}",
                    details=fv.get("notes") or f"Ground observation status: {f_status}",
                    severity="HIGH" if f_status in ["NOT_FOUND", "CONDITION_CHANGED"] else "INFO",
                    source_reference=fv_id,
                    metadata={
                        "verification_status": f_status,
                        "observation_category": f_obs,
                        "distance_meters": dist_m,
                        "location_match_state": fv.get("location_match_state"),
                        "task_id": fv.get("task_id"),
                    },
                ))

        # -------------------------------------------------------------
        # 3. Centralized Timeline Events & Audit Logs
        # -------------------------------------------------------------
        tl_query: Dict[str, Any] = {
            "$or": [
                {"report_id": clean_id},
                {"report_id": {"$in": report_ids}},
            ]
        }
        if situation_id:
            tl_query["$or"].append({"report_id": situation_id})
            tl_query["$or"].append({"metadata.situation_id": situation_id})

        tl_cursor = db["timeline_events"].find(tl_query).sort("timestamp", 1)
        async for tle in tl_cursor:
            e_id = tle.get("event_id")
            if not e_id or e_id in seen_event_ids:
                continue
            seen_event_ids.add(e_id)
            e_type = tle.get("event_type", "EVENT")
            events_list.append(IncidentEvolutionEvent(
                event_id=e_id,
                target_id=tle.get("report_id", clean_id),
                target_type="SITUATION" if str(tle.get("report_id", "")).startswith("SIT-") else "CITIZEN_REPORT",
                category=map_event_type_to_category(e_type),
                event_type=e_type,
                timestamp=ensure_utc(tle.get("timestamp")) or now,
                actor_id=tle.get("actor_id"),
                actor_name=tle.get("actor_name") or "System / Officer",
                actor_role=tle.get("actor_role"),
                summary=tle.get("details", f"Operational Event: {e_type}"),
                details=tle.get("details"),
                severity="HIGH" if "CONFLICT" in e_type or "ESCALAT" in e_type or "BLOCKED" in e_type else "INFO",
                source_reference=tle.get("report_id"),
                metadata=tle.get("metadata", {}),
            ))

        # -------------------------------------------------------------
        # 4. Live Monitoring Telemetry Events
        # -------------------------------------------------------------
        mon_query: Dict[str, Any] = {
            "$or": [
                {"source_id": clean_id},
                {"source_id": {"$in": report_ids}},
            ]
        }
        if situation_id:
            mon_query["$or"].append({"situation_id": situation_id})

        mon_cursor = db["monitoring_events"].find(mon_query).sort("timestamp", 1)
        async for me in mon_cursor:
            m_id = me.get("event_id")
            if not m_id or m_id in seen_event_ids:
                continue
            seen_event_ids.add(m_id)
            m_type = me.get("event_type", "MONITORING_EVENT")
            actor_dict = me.get("actor") or {}
            events_list.append(IncidentEvolutionEvent(
                event_id=m_id,
                target_id=clean_id,
                target_type="SITUATION" if is_situation else "CITIZEN_REPORT",
                category=map_event_type_to_category(m_type),
                event_type=m_type,
                timestamp=ensure_utc(me.get("timestamp")) or now,
                actor_id=actor_dict.get("id"),
                actor_name=actor_dict.get("full_name") or "Telemetry Engine",
                actor_role=actor_dict.get("role") or "SYSTEM",
                summary=f"Monitoring change event: {m_type}",
                details=f"Impact state: {me.get('impact_level', 'LOW')}. Source: {me.get('source_type')}:{me.get('source_id')}.",
                severity="HIGH" if me.get("impact_level") in ["HIGH", "CRITICAL"] else "INFO",
                source_reference=me.get("source_id"),
                metadata={
                    "source_type": me.get("source_type"),
                    "impact_level": me.get("impact_level"),
                    "plan_status": me.get("plan_status"),
                },
            ))

        # -------------------------------------------------------------
        # 5. Chronological Sorting & Normalization
        # -------------------------------------------------------------
        reverse_flag = (order.lower() == "desc")
        events_list.sort(key=lambda x: x.timestamp, reverse=reverse_flag)

        return IncidentEvolutionTimelineResponse(
            target_id=clean_id,
            target_type="SITUATION" if is_situation else "CITIZEN_REPORT",
            total_events=len(events_list),
            events=events_list,
            generated_at=now,
        )
