from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import math
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.mongodb import db_manager
from app.models.enums import SeverityLevel, EmergencyType, ReportStatus, SituationStatus, ResourceStatus
from app.models.map import PublicEmergencyHotspot, PublicActiveHotspotsResponse, OfficerMapDataResponse
from app.models.situation import SituationCluster
from app.models.officer import OfficerReportDetailResponse
from app.models.resource import ResourceResponse
from app.api.v1.endpoints.situations import parse_situation_doc
from app.api.v1.endpoints.officer import parse_report_document
from app.api.v1.endpoints.resources import parse_resource_doc


ACTIVE_SITUATION_STATUSES = [
    SituationStatus.ACTIVE.value,
    SituationStatus.RESPONSE_IN_PROGRESS.value,
    SituationStatus.OPERATIONS_COMPLETED.value,
    SituationStatus.OFFICER_REVIEW.value,
    SituationStatus.MONITORING.value,
    SituationStatus.CONTAINED.value,
]

RESOLVED_SITUATION_STATUSES = [
    SituationStatus.RESOLVED.value,
    SituationStatus.CLOSED.value,
]


class MapService:
    @classmethod
    async def get_public_active_hotspots(
        cls,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> PublicActiveHotspotsResponse:
        """
        Public-safe aggregation of REAL active emergency hotspots directly from MongoDB Atlas.
        Excludes all resolved/closed incidents. Strips all PII and sensitive operational telemetry.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        now_utc = datetime.now(timezone.utc)
        hotspots: List[PublicEmergencyHotspot] = []
        covered_report_ids = set()
        total_active_incidents = 0

        # 1. Fetch Authoritative Active Situations
        situations_cursor = db["situations"].find({
            "status": {"$nin": RESOLVED_SITUATION_STATUSES}
        }).sort("updated_at", -1)

        sit_index = 1
        async for doc in situations_cursor:
            sit_obj = parse_situation_doc(doc)
            # Count only active (non-resolved, non-rejected) reports in this situation
            active_rep_count = await db["citizen_reports"].count_documents({
                "report_id": {"$in": sit_obj.report_ids},
                "status": {"$nin": [ReportStatus.RESOLVED.value, ReportStatus.REJECTED.value]}
            })
            if active_rep_count == 0:
                await db["situations"].update_one(
                    {"situation_id": sit_obj.situation_id},
                    {"$set": {"status": SituationStatus.RESOLVED.value, "updated_at": now_utc}}
                )
                continue

            lat = sit_obj.center_location.latitude
            lng = sit_obj.center_location.longitude

            # Truncate coordinates to ~3 decimal places for public privacy
            gen_lat = round(float(lat), 3)
            gen_lng = round(float(lng), 3)

            total_active_incidents += active_rep_count
            for r_id in sit_obj.report_ids:
                covered_report_ids.add(r_id)

            radius = sit_obj.impact_zone.radius_km if sit_obj.impact_zone else 1.5
            area_name = sit_obj.center_location.zone_or_district or "Operational Response Sector"

            hotspots.append(PublicEmergencyHotspot(
                hotspot_id=f"HOTSPOT-ACT-{sit_index:03d}",
                latitude=gen_lat,
                longitude=gen_lng,
                severity_level=sit_obj.severity_level,
                impact_radius_km=round(radius, 2),
                active_incident_count=active_rep_count,
                emergency_type=sit_obj.emergency_type,
                general_area_name=area_name,
                last_updated_at=sit_obj.updated_at or now_utc,
            ))
            sit_index += 1

        # 2. Fetch Standalone Active Reports not clustered into above situations
        reports_cursor = db["citizen_reports"].find({
            "status": {"$nin": [ReportStatus.RESOLVED.value, ReportStatus.REJECTED.value]}
        }).sort("created_at", -1).limit(100)

        async for r_doc in reports_cursor:
            r_id = r_doc.get("report_id")
            if r_id in covered_report_ids:
                continue

            loc = r_doc.get("location", {})
            r_lat = loc.get("latitude")
            r_lng = loc.get("longitude")
            if r_lat is None or r_lng is None:
                continue

            total_active_incidents += 1
            gen_lat = round(float(r_lat), 3)
            gen_lng = round(float(r_lng), 3)

            raw_et = r_doc.get("emergency_type", EmergencyType.OTHER.value)
            et_enum = EmergencyType(raw_et) if raw_et in [e.value for e in EmergencyType] else EmergencyType.OTHER

            # Map priority/risk to severity level
            priority_val = str(r_doc.get("priority", "MEDIUM")).upper()
            sev_level = SeverityLevel.MEDIUM
            if priority_val == "CRITICAL":
                sev_level = SeverityLevel.CRITICAL
            elif priority_val == "HIGH":
                sev_level = SeverityLevel.HIGH
            elif priority_val == "LOW":
                sev_level = SeverityLevel.LOW

            area_name = loc.get("zone_or_district") or loc.get("city") or "Operational Response Sector"

            hotspots.append(PublicEmergencyHotspot(
                hotspot_id=f"HOTSPOT-ACT-{sit_index:03d}",
                latitude=gen_lat,
                longitude=gen_lng,
                severity_level=sev_level,
                impact_radius_km=1.0,
                active_incident_count=1,
                emergency_type=et_enum,
                general_area_name=area_name,
                last_updated_at=r_doc.get("updated_at") or r_doc.get("created_at") or now_utc,
            ))
            sit_index += 1

        return PublicActiveHotspotsResponse(
            hotspots=hotspots,
            total_active_hotspots=len(hotspots),
            total_active_incidents=total_active_incidents,
            last_updated_at=now_utc,
        )

    @classmethod
    async def get_officer_map_data(
        cls,
        view_mode: str = "active",
        emergency_type: Optional[EmergencyType] = None,
        severity_level: Optional[SeverityLevel] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> OfficerMapDataResponse:
        """
        Authorized Officer geospatial layer aggregation with explicit active vs historical partitioning.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("Database connection is not initialized.")

        now_utc = datetime.now(timezone.utc)
        clean_mode = view_mode.lower().strip() if view_mode else "active"
        if clean_mode not in ["active", "history", "all"]:
            clean_mode = "active"

        # 1. Build Situation Queries
        sit_query: Dict[str, Any] = {}
        if clean_mode == "active":
            sit_query["status"] = {"$nin": RESOLVED_SITUATION_STATUSES}
        elif clean_mode == "history":
            sit_query["status"] = {"$in": RESOLVED_SITUATION_STATUSES}

        if emergency_type:
            sit_query["emergency_type"] = emergency_type.value
        if severity_level:
            sit_query["severity_level"] = severity_level.value

        # 2. Build Report Queries
        rep_query: Dict[str, Any] = {}
        if clean_mode == "active":
            rep_query["status"] = {"$nin": [ReportStatus.RESOLVED.value, ReportStatus.REJECTED.value]}
        elif clean_mode == "history":
            rep_query["status"] = {"$in": [ReportStatus.RESOLVED.value, ReportStatus.REJECTED.value]}

        if emergency_type:
            rep_query["emergency_type"] = emergency_type.value

        # Counts
        total_active_situations = await db["situations"].count_documents({"status": {"$nin": RESOLVED_SITUATION_STATUSES}})
        total_resolved_situations = await db["situations"].count_documents({"status": {"$in": RESOLVED_SITUATION_STATUSES}})
        total_active_reports = await db["citizen_reports"].count_documents({"status": {"$nin": [ReportStatus.RESOLVED.value, ReportStatus.REJECTED.value]}})
        total_resolved_reports = await db["citizen_reports"].count_documents({"status": {"$in": [ReportStatus.RESOLVED.value, ReportStatus.REJECTED.value]}})

        # Fetch Situations
        situations_cursor = db["situations"].find(sit_query).sort("updated_at", -1).limit(100)
        situations: List[SituationCluster] = []
        async for doc in situations_cursor:
            sit_obj = parse_situation_doc(doc)
            if clean_mode == "active":
                act_cnt = await db["citizen_reports"].count_documents({
                    "report_id": {"$in": sit_obj.report_ids},
                    "status": {"$nin": [ReportStatus.RESOLVED.value, ReportStatus.REJECTED.value]}
                })
                if act_cnt == 0:
                    continue
            situations.append(sit_obj)

        # Fetch Reports
        reports_cursor = db["citizen_reports"].find(rep_query).sort("created_at", -1).limit(100)
        reports: List[OfficerReportItemResponse] = []
        async for doc in reports_cursor:
            reports.append(parse_report_document(doc))

        # Fetch Shelters (always active operational resources)
        shelters_cursor = db["resources"].find({
            "resource_type": "Shelter",
            "is_deleted": {"$ne": True},
        }).sort("created_at", -1).limit(50)
        shelters: List[ResourceResponse] = []
        async for doc in shelters_cursor:
            shelters.append(parse_resource_doc(doc))

        return OfficerMapDataResponse(
            view_mode=clean_mode,
            situations=situations,
            reports=reports,
            shelters=shelters,
            total_active_situations=total_active_situations,
            total_resolved_situations=total_resolved_situations,
            total_active_reports=total_active_reports,
            total_resolved_reports=total_resolved_reports,
            last_updated_at=now_utc,
        )
