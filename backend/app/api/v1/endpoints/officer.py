import os
import base64
import hashlib
import logging
import secrets
import math
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.db.mongodb import get_database
from app.api.deps import require_officer
from app.models.user import UserResponse, VolunteerProfile
from app.models.enums import (
    EmergencyType,
    ReportStatus,
    ReportPriority,
    TimelineEventType,
    UserRole,
    MonitoringEventType,
    EventSourceType,
    SituationStatus,
    CitizenImpactLevel,
    EvidenceValidationStatus,
    ReportTrustState,
)
from app.services.monitoring.monitoring_service import MonitoringService
from app.services.evidence_verification_service import EvidenceVerificationService

from app.models.citizen import LocationPayload, MediaAttachment, LiveEvidenceRecord
from app.models.visual_evidence import VisualAnalysisStatus
from app.models.officer import (
    OfficerNote,
    TimelineEvent,
    ReportPriorityUpdateRequest,
    ReportStatusUpdateRequest,
    ReportRejectionMetadata,
    ReportRejectRequest,
    ReportRejectNotificationInfo,
    ReportRejectResponse,
    OfficerNoteCreateRequest,
    OfficerReportStatsResponse,
    OfficerReportDetailResponse,
    PaginatedOfficerReportsResponse,
)
from app.models.agent import (
    OrchestrateSituationRequest,
    PlanReviewRequest,
    CoordinationPlan,
    ConflictResolutionSummary,
    RecommendedShelter,
    ShelterCoordinationSummary,
    HealthcareCoordinationSummary,
    VolunteerCoordinationSummary,
    RouteTransportCoordinationSummary,
)
from app.services.agents.orchestrator import central_orchestrator
from app.services.timeline import (
    record_timeline_event,
    validate_status_transition,
    generate_event_id,
)

logger = logging.getLogger("resilience.officer")
router = APIRouter()


def generate_note_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"NOT-{suffix}"


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
    return dt


from app.models.corroboration import CorroborationResult
from app.models.llm_extraction import LLMExtractionResult
from app.models.visual_evidence import VisualEvidenceAnalysis
from app.services.corroboration_service import EvidenceCorroborationService
from app.services.severity_engine import calculate_explainable_severity
from app.models.enums import SeverityLevel


def parse_report_document(doc: Optional[dict], corroboration: Optional[CorroborationResult] = None) -> OfficerReportDetailResponse:
    if not doc:
        doc = {}
    # Ensure priority field has a safe default
    priority_val = doc.get("priority", ReportPriority.UNASSESSED.value)
    try:
        priority_enum = ReportPriority(priority_val)
    except Exception:
        priority_enum = ReportPriority.UNASSESSED

    # Parse notes
    notes_list: List[OfficerNote] = []
    for n in doc.get("notes", []):
        try:
            note_obj = OfficerNote(
                note_id=n["note_id"],
                author_id=n["author_id"],
                author_name=n["author_name"],
                author_role=UserRole(n["author_role"]),
                note=n["note"],
                created_at=ensure_utc(n.get("created_at")),
            )
            notes_list.append(note_obj)
        except Exception:
            pass

    # Sort notes chronologically
    notes_list.sort(key=lambda n: (n.created_at or datetime.min.replace(tzinfo=timezone.utc), n.note_id))

    # Parse timeline
    timeline_list: List[TimelineEvent] = []
    for t in doc.get("timeline", []):
        try:
            timeline_list.append(TimelineEvent(
                event_id=t["event_id"],
                event_type=TimelineEventType(t["event_type"]),
                actor_id=t.get("actor_id"),
                actor_name=t.get("actor_name"),
                actor_role=t.get("actor_role"),
                details=t["details"],
                previous_value=t.get("previous_value"),
                new_value=t.get("new_value"),
                timestamp=ensure_utc(t.get("timestamp")),
            ))
        except Exception:
            pass

    # If timeline is empty (e.g. from Phase 1 report), synthesize initial creation event
    if not timeline_list:
        timeline_list.append(TimelineEvent(
            event_id=f"EVT-INIT-{doc['report_id'][-6:]}",
            event_type=TimelineEventType.REPORT_RECEIVED,
            actor_id=doc.get("citizen_id"),
            actor_name=doc.get("citizen_name"),
            actor_role="CITIZEN",
            details="Citizen emergency report submitted into Resilience intake stream.",
            previous_value=None,
            new_value=doc.get("status", ReportStatus.RECEIVED.value),
            timestamp=ensure_utc(doc.get("created_at")),
        ))

    # Sort timeline chronologically by canonical timestamp with deterministic tiebreaker
    timeline_list.sort(key=lambda t: (t.timestamp or datetime.min.replace(tzinfo=timezone.utc), t.event_id))

    raw_et = doc.get("emergency_type", EmergencyType.OTHER.value)
    et_enum = EmergencyType(raw_et) if raw_et in [e.value for e in EmergencyType] else EmergencyType.OTHER

    raw_st = doc.get("status", ReportStatus.RECEIVED.value)
    st_enum = ReportStatus(raw_st) if raw_st in [s.value for s in ReportStatus] else ReportStatus.RECEIVED

    loc_dict = doc.get("location")
    if isinstance(loc_dict, dict):
        loc_obj = LocationPayload(**loc_dict)
    else:
        loc_obj = LocationPayload(
            latitude=float(doc.get("latitude", 16.2415)),
            longitude=float(doc.get("longitude", 80.6433)),
            address=doc.get("location_summary") or doc.get("address") or "Operational Zone"
        )

    raw_impact = doc.get("citizen_impact_level", CitizenImpactLevel.NOT_SURE.value)
    try:
        impact_enum = CitizenImpactLevel(raw_impact)
    except Exception:
        impact_enum = CitizenImpactLevel.NOT_SURE

    evidence_doc = doc.get("evidence")
    evidence_obj = None
    if isinstance(evidence_doc, dict):
        try:
            evidence_obj = LiveEvidenceRecord(**evidence_doc)
        except Exception:
            pass

    raw_trust = doc.get("trust_state", ReportTrustState.NORMAL.value)
    try:
        trust_enum = ReportTrustState(raw_trust)
    except Exception:
        trust_enum = ReportTrustState.NORMAL

    # Evaluate authoritative evidence verification
    evidence_verification_obj = EvidenceVerificationService.evaluate_report_evidence(doc)

    # Parse visual evidence
    vis_doc = doc.get("visual_evidence")
    vis_obj: Optional[VisualEvidenceAnalysis] = None
    if isinstance(vis_doc, dict):
        try:
            vis_obj = VisualEvidenceAnalysis(**vis_doc)
        except Exception:
            pass

    # Parse LLM extraction
    llm_doc = doc.get("llm_extraction")
    llm_obj: Optional[LLMExtractionResult] = None
    if isinstance(llm_doc, dict):
        try:
            llm_obj = LLMExtractionResult(**llm_doc)
        except Exception:
            pass

    # Compute explainable priority recommendation
    priority_rec = doc.get("priority_recommendation")
    if not priority_rec:
        factors: List[str] = []
        unverified: List[str] = []
        uncertainties: List[str] = []

        sev_score, sev_lvl, key_factors = calculate_explainable_severity(
            emergency_type=raw_et,
            descriptions=[doc.get("description", "")],
            report_count=1,
        )
        for kf in key_factors:
            factors.append(kf)

        if vis_obj and vis_obj.status.value == "SUCCESS":
            factors.append(f"Observable {vis_obj.hazard_type.value} conditions visually detected.")
            for ce in vis_obj.claim_evaluations:
                if ce.status.value == "SUPPORTED":
                    factors.append(f"Claim confirmed: \"{ce.claim_text}\" ({ce.visual_observation})")
                elif ce.status.value == "NOT_OBSERVABLE":
                    unverified.append(f"Claim \"{ce.claim_text}\" not observable in frame ({ce.visual_observation})")
                elif ce.status.value == "CONTRADICTED":
                    unverified.append(f"Visual inconsistency: \"{ce.claim_text}\" ({ce.visual_observation})")
            for inf in vis_obj.infrastructure_conditions:
                if inf.is_access_blocked or inf.condition.upper() in ["SUBMERGED", "COLLAPSED", "BLOCKED", "DAMAGED"]:
                    factors.append(f"Infrastructure {inf.infrastructure_type} {inf.condition} (Access blocked: {inf.is_access_blocked})")
                    if inf.is_access_blocked and sev_score < 7.5:
                        sev_score = min(8.5, sev_score + 1.0)
                        if sev_score >= 8.0:
                            sev_lvl = SeverityLevel.HIGH
            for vi in vis_obj.visible_impacts:
                factors.append(f"Visual impact: {vi}")
            for un in vis_obj.uncertainties:
                uncertainties.append(un)

        if evidence_verification_obj:
            if evidence_verification_obj.location_match_state.value in ["MATCH", "NEAR_MATCH"]:
                factors.append("Camera GPS verified and consistent with report.")
            if evidence_verification_obj.evidence_freshness.value == "FRESH":
                factors.append("Evidence capture timestamp is fresh (< 30m).")

        priority_rec = {
            "recommended_priority": sev_lvl.value,
            "score": round(sev_score, 1),
            "evidence_aware": bool(vis_obj and vis_obj.status.value == "SUCCESS"),
            "text_image_consistency": vis_obj.text_image_consistency.value if vis_obj else "NOT_EVALUATED",
            "evidence_factors": factors,
            "unverified_claims": unverified,
            "uncertainties": uncertainties,
        }

    rejection_doc = doc.get("rejection")
    rejection_meta = None
    if isinstance(rejection_doc, dict):
        try:
            rejection_meta = ReportRejectionMetadata(
                reason=rejection_doc.get("reason", ""),
                rejected_by_user_id=str(rejection_doc.get("rejected_by_user_id", "")),
                rejected_by_name=rejection_doc.get("rejected_by_name", ""),
                rejected_at=ensure_utc(rejection_doc.get("rejected_at")) or datetime.now(timezone.utc),
                role=rejection_doc.get("role", "EMERGENCY_OFFICER"),
            )
        except Exception:
            pass

    return OfficerReportDetailResponse(
        report_id=doc.get("report_id", "UNKNOWN"),
        citizen_id=doc.get("citizen_id", "CIT-ANON"),
        citizen_name=doc.get("citizen_name", "Anonymous Citizen"),
        citizen_phone=doc.get("citizen_phone", "9999999999"),
        emergency_type=et_enum,
        citizen_impact_level=impact_enum,
        description=doc.get("description", "Emergency report"),
        location=loc_obj,
        media=[MediaAttachment(**m) for m in doc.get("media", []) if isinstance(m, dict)],
        evidence=evidence_obj,
        evidence_verification=evidence_verification_obj,
        corroboration=corroboration,
        llm_extraction=llm_obj,
        visual_evidence=vis_obj,
        priority_recommendation=priority_rec,
        status=st_enum,
        priority=priority_enum,
        phone_verified=doc.get("phone_verified", False),
        possible_duplicate=doc.get("possible_duplicate", False),
        risk_level=doc.get("risk_level", "LOW"),
        risk_reasons=doc.get("risk_reasons", []),
        trust_state=trust_enum,
        trust_signals=doc.get("trust_signals", []),
        acknowledged_at=ensure_utc(doc.get("acknowledged_at")),
        acknowledged_by=doc.get("acknowledged_by"),
        rejected_at=ensure_utc(doc.get("rejected_at")),
        rejected_by=doc.get("rejected_by"),
        rejection_reason=doc.get("rejection_reason") or (rejection_meta.reason if rejection_meta else None),
        rejection=rejection_meta,
        situation_id=doc.get("situation_id"),
        notes=notes_list,
        timeline=timeline_list,
        created_at=ensure_utc(doc.get("created_at")),
        updated_at=ensure_utc(doc.get("updated_at")),
    )



@router.get("/reports/stats", response_model=OfficerReportStatsResponse)
async def get_officer_report_stats(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get live real-time report count statistics directly from MongoDB.
    No hardcoded numbers or dummy counts.
    """
    total_incoming = await db["citizen_reports"].count_documents({"status": ReportStatus.RECEIVED.value})
    acknowledged = await db["citizen_reports"].count_documents({"status": ReportStatus.ACKNOWLEDGED.value})
    under_assessment = await db["citizen_reports"].count_documents({"status": ReportStatus.UNDER_ASSESSMENT.value})
    action_required = await db["citizen_reports"].count_documents({"status": ReportStatus.ACTION_REQUIRED.value})
    resolved = await db["citizen_reports"].count_documents({"status": ReportStatus.RESOLVED.value})
    rejected = await db["citizen_reports"].count_documents({"status": ReportStatus.REJECTED.value})
    total_reports = await db["citizen_reports"].count_documents({})

    return OfficerReportStatsResponse(
        total_incoming=total_incoming,
        acknowledged=acknowledged,
        under_assessment=under_assessment,
        action_required=action_required,
        resolved=resolved,
        rejected=rejected,
        total_reports=total_reports,
    )


@router.get("/reports", response_model=PaginatedOfficerReportsResponse)
async def list_officer_reports(
    status_filter: Optional[ReportStatus] = Query(None, alias="status"),
    priority_filter: Optional[ReportPriority] = Query(None, alias="priority"),
    emergency_type: Optional[EmergencyType] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Paginated, searchable, filterable emergency report feed for authorized officers.
    """
    query = {}
    if status_filter:
        query["status"] = status_filter.value
    if priority_filter:
        query["priority"] = priority_filter.value
    if emergency_type:
        query["emergency_type"] = emergency_type.value
    if search and search.strip():
        term = search.strip()
        query["$or"] = [
            {"report_id": {"$regex": term, "$options": "i"}},
            {"citizen_name": {"$regex": term, "$options": "i"}},
            {"citizen_phone": {"$regex": term, "$options": "i"}},
            {"description": {"$regex": term, "$options": "i"}},
            {"location.street_address": {"$regex": term, "$options": "i"}},
            {"location.address": {"$regex": term, "$options": "i"}},
            {"location.zone_or_district": {"$regex": term, "$options": "i"}},
            {"location.city": {"$regex": term, "$options": "i"}},
        ]

    total = await db["citizen_reports"].count_documents(query)
    total_pages = max(1, math.ceil(total / limit))
    skip = (page - 1) * limit

    cursor = db["citizen_reports"].find(query).sort("created_at", -1).skip(skip).limit(limit)
    items = []
    async for doc in cursor:
        items.append(parse_report_document(doc))

    return PaginatedOfficerReportsResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get("/reports/{report_id}", response_model=OfficerReportDetailResponse)
async def get_officer_report(
    report_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get full report details including authoritative location, media, notes, and audit timeline.
    """
    clean_id = report_id.strip().upper()
    doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report '{report_id}' not found in active operational registry.",
        )

    # Idempotent logging of VIEW event: atomic 5-minute cooldown per actor_id and report_id
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=300)
    event_id = generate_event_id()
    actor_role_val = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)

    view_event_doc = {
        "event_id": event_id,
        "event_type": TimelineEventType.REPORT_VIEWED.value,
        "actor_id": current_user.id,
        "actor_name": current_user.full_name,
        "actor_role": actor_role_val,
        "details": f"Report opened for assessment by {current_user.full_name}.",
        "previous_value": None,
        "new_value": None,
        "timestamp": now,
    }

    # Atomic update on citizen_reports: append only if no REPORT_VIEWED for current_user within cutoff
    try:
        update_result = await db["citizen_reports"].update_one(
            {
                "report_id": clean_id,
                "timeline": {
                    "$not": {
                        "$elemMatch": {
                            "event_type": TimelineEventType.REPORT_VIEWED.value,
                            "actor_id": current_user.id,
                            "timestamp": {"$gte": cutoff},
                        }
                    }
                },
            },
            {
                "$push": {"timeline": view_event_doc},
                "$set": {"updated_at": now},
            },
        )

        if update_result.modified_count > 0:
            await db["audit_logs"].insert_one({
                "event_id": event_id,
                "report_id": clean_id,
                "action": TimelineEventType.REPORT_VIEWED.value,
                "actor_id": current_user.id,
                "actor_name": current_user.full_name,
                "actor_role": actor_role_val,
                "details": f"Report opened for assessment by {current_user.full_name}.",
                "timestamp": now,
            })
    except Exception as e:
        logger.warning(f"Failed to record view event for report {clean_id}: {e}")

    # Auto-refresh failed or missing LLM extraction via TextAnalysisRouter (which triggers OpenAI fallback)
    current_llm = doc.get("llm_extraction")
    if (not current_llm or current_llm.get("status") in ["FAILED", "UNAVAILABLE"]) and doc.get("description"):
        try:
            from app.services.text_analysis_router import TextAnalysisRouter
            from app.models.llm_extraction import ExtractionStatus
            router = TextAnalysisRouter.get_instance()
            extraction_res = await router.extract_structured_evidence(
                source_id=clean_id,
                source_type="CITIZEN_REPORT",
                text_content=doc.get("description", ""),
                context_metadata={
                    "emergency_type": doc.get("emergency_type", "UNSPECIFIED"),
                    "location_address": doc.get("location", {}).get("address", "Not provided") if isinstance(doc.get("location"), dict) else "Not provided",
                },
                report_id=clean_id,
            )
            if extraction_res and extraction_res.status == ExtractionStatus.SUCCESS:
                ext_dict = extraction_res.model_dump(mode="json")
                await db["citizen_reports"].update_one(
                    {"report_id": clean_id},
                    {"$set": {"llm_extraction": ext_dict, "updated_at": now}}
                )
                doc["llm_extraction"] = ext_dict
        except Exception as e:
            logger.warning(f"Auto-refresh LLM extraction error for {clean_id}: {e}")

    updated_doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    corrob_res = await EvidenceCorroborationService.get_or_evaluate_report_corroboration(clean_id, db)
    return parse_report_document(updated_doc or doc, corroboration=corrob_res)



@router.post("/reports/{report_id}/acknowledge", response_model=OfficerReportDetailResponse)
async def acknowledge_report(
    report_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Officer acknowledges an incoming report.
    Transitions status to ACKNOWLEDGED, sets timestamp and officer name, records audit event.
    """
    clean_id = report_id.strip().upper()
    doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report '{report_id}' not found.",
        )

    current_status = ReportStatus(doc.get("status", ReportStatus.RECEIVED.value))
    if current_status not in [ReportStatus.RECEIVED, ReportStatus.VERIFIED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot acknowledge report with status '{current_status.value}'. Report has already progressed.",
        )

    now = datetime.now(timezone.utc)
    new_status = ReportStatus.ACKNOWLEDGED

    await db["citizen_reports"].update_one(
        {"report_id": clean_id},
        {
            "$set": {
                "status": new_status.value,
                "acknowledged_at": now,
                "acknowledged_by": current_user.full_name,
                "updated_at": now,
            }
        }
    )

    await record_timeline_event(
        db=db,
        report_id=clean_id,
        event_type=TimelineEventType.REPORT_ACKNOWLEDGED,
        details=f"Incident acknowledged by {current_user.full_name}.",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
        previous_value=current_status.value,
        new_value=new_status.value,
    )

    updated_doc = await db["citizen_reports"].find_one({"report_id": clean_id})

    # Dispatch Phase 6 Monitoring Event
    try:
        await MonitoringService.record_change_event(
            event_type=MonitoringEventType.REPORT_ACKNOWLEDGED,
            source_type=EventSourceType.CITIZEN_REPORT,
            source_id=clean_id,
            previous_state={"status": current_status.value},
            new_state={"status": new_status.value},
            situation_id=doc.get("situation_id"),
            location=doc.get("location"),
            actor={
                "id": current_user.id,
                "full_name": current_user.full_name,
                "role": current_user.role.value,
            },
            db=db,
        )
    except Exception as e:
        logger.warning(f"Failed to record monitoring event for report acknowledgement {clean_id}: {e}")

    # Phase 7: Event-Driven Notification Dispatch
    try:
        from app.services.notification import get_notification_service
        from app.models.enums import NotificationCategory, NotificationSeverity, UserRole
        
        target_ids = []
        if doc.get("citizen_phone"):
            target_ids.append(doc["citizen_phone"])
        if doc.get("citizen_id"):
            target_ids.append(doc["citizen_id"])

        notif_service = get_notification_service()
        await notif_service.dispatch_event(
            category=NotificationCategory.CITIZEN_REPORT,
            event_type="REPORT_ACKNOWLEDGED",
            severity=NotificationSeverity.MEDIUM,
            title=f"Emergency Report Acknowledged: {clean_id}",
            message=f"Report acknowledged by Officer {current_user.full_name}.",
            entity_type="CITIZEN_REPORT",
            entity_id=clean_id,
            situation_id=doc.get("situation_id"),
            view_hint="reports",
            target_user_ids=target_ids if target_ids else None,
            target_roles=[UserRole.EMERGENCY_OFFICER, UserRole.ADMIN],
            material_state={"report_id": clean_id, "status": new_status.value},
            metadata={"report_id": clean_id, "acknowledged_by": current_user.full_name},
        )
    except Exception as notif_err:
        logger.warning(f"Notification dispatch notice for report acknowledgement {clean_id}: {notif_err}")

    # Section 13: Web Push Notification for Report Acknowledgement
    try:
        from app.services.notification.web_push_service import WebPushService
        from app.models.enums import SafetyNotificationType
        await WebPushService.notify_citizen_report_status_update(
            report_id=clean_id,
            notification_type=SafetyNotificationType.REPORT_ACKNOWLEDGED,
            title="Emergency Report Update",
            body=f"Your emergency report {clean_id} has been acknowledged and is now under review.",
            event_id=f"EVT-ACK-PUSH-{clean_id}",
            db=db,
        )
    except Exception as push_err:
        logger.warning(f"Web push dispatch notice for report acknowledgement {clean_id}: {push_err}")

    return parse_report_document(updated_doc)


@router.post("/reports/{report_id}/reject", response_model=ReportRejectResponse)
async def reject_report(
    report_id: str,
    payload: ReportRejectRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Officer rejects an incoming emergency report with a mandatory descriptive reason.
    Removes the report from active operational workflow and Situation Intelligence,
    records an authoritative audit event, updates GIS status, and dispatches Web Push
    notification to the reporting citizen without failing on push network errors.
    """
    clean_id = report_id.strip().upper()
    doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report '{report_id}' not found in registry.",
        )

    # Validate rejection reason
    try:
        cleaned_reason = ReportRejectRequest.validate_reason(payload.reason)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )

    current_status = ReportStatus(doc.get("status", ReportStatus.RECEIVED.value))

    # Idempotency check: if report is already REJECTED
    if current_status == ReportStatus.REJECTED:
        rejection_meta_doc = doc.get("rejection") or {
            "reason": doc.get("rejection_reason") or cleaned_reason,
            "rejected_by_user_id": doc.get("rejected_by_id") or current_user.id,
            "rejected_by_name": doc.get("rejected_by") or current_user.full_name,
            "rejected_at": doc.get("rejected_at") or doc.get("updated_at") or datetime.now(timezone.utc),
            "role": "EMERGENCY_OFFICER",
        }
        rejection_meta = ReportRejectionMetadata(
            reason=rejection_meta_doc.get("reason", cleaned_reason),
            rejected_by_user_id=str(rejection_meta_doc.get("rejected_by_user_id", current_user.id)),
            rejected_by_name=rejection_meta_doc.get("rejected_by_name", current_user.full_name),
            rejected_at=ensure_utc(rejection_meta_doc.get("rejected_at")) or datetime.now(timezone.utc),
            role=rejection_meta_doc.get("role", "EMERGENCY_OFFICER"),
        )
        return ReportRejectResponse(
            success=True,
            report_id=clean_id,
            status=ReportStatus.REJECTED,
            rejection_reason=rejection_meta.reason,
            rejection=rejection_meta,
            notification=ReportRejectNotificationInfo(
                status="NO_SUBSCRIPTION",
                details="Report was already rejected. State is canonical and idempotent."
            ),
            report=parse_report_document(doc),
        )

    # Check if report is in a terminal resolved state
    if current_status == ReportStatus.RESOLVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot reject report '{clean_id}' because it has already reached terminal status 'RESOLVED'.",
        )

    now = datetime.now(timezone.utc)
    new_status = ReportStatus.REJECTED

    rejection_metadata = {
        "reason": cleaned_reason,
        "rejected_by_user_id": current_user.id,
        "rejected_by_name": current_user.full_name,
        "rejected_at": now,
        "role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
    }

    # Atomically persist rejection in MongoDB
    await db["citizen_reports"].update_one(
        {"report_id": clean_id},
        {
            "$set": {
                "status": new_status.value,
                "rejection": rejection_metadata,
                "rejection_reason": cleaned_reason,
                "rejected_at": now,
                "rejected_by": current_user.full_name,
                "rejected_by_id": current_user.id,
                "rejected_by_user_id": current_user.id,
                "updated_at": now,
            }
        }
    )

    # Record authoritative timeline & audit event
    await record_timeline_event(
        db=db,
        report_id=clean_id,
        event_type=TimelineEventType.REPORT_REJECTED,
        details=f"Report rejected by Officer {current_user.full_name}. Reason: {cleaned_reason}",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
        previous_value=current_status.value,
        new_value=new_status.value,
        metadata={"rejection": rejection_metadata, "reason": cleaned_reason},
    )

    # If report was linked to a situation cluster, refresh cluster ground truth & severity
    sit_id = doc.get("situation_id")
    if not sit_id:
        sit_doc = await db["situations"].find_one({"report_ids": clean_id})
        if sit_doc:
            sit_id = sit_doc.get("situation_id")

    if sit_id:
        try:
            from app.services.incident_fusion import refresh_situation_cluster
            await refresh_situation_cluster(db, sit_id)
        except Exception as e:
            logger.warning(f"Could not refresh situation {sit_id} on report rejection {clean_id}: {e}")

    # Dispatch Phase 6 Monitoring Event
    try:
        await MonitoringService.record_change_event(
            event_type=MonitoringEventType.REPORT_REJECTED,
            source_type=EventSourceType.CITIZEN_REPORT,
            source_id=clean_id,
            previous_state={"status": current_status.value},
            new_state={"status": new_status.value, "reason": cleaned_reason},
            situation_id=sit_id,
            location=doc.get("location"),
            actor={
                "id": current_user.id,
                "full_name": current_user.full_name,
                "role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
            },
            db=db,
        )
    except Exception as e:
        logger.warning(f"Failed to record monitoring event for report rejection {clean_id}: {e}")

    # Phase 7: Event-Driven Notification Dispatch to Officers
    try:
        from app.services.notification import get_notification_service
        from app.models.enums import NotificationCategory, NotificationSeverity, UserRole

        notif_service = get_notification_service()
        await notif_service.dispatch_event(
            category=NotificationCategory.CITIZEN_REPORT,
            event_type="REPORT_REJECTED",
            severity=NotificationSeverity.LOW,
            title=f"Emergency Report Rejected: {clean_id}",
            message=f"Report rejected by Officer {current_user.full_name}. Reason: {cleaned_reason}",
            entity_type="CITIZEN_REPORT",
            entity_id=clean_id,
            situation_id=sit_id,
            view_hint="reports",
            target_roles=[UserRole.EMERGENCY_OFFICER, UserRole.ADMIN],
            material_state={"report_id": clean_id, "status": new_status.value},
            metadata={"report_id": clean_id, "rejection_reason": cleaned_reason, "rejected_by": current_user.full_name},
        )
    except Exception as notif_err:
        logger.warning(f"Notification dispatch notice for report rejection {clean_id}: {notif_err}")

    # Section 10 & 11: Real Web Push Notification to Reporting Citizen
    push_result = {"status": "NO_SUBSCRIPTION", "subscribers_notified": 0, "details": "No subscription check run"}
    try:
        from app.services.notification.web_push_service import WebPushService
        from app.models.enums import SafetyNotificationType
        push_result = await WebPushService.notify_citizen_report_status_update(
            report_id=clean_id,
            notification_type=SafetyNotificationType.REPORT_REJECTED,
            title="Emergency Report Update",
            body=f"Your emergency report {clean_id} has been reviewed and rejected.\n\nReason: {cleaned_reason}",
            event_id=f"EVT-REJ-PUSH-{clean_id}",
            data={"rejection_reason": cleaned_reason, "report_id": clean_id, "status": "REJECTED"},
            db=db,
        )
    except Exception as push_err:
        logger.warning(f"Web push dispatch notice for report rejection {clean_id}: {push_err}")
        push_result = {
            "status": "FAILED",
            "subscribers_notified": 0,
            "details": f"Push notification service encountered an error: {push_err}"
        }

    updated_doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    rejection_meta_obj = ReportRejectionMetadata(
        reason=cleaned_reason,
        rejected_by_user_id=current_user.id,
        rejected_by_name=current_user.full_name,
        rejected_at=now,
        role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
    )

    parsed_report = parse_report_document(updated_doc)

    return ReportRejectResponse(
        success=True,
        report_id=clean_id,
        status=ReportStatus.REJECTED,
        rejection_reason=cleaned_reason,
        rejection=rejection_meta_obj,
        notification=ReportRejectNotificationInfo(
            status=push_result.get("status", "NO_SUBSCRIPTION"),
            notification_type="REPORT_REJECTED",
            provider_status=push_result.get("provider_status"),
            subscribers_notified=push_result.get("subscribers_notified", 0),
            details=push_result.get("details"),
        ),
        report=parsed_report,
    )


@router.patch("/reports/{report_id}/priority", response_model=OfficerReportDetailResponse)
async def update_report_priority(
    report_id: str,
    payload: ReportPriorityUpdateRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Update priority level of an emergency report and record audit event.
    """
    clean_id = report_id.strip().upper()
    doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report '{report_id}' not found.",
        )

    prev_priority = doc.get("priority", ReportPriority.UNASSESSED.value)
    now = datetime.now(timezone.utc)

    await db["citizen_reports"].update_one(
        {"report_id": clean_id},
        {
            "$set": {
                "priority": payload.priority.value,
                "updated_at": now,
            }
        }
    )

    await record_timeline_event(
        db=db,
        report_id=clean_id,
        event_type=TimelineEventType.PRIORITY_CHANGED,
        details=f"Priority updated from {prev_priority} to {payload.priority.value} by {current_user.full_name}.",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
        previous_value=str(prev_priority),
        new_value=payload.priority.value,
    )

    # If report is attached to a situation cluster, refresh the cluster's severity ground truth
    sit_id = doc.get("situation_id")
    if sit_id:
        try:
            from app.services.incident_fusion import refresh_situation_cluster
            await refresh_situation_cluster(db, sit_id)
        except Exception as e:
            logger.warning(f"Could not refresh situation {sit_id} on priority update: {e}")

    updated_doc = await db["citizen_reports"].find_one({"report_id": clean_id})

    # Dispatch Phase 6 Monitoring Event
    try:
        await MonitoringService.record_change_event(
            event_type=MonitoringEventType.REPORT_PRIORITY_CHANGED,
            source_type=EventSourceType.CITIZEN_REPORT,
            source_id=clean_id,
            previous_state={"priority": str(prev_priority)},
            new_state={"priority": payload.priority.value},
            situation_id=sit_id,
            location=doc.get("location"),
            actor={
                "id": current_user.id,
                "full_name": current_user.full_name,
                "role": current_user.role.value,
            },
            db=db,
        )
    except Exception as e:
        logger.warning(f"Failed to record monitoring event for priority change on {clean_id}: {e}")

    # Phase 7: Event-Driven Notification Dispatch
    try:
        from app.services.notification import get_notification_service
        from app.models.enums import NotificationCategory, NotificationSeverity, UserRole

        sev_map = {
            ReportPriority.LOW: NotificationSeverity.LOW,
            ReportPriority.MEDIUM: NotificationSeverity.MEDIUM,
            ReportPriority.HIGH: NotificationSeverity.HIGH,
            ReportPriority.CRITICAL: NotificationSeverity.CRITICAL,
        }
        notif_sev = sev_map.get(payload.priority, NotificationSeverity.HIGH)

        notif_service = get_notification_service()
        await notif_service.dispatch_event(
            category=NotificationCategory.CITIZEN_REPORT,
            event_type="REPORT_PRIORITY_CHANGED",
            severity=notif_sev,
            title=f"Report Priority Escalated: {clean_id} [{payload.priority.value}]",
            message=f"Priority updated from {prev_priority} to {payload.priority.value} by {current_user.full_name}.",
            entity_type="CITIZEN_REPORT",
            entity_id=clean_id,
            situation_id=sit_id,
            view_hint="reports",
            target_roles=[UserRole.EMERGENCY_OFFICER, UserRole.ADMIN],
            material_state={"report_id": clean_id, "priority": payload.priority.value},
            metadata={"report_id": clean_id, "new_priority": payload.priority.value},
        )
    except Exception as notif_err:
        logger.warning(f"Notification dispatch notice for report priority change {clean_id}: {notif_err}")

    return parse_report_document(updated_doc or doc)



@router.patch("/reports/{report_id}/status", response_model=OfficerReportDetailResponse)
async def update_report_status(
    report_id: str,
    payload: ReportStatusUpdateRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Enforce and perform controlled operational status transitions.
    """
    clean_id = report_id.strip().upper()
    doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report '{report_id}' not found.",
        )

    current_status = ReportStatus(doc.get("status", ReportStatus.RECEIVED.value))
    if not validate_status_transition(current_status, payload.status):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid operational transition from '{current_status.value}' to '{payload.status.value}'. "
                   f"Must follow controlled Phase 2 workflow progression.",
        )

    now = datetime.now(timezone.utc)
    update_data = {
        "status": payload.status.value,
        "updated_at": now,
    }

    if payload.status == ReportStatus.RESOLVED:
        update_data["resolved_at"] = now
        update_data["resolved_by"] = current_user.full_name
        sit_id = doc.get("situation_id")
        if sit_id:
            active_sit_reports = await db["citizen_reports"].count_documents({
                "situation_id": sit_id,
                "report_id": {"$ne": clean_id},
                "status": {"$ne": ReportStatus.RESOLVED.value}
            })
            if active_sit_reports == 0:
                await db["situations"].update_one(
                    {"situation_id": sit_id},
                    {"$set": {
                        "status": SituationStatus.RESOLVED.value,
                        "updated_at": now,
                        "resolved_at": now,
                        "resolved_by": current_user.full_name,
                    }}
                )

    await db["citizen_reports"].update_one(
        {"report_id": clean_id},
        {"$set": update_data}
    )

    reason_text = f" Reason: {payload.reason}" if payload.reason else ""
    await record_timeline_event(
        db=db,
        report_id=clean_id,
        event_type=TimelineEventType.STATUS_CHANGED,
        details=f"Status transitioned to {payload.status.value} by {current_user.full_name}.{reason_text}",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
        previous_value=current_status.value,
        new_value=payload.status.value,
    )

    updated_doc = await db["citizen_reports"].find_one({"report_id": clean_id})

    # Dispatch Phase 6 Monitoring Event
    try:
        await MonitoringService.record_change_event(
            event_type=MonitoringEventType.REPORT_STATUS_CHANGED,
            source_type=EventSourceType.CITIZEN_REPORT,
            source_id=clean_id,
            previous_state={"status": current_status.value},
            new_state={"status": payload.status.value},
            situation_id=doc.get("situation_id"),
            location=doc.get("location"),
            actor={
                "id": current_user.id,
                "full_name": current_user.full_name,
                "role": current_user.role.value,
            },
            db=db,
        )
    except Exception as e:
        logger.warning(f"Failed to record monitoring event for status change on {clean_id}: {e}")

    # Phase 7: Event-Driven Notification Dispatch
    try:
        from app.services.notification import get_notification_service
        from app.models.enums import NotificationCategory, NotificationSeverity, UserRole

        notif_service = get_notification_service()
        await notif_service.dispatch_event(
            category=NotificationCategory.CITIZEN_REPORT,
            event_type="REPORT_STATUS_CHANGED",
            severity=NotificationSeverity.MEDIUM,
            title=f"Report Status Updated: {clean_id} [{payload.status.value}]",
            message=f"Report transitioned to {payload.status.value} by {current_user.full_name}.{reason_text}",
            entity_type="CITIZEN_REPORT",
            entity_id=clean_id,
            situation_id=doc.get("situation_id"),
            view_hint="reports",
            target_roles=[UserRole.EMERGENCY_OFFICER, UserRole.ADMIN],
            material_state={"report_id": clean_id, "status": payload.status.value},
            metadata={"report_id": clean_id, "new_status": payload.status.value},
        )
    except Exception as notif_err:
        logger.warning(f"Notification dispatch notice for report status change {clean_id}: {notif_err}")

    # Citizen Web Push Notification on Status Update
    try:
        from app.services.notification.web_push_service import WebPushService
        from app.models.enums import SafetyNotificationType
        if payload.status == ReportStatus.ACKNOWLEDGED:
            await WebPushService.notify_citizen_report_status_update(
                report_id=clean_id,
                notification_type=SafetyNotificationType.REPORT_ACKNOWLEDGED,
                title="Emergency Report Update",
                body=f"Your emergency report {clean_id} has been acknowledged and is now under review.",
                event_id=f"EVT-ACK-PUSH-{clean_id}",
                db=db,
            )
        elif payload.status in [ReportStatus.ACTION_REQUIRED, ReportStatus.UNDER_ASSESSMENT]:
            await WebPushService.notify_citizen_report_status_update(
                report_id=clean_id,
                notification_type=SafetyNotificationType.REPORT_ACCEPTED,
                title="Emergency Report Accepted",
                body=f"Your emergency report {clean_id} has been accepted and assigned for response coordination.",
                event_id=f"EVT-ACCEPT-PUSH-{clean_id}-{payload.status.value}",
                db=db,
            )
    except Exception as push_err:
        logger.warning(f"Web push dispatch notice for status transition on {clean_id}: {push_err}")

    return parse_report_document(updated_doc or doc)


@router.post("/reports/{report_id}/notes", response_model=OfficerReportDetailResponse)
async def add_officer_note(
    report_id: str,
    payload: OfficerNoteCreateRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Add operational notes to an emergency report with author metadata.
    """
    clean_id = report_id.strip().upper()
    doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report '{report_id}' not found.",
        )

    note_id = generate_note_id()
    now = datetime.now(timezone.utc)

    note_doc = {
        "note_id": note_id,
        "author_id": current_user.id,
        "author_name": current_user.full_name,
        "author_role": current_user.role.value,
        "note": payload.note.strip(),
        "created_at": now,
    }

    await db["citizen_reports"].update_one(
        {"report_id": clean_id},
        {
            "$push": {"notes": note_doc},
            "$set": {"updated_at": now},
        }
    )

    # Record in audit timeline
    await record_timeline_event(
        db=db,
        report_id=clean_id,
        event_type=TimelineEventType.NOTE_ADDED,
        details=f"Operational note added by {current_user.full_name}: '{payload.note.strip()[:60]}...'",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
    )

    updated_doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    return parse_report_document(updated_doc)


@router.get("/reports/{report_id}/timeline", response_model=List[TimelineEvent])
async def get_report_timeline(
    report_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Retrieve full chronological audit timeline events for an emergency report.
    """
    clean_id = report_id.strip().upper()
    doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report '{report_id}' not found.",
        )

    parsed = parse_report_document(doc)
    return parsed.timeline


@router.post("/reports/{report_id}/analyze-visual-evidence", response_model=OfficerReportDetailResponse)
async def analyze_report_visual_evidence(
    report_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    On-demand officer trigger to analyze / re-evaluate live camera evidence via Gemini Vision.
    Idempotent and securely records audit timeline event.
    """
    clean_id = report_id.strip().upper()
    doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report '{report_id}' not found.",
        )

    evidence_doc = doc.get("evidence")
    media_list = doc.get("media", [])
    image_bytes = None
    mime_type = "image/jpeg"
    evidence_id = None
    source_type = "LIVE_CAMERA_EVIDENCE"
    content_hash = None
    has_evidence_record = False

    # 1. Check Live Camera Evidence Record
    if isinstance(evidence_doc, dict):
        if evidence_doc.get("file_url") or evidence_doc.get("filename") or evidence_doc.get("image_bytes") or evidence_doc.get("image_base64"):
            has_evidence_record = True
        evidence_id = evidence_doc.get("evidence_id")
        content_hash = evidence_doc.get("content_hash")

        # Check if raw bytes or base64 are directly in the evidence doc
        if evidence_doc.get("image_bytes"):
            raw = evidence_doc["image_bytes"]
            if isinstance(raw, str):
                try:
                    image_bytes = base64.b64decode(raw.split(",", 1)[-1])
                except Exception:
                    image_bytes = raw.encode("utf-8")
            elif isinstance(raw, bytes):
                image_bytes = raw
        elif evidence_doc.get("image_base64"):
            try:
                b64_str = str(evidence_doc["image_base64"]).split(",", 1)[-1]
                image_bytes = base64.b64decode(b64_str)
            except Exception as b64_err:
                logger.warning(f"Failed to decode evidence_doc image_base64 for {clean_id}: {b64_err}")

        # Check file stored on disk
        if not image_bytes:
            filename = evidence_doc.get("filename")
            file_url = evidence_doc.get("file_url")

            candidate_paths = []
            if filename:
                candidate_paths.append(os.path.join(settings.UPLOAD_DIR, "citizen_evidence", filename))
                candidate_paths.append(os.path.join(settings.UPLOAD_DIR, filename))
            if file_url:
                clean_rel = str(file_url).lstrip("/").replace("uploads/", "", 1)
                candidate_paths.append(os.path.join(settings.UPLOAD_DIR, clean_rel))
                candidate_paths.append(os.path.join(settings.UPLOAD_DIR, "citizen_evidence", os.path.basename(file_url)))
                candidate_paths.append(os.path.join(settings.UPLOAD_DIR, os.path.basename(file_url)))

            for path in candidate_paths:
                if os.path.isfile(path):
                    try:
                        with open(path, "rb") as f:
                            image_bytes = f.read()
                        if path.lower().endswith(".png"):
                            mime_type = "image/png"
                        elif path.lower().endswith(".webp"):
                            mime_type = "image/webp"
                        else:
                            mime_type = "image/jpeg"
                        source_type = "LIVE_CAMERA_EVIDENCE"
                        break
                    except Exception as read_err:
                        logger.warning(f"Error reading evidence file {path} for {clean_id}: {read_err}")

    # 2. Check Media Attachments (Photo Attachments)
    if not image_bytes and isinstance(media_list, list) and len(media_list) > 0:
        for m in media_list:
            if not isinstance(m, dict):
                continue
            m_type = str(m.get("media_type", "")).lower()
            m_filename = m.get("filename", "")
            m_url = m.get("file_url") or m.get("url")
            is_image = (
                m_type.startswith("image/")
                or m_type in ["photo", "image", "jpg", "jpeg", "png", "webp"]
                or m_filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                or (m_url and str(m_url).lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
            )
            if not is_image:
                continue

            has_evidence_record = True
            candidate_paths = []
            if m_filename:
                candidate_paths.append(os.path.join(settings.UPLOAD_DIR, "citizen_reports", m_filename))
                candidate_paths.append(os.path.join(settings.UPLOAD_DIR, "citizen_evidence", m_filename))
                candidate_paths.append(os.path.join(settings.UPLOAD_DIR, m_filename))
            if m_url:
                clean_rel = str(m_url).lstrip("/").replace("uploads/", "", 1)
                candidate_paths.append(os.path.join(settings.UPLOAD_DIR, clean_rel))
                candidate_paths.append(os.path.join(settings.UPLOAD_DIR, "citizen_reports", os.path.basename(m_url)))
                candidate_paths.append(os.path.join(settings.UPLOAD_DIR, os.path.basename(m_url)))

            for path in candidate_paths:
                if os.path.isfile(path):
                    try:
                        with open(path, "rb") as f:
                            image_bytes = f.read()
                        if path.lower().endswith(".png"):
                            mime_type = "image/png"
                        elif path.lower().endswith(".webp"):
                            mime_type = "image/webp"
                        else:
                            mime_type = m_type if m_type.startswith("image/") else "image/jpeg"
                        evidence_id = m_filename or os.path.basename(path)
                        source_type = "PHOTO_ATTACHMENT"
                        break
                    except Exception as read_err:
                        logger.warning(f"Error reading media file {path} for {clean_id}: {read_err}")
            if image_bytes:
                break

    # 3. Honest Status / Error Handling
    if not image_bytes:
        if has_evidence_record:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The evidence record exists, but the image could not be retrieved from storage.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No live camera evidence or photo attachment found on this report.",
            )

    if not content_hash and image_bytes:
        content_hash = hashlib.sha256(image_bytes).hexdigest()

    from app.services.gemini_service import GeminiIntelligenceService
    gemini_svc = GeminiIntelligenceService.get_instance()
    
    vis_analysis = await gemini_svc.analyze_visual_evidence(
        source_id=evidence_id or clean_id,
        source_type=source_type,
        image_bytes=image_bytes,
        citizen_text=doc.get("description", ""),
        report_id=clean_id,
        evidence_id=evidence_id,
        mime_type=mime_type,
        content_hash=content_hash,
        metadata={
            "emergency_type": doc.get("emergency_type"),
            "citizen_impact_level": doc.get("citizen_impact_level"),
            "requested_by": current_user.full_name,
        }
    )

    now = datetime.now(timezone.utc)
    vis_dict = vis_analysis.model_dump(mode="json")

    await db["citizen_reports"].update_one(
        {"report_id": clean_id},
        {"$set": {"visual_evidence": vis_dict, "updated_at": now}}
    )

    if vis_analysis.status == VisualAnalysisStatus.SUCCESS:
        prov_label = f"{vis_analysis.provider} Vision"
        if vis_analysis.fallback_triggered:
            prov_label += " (Failover Fallback)"
        timeline_details = f"Multimodal visual analysis evaluated by {prov_label} ({vis_analysis.hazard_type.value}, consistency: {vis_analysis.text_image_consistency.value})."
        timeline_value = vis_analysis.hazard_type.value
    elif vis_analysis.status == VisualAnalysisStatus.TEMPORARILY_UNAVAILABLE:
        timeline_details = f"Visual analysis providers temporarily unavailable ({vis_analysis.error_classification or '503 UNAVAILABLE'}). Visual evidence safely preserved."
        timeline_value = "TEMPORARILY_UNAVAILABLE"
    else:
        timeline_details = f"Visual analysis status: {vis_analysis.status.value} ({vis_analysis.error_reason or vis_analysis.error_message or 'Analysis unavailable'})."
        timeline_value = vis_analysis.status.value

    await record_timeline_event(
        db=db,
        report_id=clean_id,
        event_type=TimelineEventType.EVIDENCE_VALIDATED,
        details=timeline_details,
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
        previous_value=None,
        new_value=timeline_value,
    )

    updated_doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    corrob_res = await EvidenceCorroborationService.get_or_evaluate_report_corroboration(clean_id, db)
    return parse_report_document(updated_doc or doc, corroboration=corrob_res)


@router.post("/reports/{report_id}/extract-text-evidence", response_model=OfficerReportDetailResponse)
async def extract_report_text_evidence(
    report_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    On-demand officer trigger to analyze / re-evaluate unstructured citizen text evidence
    via Unified Multi-Provider Text Router (Gemini Primary + OpenAI Fallback).
    """
    clean_id = report_id.strip().upper()
    doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report '{report_id}' not found.",
        )

    description = (doc.get("description") or "").strip()
    if not description:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Report does not contain any text description to extract.",
        )

    from app.services.text_analysis_router import TextAnalysisRouter
    from app.models.llm_extraction import ExtractionStatus
    router = TextAnalysisRouter.get_instance()
    extraction_res = await router.extract_structured_evidence(
        source_id=clean_id,
        source_type="CITIZEN_REPORT",
        text_content=description,
        context_metadata={
            "emergency_type": doc.get("emergency_type", "UNSPECIFIED"),
            "location_address": doc.get("location", {}).get("address", "Not provided") if isinstance(doc.get("location"), dict) else "Not provided",
        },
        report_id=clean_id,
    )

    now = datetime.now(timezone.utc)
    ext_dict = extraction_res.model_dump(mode="json")

    await db["citizen_reports"].update_one(
        {"report_id": clean_id},
        {"$set": {"llm_extraction": ext_dict, "updated_at": now}}
    )

    prov_label = f"{extraction_res.provider} Text"
    if extraction_res.fallback_used:
        prov_label += " (Failover Fallback)"

    await record_timeline_event(
        db=db,
        report_id=clean_id,
        event_type=TimelineEventType.EVIDENCE_VALIDATED,
        details=f"Unstructured citizen text analyzed by {prov_label} (Status: {extraction_res.status.value}).",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
        previous_value=None,
        new_value=extraction_res.status.value,
    )

    updated_doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    corrob_res = await EvidenceCorroborationService.get_or_evaluate_report_corroboration(clean_id, db)
    return parse_report_document(updated_doc or doc, corroboration=corrob_res)



@router.get("/volunteers", response_model=List[UserResponse])
async def list_officer_volunteers(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Retrieve real registered volunteer responders for the Emergency Officer Command Center.
    """
    cursor = db["users"].find({"role": UserRole.VOLUNTEER.value}).sort("created_at", -1).limit(100)
    volunteers = []
    async for doc in cursor:
        vol_prof = None
        if doc.get("volunteer_profile"):
            vol_prof = VolunteerProfile(**doc["volunteer_profile"])
        volunteers.append(UserResponse(
            id=str(doc["_id"]),
            phone=doc["phone"],
            full_name=doc["full_name"],
            email=doc.get("email"),
            role=UserRole(doc["role"]),
            is_active=doc.get("is_active", True),
            badge_number=doc.get("badge_number"),
            department_or_agency=doc.get("department_or_agency"),
            created_at=doc.get("created_at", datetime.now(timezone.utc)),
            volunteer_profile=vol_prof,
            google_sub=doc.get("google_sub"),
        ))
    return volunteers


@router.get("/audit-logs", response_model=List[dict])
async def list_officer_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Retrieve real timeline audit events across the platform for the Emergency Officer Command Center.
    """
    cursor = db["audit_logs"].find({}).sort("timestamp", -1).limit(limit)
    events = []
    async for a in cursor:
        a["_id"] = str(a["_id"])
        events.append(a)
    return events


# =========================================================================
# Phase 5: Multi-Agent Coordination & Central Orchestrator Endpoints
# =========================================================================

@router.post("/coordination/situations/{situation_id}/orchestrate", response_model=CoordinationPlan)
async def orchestrate_situation_plan(
    situation_id: str,
    payload: Optional[OrchestrateSituationRequest] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Triggers Central Orchestrator for a real situation cluster.
    Deterministically selects, coordinates, and synthesizes registered agents into a Coordination Plan.
    """
    clean_sit_id = situation_id.strip().upper()
    force_refresh = payload.force_refresh if payload else False
    
    actor_dict = {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
    }

    try:
        plan = await central_orchestrator.orchestrate_situation(
            situation_id=clean_sit_id,
            actor=actor_dict,
            force_refresh=force_refresh,
            db=db,
        )
        return plan
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error orchestrating situation {situation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Central Orchestrator encountered an internal error.",
        )


@router.get("/coordination/plans/{plan_id}", response_model=CoordinationPlan)
async def get_coordination_plan(
    plan_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Retrieve a specific Coordination Plan by ID.
    """
    clean_plan_id = plan_id.strip().upper()
    doc = await db["coordination_plans"].find_one({"plan_id": clean_plan_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coordination Plan '{plan_id}' not found.",
        )
    return CoordinationPlan(**doc)


@router.get("/coordination/plans/{plan_id}/conflicts", response_model=Optional[ConflictResolutionSummary])
async def get_coordination_plan_conflicts(
    plan_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Retrieve detailed Conflict Resolution Summary for a specific Coordination Plan.
    """
    clean_plan_id = plan_id.strip().upper()
    doc = await db["coordination_plans"].find_one({"plan_id": clean_plan_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coordination Plan '{plan_id}' not found.",
        )
    plan = CoordinationPlan(**doc)
    return plan.conflict_summary


@router.get("/coordination/plans/{plan_id}/shelters", response_model=Optional[ShelterCoordinationSummary])
async def get_coordination_plan_shelters(
    plan_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Retrieve detailed Shelter Coordination Summary for a specific Coordination Plan.
    """
    clean_plan_id = plan_id.strip().upper()
    doc = await db["coordination_plans"].find_one({"plan_id": clean_plan_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coordination Plan '{plan_id}' not found.",
        )
    plan = CoordinationPlan(**doc)
    return plan.shelter_summary


@router.get("/coordination/plans/{plan_id}/healthcare", response_model=Optional[HealthcareCoordinationSummary])
async def get_coordination_plan_healthcare(
    plan_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Retrieve detailed Healthcare Coordination Summary for a specific Coordination Plan.
    """
    clean_plan_id = plan_id.strip().upper()
    doc = await db["coordination_plans"].find_one({"plan_id": clean_plan_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coordination Plan '{plan_id}' not found.",
        )
    plan = CoordinationPlan(**doc)
    return plan.healthcare_summary


@router.get("/coordination/plans/{plan_id}/volunteers", response_model=Optional[VolunteerCoordinationSummary])
async def get_coordination_plan_volunteers(
    plan_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Retrieve detailed Volunteer Coordination Summary for a specific Coordination Plan.
    """
    clean_plan_id = plan_id.strip().upper()
    doc = await db["coordination_plans"].find_one({"plan_id": clean_plan_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coordination Plan '{plan_id}' not found.",
        )
    plan = CoordinationPlan(**doc)
    return plan.volunteer_summary


@router.get("/coordination/plans/{plan_id}/routes", response_model=Optional[RouteTransportCoordinationSummary])
async def get_coordination_plan_routes(
    plan_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Retrieve detailed Route & Transport Coordination Summary for a specific Coordination Plan.
    """
    clean_plan_id = plan_id.strip().upper()
    doc = await db["coordination_plans"].find_one({"plan_id": clean_plan_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coordination Plan '{plan_id}' not found.",
        )
    plan = CoordinationPlan(**doc)
    return plan.route_summary


@router.get("/coordination/situations/{situation_id}/plans", response_model=List[CoordinationPlan])
async def list_situation_coordination_plans(
    situation_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    List all generated Coordination Plans for a given situation cluster.
    """
    clean_sit_id = situation_id.strip().upper()
    cursor = db["coordination_plans"].find({"situation_id": clean_sit_id}).sort("generated_at", -1)
    plans = []
    async for doc in cursor:
        plans.append(CoordinationPlan(**doc))
    return plans


@router.post("/coordination/plans/{plan_id}/review", response_model=CoordinationPlan)
async def review_coordination_plan_endpoint(
    plan_id: str,
    payload: PlanReviewRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Human-in-the-loop Emergency Officer review of a Coordination Plan.
    Authoritatively approves, modifies, or rejects the plan.
    """
    clean_plan_id = plan_id.strip().upper()
    actor_dict = {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
    }

    try:
        updated_plan = await central_orchestrator.review_coordination_plan(
            plan_id=clean_plan_id,
            action=payload.action,
            actor=actor_dict,
            notes=payload.notes,
            modified_needs=payload.modified_needs,
            modified_allocations=payload.modified_allocations,
            modified_shelters=payload.modified_shelters,
            modified_facilities=payload.modified_facilities,
            modified_volunteers=payload.modified_volunteers,
            modified_transports=payload.modified_transports,
            modified_routes=payload.modified_routes,
            db=db,
        )
        return updated_plan
    except ValueError as e:
        err_msg = str(e)
        if "STALE_PLAN" in err_msg or "CONFLICT" in err_msg or "MISMATCH" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=err_msg,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )
    except Exception as e:
        logger.error(f"Error reviewing coordination plan {plan_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record officer review for coordination plan.",
        )


@router.get("/coordination/agent-runs/{run_id}", response_model=dict)
async def get_agent_run_detail(
    run_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Inspect raw structured execution output of a single agent run.
    """
    clean_run_id = run_id.strip().upper()
    doc = await db["ai_agent_runs"].find_one({"run_id": clean_run_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent Run '{run_id}' not found.",
        )
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("/coordination/situations/{situation_id}/agent-runs", response_model=List[dict])
async def list_situation_agent_runs(
    situation_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    List all agent executions recorded for a situation cluster.
    """
    clean_sit_id = situation_id.strip().upper()
    cursor = db["ai_agent_runs"].find({"situation_id": clean_sit_id}).sort("started_at", -1)
    runs = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
    return runs


from app.models.incident_evolution import IncidentEvolutionTimelineResponse
from app.services.incident_evolution_service import IncidentEvolutionService


@router.get("/reports/{report_id}/evolution-timeline", response_model=IncidentEvolutionTimelineResponse)
async def get_officer_report_evolution_timeline(
    report_id: str,
    order: str = Query("asc", description="Sort order: 'asc' or 'desc'"),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
) -> IncidentEvolutionTimelineResponse:
    """
    Incident Evolution Timeline for Officer inspection (Phase C).
    Aggregates report events, evidence validation, corroboration, field verifications,
    and operational milestone events chronologically from genuine database records.
    """
    clean_id = report_id.strip().upper()
    rep_doc = await db["citizen_reports"].find_one({"report_id": clean_id})
    if not rep_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency report with ID '{report_id}' not found.",
        )
    return await IncidentEvolutionService.get_evolution_timeline(
        target_id=clean_id,
        db=db,
        order=order,
    )



