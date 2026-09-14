import logging
import math
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.api.deps import require_officer
from app.models.user import UserResponse
from app.models.enums import (
    EmergencyType,
    SeverityLevel,
    SituationStatus,
    AssessmentStatus,
    OfficerReviewAction,
    TimelineEventType,
    UserRole,
    MonitoringEventType,
    EventSourceType,
    ReportStatus,
)
from app.services.monitoring.monitoring_service import MonitoringService

from app.models.situation import (
    SituationCluster,
    SituationDetailResponse,
    ClusteredReportSummary,
    SensorEvidenceSummary,
    SituationEvidenceResponse,
    SituationAssessment,
    OfficerSituationReview,
    OfficerSituationReviewRequest,
    PaginatedSituationsResponse,
    SituationStatsResponse,
)
from app.models.corroboration import CorroborationResult
from app.services.incident_fusion import (
    fuse_or_create_situation_for_report,
    sync_all_incident_clusters,
)
from app.services.situation_assessment import generate_situation_assessment
from app.services.corroboration_service import EvidenceCorroborationService
from app.services.timeline import record_timeline_event

logger = logging.getLogger("resilience.situations")
router = APIRouter()


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
    return dt


def parse_situation_doc(doc: dict) -> SituationCluster:
    # Ensure nested objects and defaults are parsed correctly with backwards compatibility
    doc_copy = dict(doc)
    sit_id = doc_copy.get("situation_id", "UNKNOWN")
    if "cluster_id" not in doc_copy or not doc_copy["cluster_id"]:
        doc_copy["cluster_id"] = f"CLS-{sit_id.replace('SIT-', '')}"
    if "primary_report_id" not in doc_copy or not doc_copy["primary_report_id"]:
        rep_ids = doc_copy.get("report_ids") or []
        doc_copy["primary_report_id"] = rep_ids[0] if rep_ids else "REP-PRIMARY"

    # Normalize emergency_type
    raw_et = doc_copy.get("emergency_type")
    valid_et_values = {e.value: e for e in EmergencyType}
    if raw_et in valid_et_values:
        doc_copy["emergency_type"] = valid_et_values[raw_et]
    else:
        matched = None
        for val, enum_obj in valid_et_values.items():
            if raw_et and (str(raw_et).lower() in val.lower() or val.lower() in str(raw_et).lower()):
                matched = enum_obj
                break
        doc_copy["emergency_type"] = matched or EmergencyType.OTHER

    # Normalize center_location
    if "center_location" not in doc_copy or not doc_copy["center_location"] or not isinstance(doc_copy["center_location"], dict):
        center_lat = float(doc_copy.get("center_latitude") or doc_copy.get("latitude") or 16.2415)
        center_lon = float(doc_copy.get("center_longitude") or doc_copy.get("longitude") or 80.6433)
        doc_copy["center_location"] = {
            "latitude": center_lat,
            "longitude": center_lon,
            "address": doc_copy.get("location_summary") or doc_copy.get("address") or "Operational Zone",
            "zone_or_district": doc_copy.get("zone_or_district") or "Operational Zone",
        }
    else:
        cl = dict(doc_copy["center_location"])
        cl["latitude"] = float(cl.get("latitude", 16.2415))
        cl["longitude"] = float(cl.get("longitude", 80.6433))
        doc_copy["center_location"] = cl

    if "impact_zone" not in doc_copy or not doc_copy["impact_zone"]:
        center = doc_copy.get("center_location") or {}
        doc_copy["impact_zone"] = {
            "center_latitude": center.get("latitude", 16.2415),
            "center_longitude": center.get("longitude", 80.6433),
            "radius_km": float(doc_copy.get("impact_radius_km", 2.5)),
            "affected_zone_name": center.get("zone_or_district") or center.get("city") or "Operational Zone",
        }
    if "computed_severity_score" not in doc_copy:
        doc_copy["computed_severity_score"] = float(doc_copy.get("severity_score", 5.0))
    if "computed_severity_level" not in doc_copy:
        doc_copy["computed_severity_level"] = doc_copy.get("severity_level", SeverityLevel.MEDIUM.value)
    if "severity_score" not in doc_copy:
        doc_copy["severity_score"] = float(doc_copy.get("computed_severity_score", 5.0))
    if "severity_level" not in doc_copy:
        doc_copy["severity_level"] = doc_copy.get("computed_severity_level", SeverityLevel.MEDIUM.value)
    if "estimated_affected_population" not in doc_copy:
        doc_copy["estimated_affected_population"] = int(doc_copy.get("affected_population", 0))
    if "hazard_risk" not in doc_copy:
        doc_copy["hazard_risk"] = "Moderate Operational Risk"
    if "situation_summary" not in doc_copy:
        doc_copy["situation_summary"] = doc_copy.get("title", f"Emergency incident cluster {sit_id}")
    now = datetime.now(timezone.utc)
    if "created_at" not in doc_copy or not doc_copy["created_at"]:
        doc_copy["created_at"] = now
    if "updated_at" not in doc_copy or not doc_copy["updated_at"]:
        doc_copy["updated_at"] = doc_copy.get("created_at") or now
    return SituationCluster(**doc_copy)


@router.get("/stats", response_model=SituationStatsResponse)
async def get_situation_stats(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Real-time situation statistics aggregated directly from MongoDB Atlas.
    """
    active_statuses = [
        SituationStatus.ACTIVE.value,
        SituationStatus.RESPONSE_IN_PROGRESS.value,
        SituationStatus.OFFICER_REVIEW.value,
        SituationStatus.MONITORING.value,
    ]
    total = await db["situations"].count_documents({})
    active = await db["situations"].count_documents({
        "status": {"$in": active_statuses},
        "report_count": {"$gt": 0},
    })
    critical = await db["situations"].count_documents({
        "severity_level": SeverityLevel.CRITICAL.value,
        "report_count": {"$gt": 0},
        "status": {"$in": active_statuses},
    })
    high = await db["situations"].count_documents({
        "severity_level": SeverityLevel.HIGH.value,
        "report_count": {"$gt": 0},
        "status": {"$in": active_statuses},
    })

    # Count all unique active clustered reports
    pipeline = [
        {"$match": {"status": {"$in": active_statuses}, "report_count": {"$gt": 0}}},
        {"$unwind": "$report_ids"},
        {"$group": {"_id": None, "unique_reports": {"$addToSet": "$report_ids"}}},
    ]
    cursor = db["situations"].aggregate(pipeline)
    total_clustered = 0
    async for item in cursor:
        total_clustered = len(item.get("unique_reports", []))

    # Average confidence
    conf_pipeline = [
        {"$match": {"status": {"$in": active_statuses}, "report_count": {"$gt": 0}}},
        {"$group": {"_id": None, "avg_conf": {"$avg": "$confidence"}}},
    ]
    conf_cursor = db["situations"].aggregate(conf_pipeline)
    avg_conf = 0.0
    async for c in conf_cursor:
        avg_conf = round(float(c.get("avg_conf", 0.0)), 2)

    return SituationStatsResponse(
        total_situations=total,
        active_situations=active,
        critical_situations=critical,
        high_situations=high,
        total_clustered_reports=total_clustered,
        average_confidence=avg_conf,
    )


@router.get("", response_model=PaginatedSituationsResponse)
async def list_situations(
    status_filter: Optional[SituationStatus] = Query(None, alias="status"),
    emergency_type: Optional[EmergencyType] = None,
    severity_level: Optional[SeverityLevel] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    List situation clusters with multi-attribute filtering and pagination.
    """
    query: dict = {}
    if status_filter:
        query["status"] = status_filter.value
    else:
        # Default active situation feed excludes closed/contained/0-report situations
        query["status"] = {"$in": [
            SituationStatus.ACTIVE.value,
            SituationStatus.RESPONSE_IN_PROGRESS.value,
            SituationStatus.OFFICER_REVIEW.value,
            SituationStatus.MONITORING.value,
        ]}
        query["report_count"] = {"$gt": 0}

    if emergency_type:
        query["emergency_type"] = emergency_type.value
    if severity_level:
        query["severity_level"] = severity_level.value
    if search:
        s_clean = search.strip()
        query["$or"] = [
            {"title": {"$regex": s_clean, "$options": "i"}},
            {"situation_id": {"$regex": s_clean, "$options": "i"}},
            {"cluster_id": {"$regex": s_clean, "$options": "i"}},
            {"report_ids": {"$regex": s_clean, "$options": "i"}},
            {"center_location.zone_or_district": {"$regex": s_clean, "$options": "i"}},
            {"center_location.city": {"$regex": s_clean, "$options": "i"}},
        ]

    total = await db["situations"].count_documents(query)
    skip = (page - 1) * limit
    total_pages = math.ceil(total / limit) if total > 0 else 1

    cursor = db["situations"].find(query).sort("updated_at", -1).skip(skip).limit(limit)
    items = []
    async for doc in cursor:
        items.append(parse_situation_doc(doc))

    return PaginatedSituationsResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.post("/fuse-all", response_model=dict)
async def fuse_all_reports(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Triggers idempotent synchronization and fusion of all pending citizen reports into Situation Clusters.
    """
    synced_count = await sync_all_incident_clusters(db)
    return {"message": f"Successfully synced incident clusters ({synced_count} active situations).", "total_situations": synced_count}


@router.get("/{situation_id}", response_model=SituationDetailResponse)
async def get_situation_detail(
    situation_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Fetch comprehensive situation details including all member citizen reports.
    """
    clean_id = situation_id.strip().upper()
    doc = await db["situations"].find_one({"situation_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Situation cluster '{clean_id}' not found.",
        )

    situation_obj = parse_situation_doc(doc)
    c_lat = situation_obj.center_location.latitude
    c_lon = situation_obj.center_location.longitude

    # Fetch all active non-rejected clustered reports
    reports_cursor = db["citizen_reports"].find({
        "report_id": {"$in": situation_obj.report_ids},
        "status": {"$ne": ReportStatus.REJECTED.value},
    })
    clustered_reports: List[ClusteredReportSummary] = []
    
    async for r in reports_cursor:
        loc = r.get("location", {})
        r_lat = loc.get("latitude", 0.0)
        r_lon = loc.get("longitude", 0.0)
        from app.services.resource_matching import haversine_distance_km
        dist = haversine_distance_km(c_lat, c_lon, r_lat, r_lon)

        clustered_reports.append(ClusteredReportSummary(
            report_id=r["report_id"],
            emergency_type=EmergencyType(r.get("emergency_type", EmergencyType.OTHER.value)),
            description=r.get("description", ""),
            citizen_name=r.get("citizen_name", "Anonymous"),
            citizen_phone=r.get("citizen_phone", ""),
            latitude=r_lat,
            longitude=r_lon,
            address=loc.get("address") or loc.get("display_name"),
            zone_or_district=loc.get("zone_or_district"),
            distance_to_center_km=dist,
            status=r.get("status", "RECEIVED"),
            priority=r.get("priority", "UNASSESSED"),
            created_at=ensure_utc(r.get("created_at")),
            media=r.get("media", []),
        ))

    # Sort clustered reports by distance from center
    clustered_reports.sort(key=lambda x: x.distance_to_center_km)

    # -------------------------------------------------------------
    # SENSOR EVIDENCE FUSION & CORRELATION
    # -------------------------------------------------------------
    from app.services.resource_matching import haversine_distance_km
    sensor_evidence: List[SensorEvidenceSummary] = []
    seen_sensor_ids = set()

    # 1. Fetch sensor alerts linked directly to this situation
    alerts_cursor = db["sensor_alerts"].find({"situation_id": clean_id}).sort("created_at", -1)
    async for a in alerts_cursor:
        s_id = a.get("sensor_id")
        if s_id and s_id not in seen_sensor_ids:
            seen_sensor_ids.add(s_id)
            s_lat = float(a.get("latitude", c_lat))
            s_lon = float(a.get("longitude", c_lon))
            dist = haversine_distance_km(c_lat, c_lon, s_lat, s_lon)
            is_breach = a.get("status") == "ACTIVE_BREACH"
            state = "BREACHED" if is_breach else "RECOVERED" if "RESOLVED" in str(a.get("status")) else "NORMAL"
            
            # Fetch sensor doc to enrich coverage & location
            s_doc = await db["sensors"].find_one({"sensor_id": s_id}) or {}
            cov_m = float(a.get("coverage_radius_meters") or s_doc.get("coverage", {}).get("radius_meters") or 2000.0)
            cov_km = round(cov_m / 1000.0, 2)
            s_address = s_doc.get("location", {}).get("address") or a.get("location_name")

            sensor_evidence.append(SensorEvidenceSummary(
                source_type="SIMULATED_SENSOR",
                source_id=s_id,
                sensor_id=s_id,
                sensor_name=a.get("sensor_name") or f"Sensor {s_id}",
                sensor_type=str(a.get("sensor_type", "SENSOR")),
                event_id=a.get("event_id") or a.get("alert_id"),
                reading_id=a.get("reading_id"),
                value=float(a.get("current_value", 0.0)),
                current_value=float(a.get("current_value", 0.0)),
                previous_value=float(a.get("previous_value")) if a.get("previous_value") is not None else None,
                unit=a.get("unit", ""),
                threshold=float(a.get("threshold", 0.0)),
                threshold_state=state,
                is_breach=is_breach,
                timestamp=ensure_utc(a.get("created_at")),
                latitude=s_lat,
                longitude=s_lon,
                location_name=a.get("location_name"),
                sensor_address=s_address,
                coverage_radius_meters=cov_m,
                coverage_radius_km=cov_km,
                distance_to_center_km=round(dist, 2),
                correlation_reason=f"WITHIN_SENSOR_COVERAGE: Corroborating threshold alert ({state}) linked to situation (~{dist:.2f} km <= {cov_km:.2f} km coverage)",
                confidence_contribution=0.15 if is_breach else 0.05,
                is_simulated=True,
            ))

    # 2. Query sensors explicitly linked or spatially within sensor's configured coverage radius
    sensors_cursor = db["sensors"].find({
        "$or": [
            {"linked_situation_id": clean_id},
            {"status": {"$in": ["ACTIVE", "PAUSED"]}},
        ]
    })
    async for s in sensors_cursor:
        s_id = s.get("sensor_id")
        if not s_id or s_id in seen_sensor_ids:
            continue

        s_lat = s.get("latitude")
        s_lon = s.get("longitude")
        if s_lat is None or s_lon is None:
            continue

        dist = haversine_distance_km(c_lat, c_lon, float(s_lat), float(s_lon))
        is_explicit = s.get("linked_situation_id") == clean_id

        cov_dict = s.get("coverage") or {}
        cov_m = float(cov_dict.get("radius_meters", 2000.0))
        cov_km = round(cov_m / 1000.0, 2)

        # Strict spatial correlation: must be within sensor's own coverage radius OR explicitly linked
        if is_explicit or dist <= cov_km:
            has_reading = s.get("current_reading") is not None
            in_alert = bool(s.get("in_alert", False))
            if not has_reading and not in_alert:
                continue

            seen_sensor_ids.add(s_id)
            current_val = float(s.get("current_reading", 0.0)) if s.get("current_reading") is not None else 0.0
            thresh = float(s.get("threshold", 0.0))
            is_breach = in_alert or (current_val > thresh and thresh > 0)
            state = "BREACHED" if is_breach else "NORMAL"
            s_address = s.get("location", {}).get("address") or s.get("location_name")

            reason = (
                f"Explicitly linked IoT sensor station (~{dist:.2f} km from center)" if is_explicit
                else f"WITHIN_SENSOR_COVERAGE: Telemetry within sensor coverage radius (~{dist:.2f} km <= {cov_km:.2f} km)"
            )

            sensor_evidence.append(SensorEvidenceSummary(
                source_type="SIMULATED_SENSOR",
                source_id=s_id,
                sensor_id=s_id,
                sensor_name=s.get("name") or f"Sensor {s_id}",
                sensor_type=str(s.get("sensor_type", "SENSOR")),
                event_id=s.get("current_alert_id"),
                reading_id=None,
                value=current_val,
                current_value=current_val,
                previous_value=float(s.get("previous_reading")) if s.get("previous_reading") is not None else None,
                unit=s.get("unit", ""),
                threshold=thresh,
                threshold_state=state,
                is_breach=is_breach,
                timestamp=ensure_utc(s.get("last_updated") or s.get("updated_at") or s.get("created_at")),
                latitude=float(s_lat),
                longitude=float(s_lon),
                location_name=s.get("location_name"),
                sensor_address=s_address,
                coverage_radius_meters=cov_m,
                coverage_radius_km=cov_km,
                distance_to_center_km=round(dist, 2),
                correlation_reason=reason,
                confidence_contribution=0.15 if is_breach else 0.05,
                is_simulated=True,
            ))

    # Sort sensor evidence: breached first, then closest to center
    sensor_evidence.sort(key=lambda x: (not x.is_breach, x.distance_to_center_km))

    evidence_summary = SituationEvidenceResponse(
        total_sources=len(clustered_reports) + len(sensor_evidence),
        citizen_reports_count=len(clustered_reports),
        sensor_events_count=len(sensor_evidence),
        citizen_reports=clustered_reports,
        sensor_evidence=sensor_evidence,
    )

    corroboration_res = await EvidenceCorroborationService.evaluate_situation_corroboration(clean_id, db)

    return SituationDetailResponse(
        situation=situation_obj,
        clustered_reports=clustered_reports,
        sensor_evidence=sensor_evidence,
        evidence=evidence_summary,
        corroboration=corroboration_res,
    )


@router.get("/{situation_id}/corroboration", response_model=CorroborationResult)
async def get_situation_corroboration(
    situation_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Multi-Source Corroboration & Conflict Detection for Situation Cluster (Phase B).
    """
    clean_id = situation_id.strip().upper()
    result = await EvidenceCorroborationService.evaluate_situation_corroboration(clean_id, db)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Situation cluster with ID '{situation_id}' not found.",
        )
    return result


@router.post("/{situation_id}/assess", response_model=SituationCluster)
async def assess_situation(
    situation_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Generate or refresh AI-assisted Situation Assessment for a situation cluster.
    Preserves Emergency Officer severity overrides as the operational severity,
    while updating newly computed engine/AI assessment and scores.
    """
    clean_id = situation_id.strip().upper()
    doc = await db["situations"].find_one({"situation_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Situation cluster '{clean_id}' not found.",
        )

    situation_obj = parse_situation_doc(doc)

    # Fetch member reports for context
    reports_cursor = db["citizen_reports"].find({"report_id": {"$in": situation_obj.report_ids}})
    reports = await reports_cursor.to_list(length=100)

    # Record started event
    await record_timeline_event(
        db=db,
        report_id=situation_obj.primary_report_id,
        event_type=TimelineEventType.SITUATION_ASSESSMENT_STARTED,
        details=f"Situation assessment initiated for '{clean_id}' by {current_user.full_name}.",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
    )

    # Generate newly computed assessment
    assessment = await generate_situation_assessment(situation_obj, reports)
    now = datetime.now(timezone.utc)

    # Check if Emergency Officer override is active
    has_override = doc.get("officer_override_severity") is not None
    if has_override:
        op_level = doc["officer_override_severity"]
        op_score = doc.get("officer_override_score", doc.get("severity_score", assessment.severity_score))
        status_value = doc.get("assessment_status", AssessmentStatus.REVIEWED.value)
    else:
        op_level = assessment.severity_level.value
        op_score = assessment.severity_score
        status_value = AssessmentStatus.COMPLETED.value

    update_fields = {
        "assessment": assessment.model_dump(),
        "assessment_status": status_value,
        "computed_severity_score": assessment.severity_score,
        "computed_severity_level": assessment.severity_level.value,
        "severity_score": op_score,
        "severity_level": op_level,
        "estimated_affected_population": assessment.estimated_affected_population,
        "hazard_risk": assessment.hazard_risk,
        "confidence": assessment.confidence,
        "situation_summary": assessment.situation_summary,
        "impact_zone.radius_km": assessment.impact_radius_km,
        "updated_at": now,
    }

    await db["situations"].update_one({"situation_id": clean_id}, {"$set": update_fields})

    # Record generated event
    if has_override:
        evt_details = (
            f"Situation assessment refreshed: Newly computed severity {assessment.severity_level.value} "
            f"({assessment.severity_score:.1f}/10.0). Operational severity retained at {op_level} by Officer override."
        )
    else:
        evt_details = (
            f"Situation assessment generated: Severity {assessment.severity_level.value} "
            f"({assessment.severity_score:.1f}/10.0), Confidence: {int(assessment.confidence * 100)}%."
        )

    await record_timeline_event(
        db=db,
        report_id=situation_obj.primary_report_id,
        event_type=TimelineEventType.SITUATION_ASSESSMENT_GENERATED,
        details=evt_details,
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
    )

    updated_doc = await db["situations"].find_one({"situation_id": clean_id})
    return parse_situation_doc(updated_doc)


@router.post("/{situation_id}/review", response_model=SituationCluster)
async def review_situation(
    situation_id: str,
    payload: OfficerSituationReviewRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Emergency Officer Human-in-the-Loop review of situation assessment.
    Officer can Accept, Modify Severity (persisting officer override), or Reject.
    """
    clean_id = situation_id.strip().upper()
    doc = await db["situations"].find_one({"situation_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Situation cluster '{clean_id}' not found.",
        )

    situation_obj = parse_situation_doc(doc)
    now = datetime.now(timezone.utc)
    override_fields = {}

    # Determine resulting operational severity
    if payload.action == OfficerReviewAction.MODIFY:
        if not payload.modified_severity_level:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="modified_severity_level is required when modifying assessment.",
            )
        op_level = payload.modified_severity_level
        op_score = payload.modified_severity_score if payload.modified_severity_score is not None else situation_obj.severity_score
        
        override_fields = {
            "officer_override_severity": op_level.value,
            "officer_override_score": op_score,
            "officer_override_by": current_user.full_name,
            "officer_override_by_id": current_user.id,
            "officer_override_at": now,
            "officer_override_notes": payload.notes,
        }
    elif payload.action == OfficerReviewAction.ACCEPT:
        if payload.reset_override:
            # Explicitly reset officer override back to computed severity
            op_level = situation_obj.computed_severity_level or (situation_obj.assessment.severity_level if situation_obj.assessment else situation_obj.severity_level)
            op_score = situation_obj.computed_severity_score or (situation_obj.assessment.severity_score if situation_obj.assessment else situation_obj.severity_score)
            override_fields = {
                "officer_override_severity": None,
                "officer_override_score": None,
                "officer_override_by": None,
                "officer_override_by_id": None,
                "officer_override_at": None,
                "officer_override_notes": None,
            }
        else:
            if situation_obj.officer_override_severity:
                op_level = situation_obj.officer_override_severity
                op_score = situation_obj.officer_override_score if situation_obj.officer_override_score is not None else situation_obj.severity_score
            else:
                op_level = situation_obj.severity_level
                op_score = situation_obj.severity_score
    else:  # REJECT
        op_level = situation_obj.severity_level
        op_score = situation_obj.severity_score

    review = OfficerSituationReview(
        reviewed_by_id=current_user.id,
        reviewed_by_name=current_user.full_name,
        action=payload.action,
        operational_severity_level=op_level if isinstance(op_level, SeverityLevel) else SeverityLevel(op_level),
        operational_severity_score=op_score,
        notes=payload.notes,
        reviewed_at=now,
    )

    # Event mapping
    if payload.action == OfficerReviewAction.ACCEPT:
        evt_type = TimelineEventType.SITUATION_ASSESSMENT_ACCEPTED
        if payload.reset_override:
            detail_msg = f"Officer {current_user.full_name} reset severity override back to computed baseline ({op_level.value if isinstance(op_level, SeverityLevel) else op_level})."
        else:
            detail_msg = f"Officer {current_user.full_name} accepted situation assessment."
    elif payload.action == OfficerReviewAction.MODIFY:
        evt_type = TimelineEventType.SITUATION_ASSESSMENT_MODIFIED
        detail_msg = f"Officer {current_user.full_name} modified situation severity to {op_level.value if isinstance(op_level, SeverityLevel) else op_level} ({op_score:.1f}/10.0)."
    else:
        evt_type = TimelineEventType.SITUATION_ASSESSMENT_REJECTED
        detail_msg = f"Officer {current_user.full_name} rejected situation assessment. Reason: {payload.notes or 'Officer override'}."

    update_fields = {
        "officer_review": review.model_dump(),
        "assessment_status": AssessmentStatus.REVIEWED.value,
        "severity_level": op_level.value if isinstance(op_level, SeverityLevel) else op_level,
        "severity_score": op_score,
        "updated_at": now,
        **override_fields,
    }

    await db["situations"].update_one({"situation_id": clean_id}, {"$set": update_fields})

    # Record review audit event
    await record_timeline_event(
        db=db,
        report_id=situation_obj.primary_report_id,
        event_type=evt_type,
        details=detail_msg,
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
    )

    updated_doc = await db["situations"].find_one({"situation_id": clean_id})

    # Dispatch Phase 6 Monitoring Event
    try:
        await MonitoringService.record_change_event(
            event_type=MonitoringEventType.SITUATION_SEVERITY_CHANGED if payload.action == OfficerReviewAction.MODIFY else MonitoringEventType.OFFICER_SEVERITY_OVERRIDDEN,
            source_type=EventSourceType.SITUATION_INTELLIGENCE,
            source_id=clean_id,
            previous_state={
                "severity_level": situation_obj.severity_level.value if isinstance(situation_obj.severity_level, SeverityLevel) else situation_obj.severity_level,
                "severity_score": situation_obj.severity_score,
                "officer_override_severity": situation_obj.officer_override_severity.value if situation_obj.officer_override_severity else None,
            },
            new_state={
                "severity_level": updated_doc.get("severity_level"),
                "severity_score": updated_doc.get("severity_score"),
                "officer_override_severity": updated_doc.get("officer_override_severity"),
            },
            situation_id=clean_id,
            location=updated_doc.get("center_location"),
            actor={
                "id": current_user.id,
                "full_name": current_user.full_name,
                "role": current_user.role.value,
            },
            db=db,
        )
    except Exception as e:
        logger.warning(f"Failed to record monitoring event for situation review on {clean_id}: {e}")

    # Phase 7: Event-Driven Notification Dispatch
    try:
        from app.services.notification import get_notification_service
        from app.models.enums import NotificationCategory, NotificationSeverity, UserRole

        sev_val = str(updated_doc.get("severity_level", "HIGH")).upper()
        notif_sev = NotificationSeverity.CRITICAL if sev_val == "CRITICAL" else NotificationSeverity.HIGH

        notif_service = get_notification_service()
        await notif_service.dispatch_event(
            category=NotificationCategory.SITUATION,
            event_type="SITUATION_SEVERITY_CHANGED" if payload.action == OfficerReviewAction.MODIFY else "SITUATION_REVIEWED",
            severity=notif_sev,
            title=f"Situation Severity Updated: {clean_id} [{sev_val}]",
            message=f"{detail_msg} (Action: {payload.action.value})",
            entity_type="SITUATION",
            entity_id=clean_id,
            situation_id=clean_id,
            view_hint="situations",
            target_roles=[UserRole.EMERGENCY_OFFICER, UserRole.ADMIN],
            material_state={"situation_id": clean_id, "severity_level": sev_val, "action": payload.action.value},
            metadata={
                "situation_id": clean_id,
                "situation_title": updated_doc.get("title"),
                "severity_level": sev_val,
                "location_name": (updated_doc.get("center_location") or {}).get("address", ""),
            },
        )
    except Exception as notif_err:
        logger.warning(f"Notification dispatch notice for situation review on {clean_id}: {notif_err}")

    return parse_situation_doc(updated_doc)



@router.get("/{situation_id}/timeline", response_model=List[dict])
async def get_situation_timeline(
    situation_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get all audit events associated with a situation and its member reports.
    """
    clean_id = situation_id.strip().upper()
    doc = await db["situations"].find_one({"situation_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Situation cluster '{clean_id}' not found.",
        )

    report_ids = doc.get("report_ids", [])
    audits_cursor = db["audit_logs"].find({"report_id": {"$in": report_ids}}).sort("timestamp", 1)
    
    events = []
    async for a in audits_cursor:
        a["_id"] = str(a["_id"])
    return events


from app.models.incident_evolution import IncidentEvolutionTimelineResponse
from app.services.incident_evolution_service import IncidentEvolutionService


@router.get("/{situation_id}/evolution-timeline", response_model=IncidentEvolutionTimelineResponse)
async def get_situation_evolution_timeline(
    situation_id: str,
    order: str = Query("asc", description="Sort order: 'asc' or 'desc'"),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
) -> IncidentEvolutionTimelineResponse:
    """
    Incident Evolution Timeline (Phase C).
    Aggregates situation evolution, member reports, telemetry, field verifications,
    and coordination milestones chronologically from genuine database records.
    """
    clean_id = situation_id.strip().upper()
    doc = await db["situations"].find_one({"situation_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Situation cluster '{clean_id}' not found.",
        )
    return await IncidentEvolutionService.get_evolution_timeline(
        target_id=clean_id,
        db=db,
        order=order,
    )

