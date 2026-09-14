import logging
import math
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.config import settings
from app.models.enums import EmergencyType, SeverityLevel, SituationStatus, AssessmentStatus, ReportStatus
from app.models.situation import (
    SituationCluster,
    SituationLocationCenter,
    ImpactZone,
    generate_situation_id,
    generate_cluster_id,
)
from app.services.resource_matching import haversine_distance_km
from app.services.severity_engine import calculate_explainable_severity

logger = logging.getLogger("resilience.incident_fusion")

# Minimum impact radius in km per disaster type for initial safety buffer
MIN_IMPACT_RADIUS_KM: Dict[str, float] = {
    EmergencyType.CYCLONE_STORM.value: 5.0,
    EmergencyType.FLOOD.value: 2.0,
    EmergencyType.FIRE.value: 1.0,
    EmergencyType.BUILDING_COLLAPSE.value: 0.5,
    EmergencyType.LANDSLIDE.value: 1.0,
    EmergencyType.MISSING_TRAPPED.value: 0.5,
    EmergencyType.MEDICAL_EMERGENCY.value: 0.2,
    EmergencyType.ROAD_ACCIDENT.value: 0.3,
    EmergencyType.OTHER.value: 0.5,
}

# Compatible emergency types for compound incidents when within close proximity (< 1.0 km)
COMPATIBLE_EMERGENCY_TYPES: Dict[str, List[str]] = {
    EmergencyType.BUILDING_COLLAPSE.value: [EmergencyType.LANDSLIDE.value, EmergencyType.MISSING_TRAPPED.value],
    EmergencyType.LANDSLIDE.value: [EmergencyType.BUILDING_COLLAPSE.value, EmergencyType.ROAD_ACCIDENT.value],
    EmergencyType.CYCLONE_STORM.value: [EmergencyType.FLOOD.value],
    EmergencyType.FLOOD.value: [EmergencyType.CYCLONE_STORM.value],
}


def are_emergency_types_cluster_compatible(type_a: str, type_b: str, distance_km: float) -> bool:
    """Check whether two emergency types are compatible for fusion into the same situation."""
    if type_a == type_b:
        return True
    if distance_km <= 1.0:
        compatible = COMPATIBLE_EMERGENCY_TYPES.get(type_a, [])
        if type_b in compatible:
            return True
    return False


def calculate_cluster_centroid_and_radius(
    reports: List[Dict[str, Any]],
    emergency_type: str,
) -> Tuple[float, float, float, Dict[str, float]]:
    """
    Calculates geographic centroid, bounding box, and estimated impact radius for a group of reports.
    """
    if not reports:
        return 0.0, 0.0, 1.0, {"min_lat": 0.0, "min_lon": 0.0, "max_lat": 0.0, "max_lon": 0.0}

    lats = [r.get("location", {}).get("latitude", 0.0) for r in reports]
    lons = [r.get("location", {}).get("longitude", 0.0) for r in reports]

    center_lat = round(sum(lats) / len(lats), 6)
    center_lon = round(sum(lons) / len(lons), 6)

    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    # Calculate max distance from centroid to any member report
    max_dist_to_center = 0.0
    for r in reports:
        loc = r.get("location", {})
        d = haversine_distance_km(center_lat, center_lon, loc.get("latitude", 0.0), loc.get("longitude", 0.0))
        if d > max_dist_to_center:
            max_dist_to_center = d

    base_min = MIN_IMPACT_RADIUS_KM.get(emergency_type, 1.0)
    # Impact radius = max distance to member + safety buffer, bounded by base minimum
    calculated_radius = round(max(base_min, max_dist_to_center + 0.5), 2)

    bounding_box = {
        "min_lat": min_lat,
        "max_lat": max_lat,
        "min_lon": min_lon,
        "max_lon": max_lon,
    }

    return center_lat, center_lon, calculated_radius, bounding_box


async def fuse_or_create_situation_for_report(
    db: AsyncIOMotorDatabase,
    report_doc: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Fuses a newly ingested or updated citizen report into an existing compatible SituationCluster,
    or creates a new standalone SituationCluster for it.
    """
    report_id = report_doc["report_id"]
    if report_doc.get("status") == ReportStatus.REJECTED.value:
        logger.info(f"Report '{report_id}' is REJECTED. Excluded from Situation Intelligence candidate selection and fusion.")
        return {}
    rep_type = report_doc.get("emergency_type", EmergencyType.OTHER.value)
    rep_loc = report_doc.get("location", {})
    rep_lat = rep_loc.get("latitude", 0.0)
    rep_lon = rep_loc.get("longitude", 0.0)
    rep_created_at = report_doc.get("created_at")
    
    if isinstance(rep_created_at, str):
        try:
            rep_created_at = datetime.fromisoformat(rep_created_at.replace("Z", "+00:00"))
        except Exception:
            rep_created_at = datetime.now(timezone.utc)
    elif rep_created_at is None:
        rep_created_at = datetime.now(timezone.utc)
    elif rep_created_at.tzinfo is None:
        rep_created_at = rep_created_at.replace(tzinfo=timezone.utc)

    # Check if report is already attached to an active situation
    existing_situation = await db["situations"].find_one({"report_ids": report_id})
    if existing_situation:
        return existing_situation

    max_dist_km = settings.SITUATION_CLUSTERING_DISTANCE_KM
    max_hours = settings.SITUATION_CLUSTERING_TIME_WINDOW_HOURS
    earliest_time = rep_created_at - timedelta(hours=max_hours)
    latest_time = rep_created_at + timedelta(hours=max_hours)

    # Search existing active situations for spatial & temporal candidate match
    active_situations_cursor = db["situations"].find({
        "status": {"$in": [SituationStatus.ACTIVE.value, SituationStatus.MONITORING.value]},
        "created_at": {"$gte": earliest_time, "$lte": latest_time},
    })

    matched_situation = None
    min_found_dist = 999999.0

    async for sit_doc in active_situations_cursor:
        sit_type = sit_doc.get("emergency_type")
        c_loc = sit_doc.get("center_location", {})
        c_lat = c_loc.get("latitude", 0.0)
        c_lon = c_loc.get("longitude", 0.0)

        dist = haversine_distance_km(rep_lat, rep_lon, c_lat, c_lon)

        if dist <= max_dist_km and are_emergency_types_cluster_compatible(rep_type, sit_type, dist):
            if dist < min_found_dist:
                min_found_dist = dist
                matched_situation = sit_doc

    now = datetime.now(timezone.utc)

    if matched_situation:
        # Fuse report into existing situation cluster
        sit_id = matched_situation["situation_id"]
        updated_report_ids = list(set(matched_situation.get("report_ids", []) + [report_id]))
        
        # Fetch all active non-rejected member reports to recalculate center, impact zone & severity
        member_reports_cursor = db["citizen_reports"].find({
            "report_id": {"$in": updated_report_ids},
            "status": {"$ne": ReportStatus.REJECTED.value}
        })
        member_reports = await member_reports_cursor.to_list(length=100)

        center_lat, center_lon, impact_radius, bbox = calculate_cluster_centroid_and_radius(member_reports, matched_situation["emergency_type"])

        descriptions = [r.get("description", "") for r in member_reports]
        priorities = [r.get("priority") for r in member_reports if r.get("priority")]
        media_count = sum(len(r.get("media", [])) for r in member_reports)

        score, level, key_factors = calculate_explainable_severity(
            emergency_type=matched_situation["emergency_type"],
            descriptions=descriptions,
            report_count=len(updated_report_ids),
            officer_priorities=priorities,
            media_count=media_count,
        )

        reasoning = [
            f"Clustered {len(updated_report_ids)} corroborating reports for '{matched_situation['emergency_type']}'",
            f"Centroid updated: ({center_lat:.4f}, {center_lon:.4f}) with {impact_radius:.1f} km impact buffer",
            f"Latest member report '{report_id}' added at distance {min_found_dist:.2f} km from center",
        ]

        title = f"{matched_situation['emergency_type']} Cluster ({len(updated_report_ids)} Reports) - {rep_loc.get('zone_or_district') or rep_loc.get('city') or 'Local Area'}"

        has_override = matched_situation.get("officer_override_severity") is not None
        if has_override:
            effective_level = matched_situation["officer_override_severity"]
            effective_score = matched_situation.get("officer_override_score", matched_situation.get("severity_score", score))
        else:
            effective_level = level.value
            effective_score = score

        update_fields = {
            "report_ids": updated_report_ids,
            "report_count": len(updated_report_ids),
            "title": title,
            "center_location.latitude": center_lat,
            "center_location.longitude": center_lon,
            "impact_zone.center_latitude": center_lat,
            "impact_zone.center_longitude": center_lon,
            "impact_zone.radius_km": impact_radius,
            "impact_zone.bounding_box": bbox,
            "computed_severity_score": score,
            "computed_severity_level": level.value,
            "severity_score": effective_score,
            "severity_level": effective_level,
            "clustering_reasoning": reasoning,
            "updated_at": now,
        }

        await db["situations"].update_one({"situation_id": sit_id}, {"$set": update_fields})
        
        # Link situation_id in citizen report
        await db["citizen_reports"].update_one({"report_id": report_id}, {"$set": {"situation_id": sit_id}})

        # Dispatch Phase 6 Monitoring Event
        try:
            from app.services.monitoring.monitoring_service import MonitoringService
            from app.models.enums import MonitoringEventType, EventSourceType
            await MonitoringService.record_change_event(
                event_type=MonitoringEventType.SITUATION_MEMBERSHIP_CHANGED,
                source_type=EventSourceType.SITUATION_INTELLIGENCE,
                source_id=sit_id,
                previous_state={"report_count": len(matched_situation.get("report_ids", []))},
                new_state={"report_count": len(updated_report_ids), "latest_report_id": report_id},
                situation_id=sit_id,
                location=matched_situation.get("center_location"),
                db=db,
            )
        except Exception as mon_err:
            logger.warning(f"Monitoring notice on situation cluster update {sit_id}: {mon_err}")

        return await db["situations"].find_one({"situation_id": sit_id})

    else:
        # Create brand-new standalone situation cluster for report
        sit_id = generate_situation_id()
        cls_id = generate_cluster_id()
        base_radius = MIN_IMPACT_RADIUS_KM.get(rep_type, 1.0)

        score, level, key_factors = calculate_explainable_severity(
            emergency_type=rep_type,
            descriptions=[report_doc.get("description", "")],
            report_count=1,
            officer_priorities=[report_doc.get("priority")] if report_doc.get("priority") else [],
            media_count=len(report_doc.get("media", [])),
        )

        zone_name = rep_loc.get("zone_or_district") or rep_loc.get("city") or rep_loc.get("address") or "Incident Location"
        title = f"{rep_type} Emergency - {zone_name}"

        reasoning = [
            f"Initial situation created from incoming citizen report '{report_id}'",
            f"Designated primary emergency type: '{rep_type}'",
            f"Location: ({rep_lat:.4f}, {rep_lon:.4f}) with initial {base_radius:.1f} km safety perimeter",
        ]

        situation_doc = {
            "situation_id": sit_id,
            "cluster_id": cls_id,
            "title": title,
            "emergency_type": rep_type,
            "primary_report_id": report_id,
            "report_ids": [report_id],
            "report_count": 1,
            "center_location": {
                "latitude": rep_lat,
                "longitude": rep_lon,
                "address": rep_loc.get("address"),
                "street_address": rep_loc.get("street_address"),
                "landmark": rep_loc.get("landmark"),
                "zone_or_district": rep_loc.get("zone_or_district"),
                "city": rep_loc.get("city"),
                "state": rep_loc.get("state"),
                "country": rep_loc.get("country"),
                "postal_code": rep_loc.get("postal_code"),
            },
            "impact_zone": {
                "center_latitude": rep_lat,
                "center_longitude": rep_lon,
                "radius_km": base_radius,
                "affected_zone_name": zone_name,
                "bounding_box": {
                    "min_lat": rep_lat,
                    "max_lat": rep_lat,
                    "min_lon": rep_lon,
                    "max_lon": rep_lon,
                },
                "is_estimated": True,
                "estimation_rationale": "Initial impact boundary established from citizen reported disaster category.",
            },
            "status": SituationStatus.ACTIVE.value,
            "assessment_status": AssessmentStatus.PENDING.value,
            "severity_score": score,
            "severity_level": level.value,
            "computed_severity_score": score,
            "computed_severity_level": level.value,
            "officer_override_severity": None,
            "officer_override_score": None,
            "officer_override_by": None,
            "officer_override_by_id": None,
            "officer_override_at": None,
            "officer_override_notes": None,
            "estimated_affected_population": 0,
            "hazard_risk": "General Incident Containment",
            "confidence": 0.65,
            "situation_summary": f"Initial report of {rep_type} in {zone_name}. Pending AI situation assessment.",
            "assessment": None,
            "officer_review": None,
            "clustering_reasoning": reasoning,
            "created_at": now,
            "updated_at": now,
        }

        await db["situations"].insert_one(situation_doc)
        
        # Link situation_id in citizen report
        await db["citizen_reports"].update_one({"report_id": report_id}, {"$set": {"situation_id": sit_id}})

        # Record timeline event
        from app.services.timeline import record_timeline_event
        from app.models.enums import TimelineEventType
        await record_timeline_event(
            db=db,
            report_id=report_id,
            event_type=TimelineEventType.SITUATION_CLUSTER_CREATED,
            details=f"Situation cluster '{sit_id}' created for emergency report.",
        )

        # Dispatch Phase 6 Monitoring Event
        try:
            from app.services.monitoring.monitoring_service import MonitoringService
            from app.models.enums import MonitoringEventType, EventSourceType
            await MonitoringService.record_change_event(
                event_type=MonitoringEventType.SITUATION_CREATED,
                source_type=EventSourceType.SITUATION_INTELLIGENCE,
                source_id=sit_id,
                previous_state={},
                new_state={
                    "situation_id": sit_id,
                    "title": title,
                    "emergency_type": rep_type,
                    "severity_level": level.value,
                    "severity_score": score,
                    "report_count": 1,
                },
                situation_id=sit_id,
                location=situation_doc.get("center_location"),
                db=db,
            )
        except Exception as mon_err:
            logger.warning(f"Monitoring event recording notice for situation {sit_id}: {mon_err}")

        return situation_doc


async def refresh_situation_cluster(db: AsyncIOMotorDatabase, situation_id: str) -> Optional[Dict[str, Any]]:
    """
    Recalculates centroid, impact radius, bounding box, and explainable severity
    for an existing situation cluster based on its latest member report state.
    """
    situation = await db["situations"].find_one({"situation_id": situation_id})
    if not situation:
        return None

    report_ids = situation.get("report_ids", [])
    if not report_ids:
        return situation

    reports_cursor = db["citizen_reports"].find({
        "report_id": {"$in": report_ids},
        "status": {"$ne": ReportStatus.REJECTED.value}
    })
    reports = await reports_cursor.to_list(length=100)
    if not reports:
        now = datetime.now(timezone.utc)
        await db["situations"].update_one(
            {"situation_id": situation_id},
            {"$set": {
                "report_ids": [],
                "report_count": 0,
                "status": SituationStatus.CLOSED.value,
                "situation_summary": f"Situation closed automatically. All {len(report_ids)} member reports were officially rejected by emergency operations.",
                "updated_at": now,
            }}
        )
        return await db["situations"].find_one({"situation_id": situation_id})

    active_report_ids = [r["report_id"] for r in reports]
    emergency_type = situation.get("emergency_type", EmergencyType.OTHER.value)
    center_lat, center_lon, impact_radius, bbox = calculate_cluster_centroid_and_radius(reports, emergency_type)

    descriptions = [r.get("description", "") for r in reports]
    priorities = [r.get("priority") for r in reports if r.get("priority")]
    media_count = sum(len(r.get("media", [])) for r in reports)

    score, level, key_factors = calculate_explainable_severity(
        emergency_type=emergency_type,
        descriptions=descriptions,
        report_count=len(active_report_ids),
        officer_priorities=priorities,
        media_count=media_count,
    )

    now = datetime.now(timezone.utc)
    has_override = situation.get("officer_override_severity") is not None
    if has_override:
        effective_level = situation["officer_override_severity"]
        effective_score = situation.get("officer_override_score", situation.get("severity_score", score))
    else:
        effective_level = level.value
        effective_score = score

    primary_id = situation.get("primary_report_id")
    if not primary_id or primary_id not in active_report_ids:
        primary_id = active_report_ids[0]

    update_fields = {
        "report_ids": active_report_ids,
        "report_count": len(active_report_ids),
        "primary_report_id": primary_id,
        "center_location.latitude": center_lat,
        "center_location.longitude": center_lon,
        "impact_zone.center_latitude": center_lat,
        "impact_zone.center_longitude": center_lon,
        "impact_zone.radius_km": impact_radius,
        "impact_zone.bounding_box": bbox,
        "computed_severity_score": score,
        "computed_severity_level": level.value,
        "severity_score": effective_score,
        "severity_level": effective_level,
        "updated_at": now,
    }

    await db["situations"].update_one({"situation_id": situation_id}, {"$set": update_fields})
    return await db["situations"].find_one({"situation_id": situation_id})


async def sync_all_incident_clusters(db: AsyncIOMotorDatabase) -> int:
    """
    Scans all reports in database and guarantees each is attached to a SituationCluster.
    Idempotent and safe. Returns count of synced situations.
    """
    cursor = db["citizen_reports"].find({"status": {"$ne": ReportStatus.REJECTED.value}})
    reports = await cursor.to_list(length=1000)
    for rep in reports:
        await fuse_or_create_situation_for_report(db, rep)

    return await db["situations"].count_documents({})

