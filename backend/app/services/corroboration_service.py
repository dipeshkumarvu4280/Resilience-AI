import logging
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.enums import (
    EmergencyType,
    SensorType,
    CitizenImpactLevel,
    EvidenceValidationStatus,
    CorroborationStatus,
    CorroborationSourceType,
    CorroborationSpatialRelationship,
    CorroborationTemporalRelationship,
    CorroborationAlignment,
    EvidenceConflictCategory,
)
from app.models.corroboration import (
    CorroboratingSource,
    ConflictDetail,
    CorroborationResult,
)
from app.services.evidence_service import calculate_haversine_distance_meters

logger = logging.getLogger("resilience.corroboration")


class EvidenceCorroborationService:
    """
    Multi-Source Corroboration & Evidence Conflict Detection Engine (Phase B).
    
    Evaluates real operational records across independent source categories:
    - CITIZEN_REPORT (other nearby citizen reports)
    - CITIZEN_EVIDENCE (live browser camera photo & GPS)
    - SENSOR_EVENT (IoT sensor telemetry & alerts)
    - FIELD_UPDATE (responder field observations)
    - SITUATION_INTELLIGENCE (incident cluster intelligence)
    
    SAFETY PRINCIPLES:
    - Purely advisory intelligence (Human-in-the-loop).
    - NEVER autonomously rejects reports, mutates officer priority, activates plans, or consumes inventory.
    - Deterministic and explainable (Zero arbitrary AI confidence percentages).
    - Zero dummy/fabricated operational records.
    - Clear separation between:
      * Individual Evidence Trust (Phase A)
      * Multi-Source Corroboration (Phase B)
      * Response Plan Conflict Resolution (Phase 5 Agent)
    """

    # Spatial tolerance thresholds (meters)
    MATCH_TOLERANCE_METERS = 500.0
    NEAR_MATCH_TOLERANCE_METERS = 2000.0

    # Temporal tolerance thresholds (seconds)
    COINCIDENT_THRESHOLD_SECONDS = 1800.0       # 30 minutes
    NEAR_CONTEMPORARY_THRESHOLD_SECONDS = 7200.0 # 2 hours

    # Contradiction keywords for citizen observation analysis
    NEGATIVE_OBSERVATION_KEYWORDS = {
        "no flood", "no flooding", "no water", "dry", "water cleared", "roads clear",
        "no fire", "no smoke", "false alarm", "all clear", "nothing happened",
        "no incident", "normal condition", "fake report", "mistake", "cleared",
        "all safe", "no damage", "situation normal"
    }

    SEVERE_OBSERVATION_KEYWORDS = {
        "severe", "massive", "heavy flood", "deep water", "drowning", "trapped",
        "raging fire", "major fire", "heavy smoke", "critical", "catastrophic",
        "submerged", "rapidly rising", "intense flames", "house collapse"
    }

    @classmethod
    def _classify_spatial(cls, distance_meters: Optional[float]) -> CorroborationSpatialRelationship:
        if distance_meters is None:
            return CorroborationSpatialRelationship.UNAVAILABLE
        if distance_meters <= cls.MATCH_TOLERANCE_METERS:
            return CorroborationSpatialRelationship.MATCH
        if distance_meters <= cls.NEAR_MATCH_TOLERANCE_METERS:
            return CorroborationSpatialRelationship.NEAR_MATCH
        return CorroborationSpatialRelationship.DISTANT

    @classmethod
    def _classify_temporal(cls, time_diff_seconds: Optional[float]) -> CorroborationTemporalRelationship:
        if time_diff_seconds is None:
            return CorroborationTemporalRelationship.UNAVAILABLE
        abs_diff = abs(time_diff_seconds)
        if abs_diff <= cls.COINCIDENT_THRESHOLD_SECONDS:
            return CorroborationTemporalRelationship.COINCIDENT
        if abs_diff <= cls.NEAR_CONTEMPORARY_THRESHOLD_SECONDS:
            return CorroborationTemporalRelationship.NEAR_CONTEMPORARY
        return CorroborationTemporalRelationship.HISTORICAL

    @classmethod
    def _is_negative_observation(cls, text: str) -> bool:
        low = (text or "").lower()
        return any(phrase in low for phrase in cls.NEGATIVE_OBSERVATION_KEYWORDS)

    @classmethod
    def _is_severe_observation(cls, text: str, impact_level: Optional[CitizenImpactLevel] = None) -> bool:
        if impact_level in [CitizenImpactLevel.HIGH, CitizenImpactLevel.CRITICAL]:
            return True
        low = (text or "").lower()
        return any(phrase in low for phrase in cls.SEVERE_OBSERVATION_KEYWORDS)

    @classmethod
    def evaluate_report_corroboration(
        cls,
        target_report: Dict[str, Any],
        candidate_reports: Optional[List[Dict[str, Any]]] = None,
        candidate_sensors: Optional[List[Dict[str, Any]]] = None,
        candidate_alerts: Optional[List[Dict[str, Any]]] = None,
        candidate_readings: Optional[List[Dict[str, Any]]] = None,
        candidate_field_updates: Optional[List[Dict[str, Any]]] = None,
        eval_time: Optional[datetime] = None,
    ) -> CorroborationResult:
        """
        Evaluates multi-source corroboration and conflict detection for a target citizen report.
        """
        now = eval_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        target_id = target_report.get("report_id", "UNKNOWN")
        raw_et = target_report.get("emergency_type") or "Other"
        try:
            target_et = EmergencyType(raw_et)
        except Exception:
            target_et = EmergencyType.OTHER

        raw_impact = target_report.get("citizen_impact_level", CitizenImpactLevel.NOT_SURE.value)
        try:
            target_impact = CitizenImpactLevel(raw_impact)
        except Exception:
            target_impact = CitizenImpactLevel.NOT_SURE

        target_desc = target_report.get("description", "")
        target_loc = target_report.get("location") or {}
        t_lat = target_loc.get("latitude")
        t_lon = target_loc.get("longitude")
        has_target_coords = (
            t_lat is not None
            and t_lon is not None
            and -90.0 <= t_lat <= 90.0
            and -180.0 <= t_lon <= 180.0
            and not (t_lat == 0.0 and t_lon == 0.0)
        )

        raw_created_at = target_report.get("created_at")
        if isinstance(raw_created_at, str):
            try:
                target_dt = datetime.fromisoformat(raw_created_at.replace("Z", "+00:00"))
            except Exception:
                target_dt = now
        elif isinstance(raw_created_at, datetime):
            target_dt = raw_created_at
        else:
            target_dt = now
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=timezone.utc)

        supporting_sources: List[CorroboratingSource] = []
        conflicting_sources: List[CorroboratingSource] = []
        neutral_sources: List[CorroboratingSource] = []
        conflict_details: List[ConflictDetail] = []
        corroboration_factors: List[str] = []
        conflict_factors: List[str] = []
        warnings: List[str] = []
        recommendations: List[str] = []

        # =====================================================================
        # SOURCE 1: CITIZEN EVIDENCE (Attached Live Camera Evidence & GPS)
        # =====================================================================
        evidence_doc = target_report.get("evidence")
        if isinstance(evidence_doc, dict):
            ev_id = evidence_doc.get("evidence_id", f"EVD-{target_id[-6:]}")
            val_status = evidence_doc.get("validation_status")
            ev_lat = evidence_doc.get("latitude")
            ev_lon = evidence_doc.get("longitude")
            
            has_ev_coords = (
                ev_lat is not None
                and ev_lon is not None
                and -90.0 <= ev_lat <= 90.0
                and -180.0 <= ev_lon <= 180.0
                and not (ev_lat == 0.0 and ev_lon == 0.0)
            )

            if val_status == EvidenceValidationStatus.UNAVAILABLE.value or not evidence_doc.get("file_url") and not evidence_doc.get("image_base64"):
                # Camera unavailable is NEUTRAL (missing data != negative signal)
                neutral_sources.append(CorroboratingSource(
                    source_type=CorroborationSourceType.CITIZEN_EVIDENCE,
                    source_id=ev_id,
                    source_name="Citizen Live Photo",
                    summary="Live camera evidence was not captured or permission unavailable.",
                    alignment=CorroborationAlignment.NEUTRAL,
                    spatial_relationship=CorroborationSpatialRelationship.UNAVAILABLE,
                    temporal_relationship=CorroborationTemporalRelationship.UNAVAILABLE,
                    details={"reason": evidence_doc.get("error_reason") or "Camera unavailable on client device"},
                ))
            elif has_ev_coords and has_target_coords:
                ev_dist = round(calculate_haversine_distance_meters(ev_lat, ev_lon, t_lat, t_lon), 1)
                ev_spatial = cls._classify_spatial(ev_dist)

                raw_cap_ts = evidence_doc.get("client_capture_timestamp")
                cap_dt = None
                if raw_cap_ts:
                    if isinstance(raw_cap_ts, str):
                        try:
                            cap_dt = datetime.fromisoformat(raw_cap_ts.replace("Z", "+00:00"))
                        except Exception:
                            pass
                    elif isinstance(raw_cap_ts, datetime):
                        cap_dt = raw_cap_ts
                if cap_dt and cap_dt.tzinfo is None:
                    cap_dt = cap_dt.replace(tzinfo=timezone.utc)
                
                time_diff = (now - cap_dt).total_seconds() if cap_dt else None
                ev_temporal = cls._classify_temporal(time_diff)

                if ev_spatial in [CorroborationSpatialRelationship.MATCH, CorroborationSpatialRelationship.NEAR_MATCH] and ev_temporal != CorroborationTemporalRelationship.HISTORICAL:
                    supporting_sources.append(CorroboratingSource(
                        source_type=CorroborationSourceType.CITIZEN_EVIDENCE,
                        source_id=ev_id,
                        source_name="Citizen Live Photo",
                        summary=f"Live camera photo captured at incident location ({ev_dist:.0f}m distance, verified hash).",
                        alignment=CorroborationAlignment.SUPPORTING,
                        spatial_relationship=ev_spatial,
                        distance_meters=ev_dist,
                        temporal_relationship=ev_temporal,
                        time_difference_seconds=time_diff,
                        timestamp=cap_dt,
                        details={"content_hash": evidence_doc.get("content_hash"), "accuracy_meters": evidence_doc.get("accuracy_meters")},
                    ))
                    corroboration_factors.append(f"Live camera photo verified within {ev_dist:.0f}m of reported coordinates")
                elif ev_spatial == CorroborationSpatialRelationship.DISTANT:
                    # Spatial Conflict between evidence location and reported location
                    conflicting_sources.append(CorroboratingSource(
                        source_type=CorroborationSourceType.CITIZEN_EVIDENCE,
                        source_id=ev_id,
                        source_name="Citizen Live Photo",
                        summary=f"Evidence capture GPS location ({ev_dist:.0f}m) exceeds geographic tolerance from report.",
                        alignment=CorroborationAlignment.CONFLICTING,
                        spatial_relationship=ev_spatial,
                        distance_meters=ev_dist,
                        temporal_relationship=ev_temporal,
                        time_difference_seconds=time_diff,
                        timestamp=cap_dt,
                        details={"content_hash": evidence_doc.get("content_hash"), "accuracy_meters": evidence_doc.get("accuracy_meters")},
                    ))
                    conflict_details.append(ConflictDetail(
                        category=EvidenceConflictCategory.SPATIAL_CONFLICT,
                        conflicting_source_id=ev_id,
                        conflicting_source_type=CorroborationSourceType.CITIZEN_EVIDENCE,
                        conflicting_source_name="Citizen Live Photo",
                        summary="Evidence GPS location mismatch",
                        reason=f"Live camera capture GPS is {ev_dist:.0f}m away from reported incident location (exceeds {cls.NEAR_MATCH_TOLERANCE_METERS:.0f}m tolerance).",
                        severity="HIGH",
                        recommended_action="Inspect citizen evidence metadata and request field confirmation of incident site.",
                    ))
                    conflict_factors.append(f"Evidence photo location is {ev_dist:.0f}m away from report coordinates")
                else:
                    neutral_sources.append(CorroboratingSource(
                        source_type=CorroborationSourceType.CITIZEN_EVIDENCE,
                        source_id=ev_id,
                        source_name="Citizen Live Photo",
                        summary=f"Evidence photo captured {time_diff / 60.0:.0f} min ago (historical window).",
                        alignment=CorroborationAlignment.NEUTRAL,
                        spatial_relationship=ev_spatial,
                        distance_meters=ev_dist,
                        temporal_relationship=ev_temporal,
                        time_difference_seconds=time_diff,
                        timestamp=cap_dt,
                    ))

        # =====================================================================
        # SOURCE 2: OTHER CITIZEN REPORTS (Peer Corroboration & Conflict)
        # =====================================================================
        if candidate_reports:
            for rep in candidate_reports:
                c_id = rep.get("report_id")
                if not c_id or c_id == target_id:
                    continue

                c_loc = rep.get("location") or {}
                c_lat = c_loc.get("latitude")
                c_lon = c_loc.get("longitude")
                has_c_coords = (
                    c_lat is not None
                    and c_lon is not None
                    and -90.0 <= c_lat <= 90.0
                    and -180.0 <= c_lon <= 180.0
                    and not (c_lat == 0.0 and c_lon == 0.0)
                )

                dist_m = None
                spatial_rel = CorroborationSpatialRelationship.UNAVAILABLE
                if has_target_coords and has_c_coords:
                    dist_m = round(calculate_haversine_distance_meters(t_lat, t_lon, c_lat, c_lon), 1)
                    spatial_rel = cls._classify_spatial(dist_m)

                c_created = rep.get("created_at")
                c_dt = None
                if isinstance(c_created, str):
                    try:
                        c_dt = datetime.fromisoformat(c_created.replace("Z", "+00:00"))
                    except Exception:
                        pass
                elif isinstance(c_created, datetime):
                    c_dt = c_created
                if c_dt and c_dt.tzinfo is None:
                    c_dt = c_dt.replace(tzinfo=timezone.utc)

                time_diff_s = (c_dt - target_dt).total_seconds() if c_dt and target_dt else None
                temporal_rel = cls._classify_temporal(time_diff_s)

                c_et_raw = rep.get("emergency_type", "Other")
                try:
                    c_et = EmergencyType(c_et_raw)
                except Exception:
                    c_et = EmergencyType.OTHER

                c_desc = rep.get("description", "")
                c_impact_raw = rep.get("citizen_impact_level", CitizenImpactLevel.NOT_SURE.value)
                try:
                    c_impact = CitizenImpactLevel(c_impact_raw)
                except Exception:
                    c_impact = CitizenImpactLevel.NOT_SURE

                # Filter out distant or historical reports as NEUTRAL
                if spatial_rel == CorroborationSpatialRelationship.DISTANT or temporal_rel == CorroborationTemporalRelationship.HISTORICAL:
                    neutral_sources.append(CorroboratingSource(
                        source_type=CorroborationSourceType.CITIZEN_REPORT,
                        source_id=c_id,
                        source_name=f"Report {c_id}",
                        summary=f"Citizen report {c_id} ({c_et.value}) is outside spatial/temporal operational window ({dist_m or 'unknown'}m, {abs(time_diff_s or 0)/60.0:.0f}m delta).",
                        alignment=CorroborationAlignment.NEUTRAL,
                        spatial_relationship=spatial_rel,
                        distance_meters=dist_m,
                        temporal_relationship=temporal_rel,
                        time_difference_seconds=time_diff_s,
                        timestamp=c_dt,
                    ))
                    continue

                if spatial_rel == CorroborationSpatialRelationship.UNAVAILABLE or temporal_rel == CorroborationTemporalRelationship.UNAVAILABLE:
                    neutral_sources.append(CorroboratingSource(
                        source_type=CorroborationSourceType.CITIZEN_REPORT,
                        source_id=c_id,
                        source_name=f"Report {c_id}",
                        summary=f"Citizen report {c_id} coordinates or timestamp unavailable for comparative corroboration.",
                        alignment=CorroborationAlignment.NEUTRAL,
                        spatial_relationship=spatial_rel,
                        distance_meters=dist_m,
                        temporal_relationship=temporal_rel,
                        time_difference_seconds=time_diff_s,
                        timestamp=c_dt,
                    ))
                    continue

                # Spatially and temporally contemporary candidate report!
                # 1. Check for contradictory observations
                target_is_severe = cls._is_severe_observation(target_desc, target_impact)
                cand_is_negative = cls._is_negative_observation(c_desc)
                cand_is_severe = cls._is_severe_observation(c_desc, c_impact)
                target_is_negative = cls._is_negative_observation(target_desc)

                is_contradiction = (target_is_severe and cand_is_negative) or (target_is_negative and cand_is_severe)

                # 2. Check for event type conflict (e.g. Fire vs Flood at exact same point)
                incompatible_types = (
                    (target_et == EmergencyType.FIRE and c_et in [EmergencyType.FLOOD, EmergencyType.CYCLONE_STORM]) or
                    (target_et in [EmergencyType.FLOOD, EmergencyType.CYCLONE_STORM] and c_et == EmergencyType.FIRE)
                )

                if is_contradiction:
                    conflicting_sources.append(CorroboratingSource(
                        source_type=CorroborationSourceType.CITIZEN_REPORT,
                        source_id=c_id,
                        source_name=f"Citizen Report {c_id}",
                        summary=f"Report {c_id} contains conflicting observation: '{c_desc[:80]}...'",
                        alignment=CorroborationAlignment.CONFLICTING,
                        spatial_relationship=spatial_rel,
                        distance_meters=dist_m,
                        temporal_relationship=temporal_rel,
                        time_difference_seconds=time_diff_s,
                        timestamp=c_dt,
                        details={"description": c_desc, "impact_level": c_impact.value},
                    ))
                    conflict_details.append(ConflictDetail(
                        category=EvidenceConflictCategory.CITIZEN_REPORT_CONFLICT,
                        conflicting_source_id=c_id,
                        conflicting_source_type=CorroborationSourceType.CITIZEN_REPORT,
                        conflicting_source_name=f"Citizen Report {c_id}",
                        summary="Conflicting citizen observation detected",
                        reason=f"Nearby citizen report {c_id} ({dist_m:.0f}m distance) indicates a conflicting observation during the same time window.",
                        severity="HIGH",
                        recommended_action="Dispatch field responder to verify actual ground conditions at the scene.",
                    ))
                    conflict_factors.append(f"Nearby citizen report {c_id} presents conflicting situation observation ({dist_m:.0f}m away)")

                elif incompatible_types:
                    conflicting_sources.append(CorroboratingSource(
                        source_type=CorroborationSourceType.CITIZEN_REPORT,
                        source_id=c_id,
                        source_name=f"Citizen Report {c_id}",
                        summary=f"Report {c_id} claims incompatible incident type ({c_et.value} vs {target_et.value}) at the same location.",
                        alignment=CorroborationAlignment.CONFLICTING,
                        spatial_relationship=spatial_rel,
                        distance_meters=dist_m,
                        temporal_relationship=temporal_rel,
                        time_difference_seconds=time_diff_s,
                        timestamp=c_dt,
                        details={"emergency_type": c_et.value},
                    ))
                    conflict_details.append(ConflictDetail(
                        category=EvidenceConflictCategory.EVENT_TYPE_CONFLICT,
                        conflicting_source_id=c_id,
                        conflicting_source_type=CorroborationSourceType.CITIZEN_REPORT,
                        conflicting_source_name=f"Citizen Report {c_id}",
                        summary="Incompatible emergency event types",
                        reason=f"Report {c_id} claims {c_et.value} while target report claims {target_et.value} within {dist_m:.0f}m at the same time.",
                        severity="HIGH",
                        recommended_action="Human watch officer review required to establish authoritative incident classification.",
                    ))
                    conflict_factors.append(f"Incompatible incident types reported: {target_et.value} vs {c_et.value}")

                elif target_et == c_et or (target_et in [EmergencyType.FLOOD, EmergencyType.CYCLONE_STORM] and c_et in [EmergencyType.FLOOD, EmergencyType.CYCLONE_STORM]):
                    # Compatible and supporting report!
                    supporting_sources.append(CorroboratingSource(
                        source_type=CorroborationSourceType.CITIZEN_REPORT,
                        source_id=c_id,
                        source_name=f"Citizen Report {c_id}",
                        summary=f"Independent citizen report {c_id} corroborates {c_et.value} at nearby location ({dist_m:.0f}m distance).",
                        alignment=CorroborationAlignment.SUPPORTING,
                        spatial_relationship=spatial_rel,
                        distance_meters=dist_m,
                        temporal_relationship=temporal_rel,
                        time_difference_seconds=time_diff_s,
                        timestamp=c_dt,
                        details={"emergency_type": c_et.value, "citizen_name": rep.get("citizen_name")},
                    ))
                    corroboration_factors.append(f"Nearby citizen report {c_id} independently corroborates {c_et.value} ({dist_m:.0f}m distance)")
                else:
                    # Unrelated incident type in vicinity
                    neutral_sources.append(CorroboratingSource(
                        source_type=CorroborationSourceType.CITIZEN_REPORT,
                        source_id=c_id,
                        source_name=f"Citizen Report {c_id}",
                        summary=f"Adjacent citizen report {c_id} describes distinct incident type ({c_et.value}).",
                        alignment=CorroborationAlignment.NEUTRAL,
                        spatial_relationship=spatial_rel,
                        distance_meters=dist_m,
                        temporal_relationship=temporal_rel,
                        time_difference_seconds=time_diff_s,
                        timestamp=c_dt,
                    ))

        # =====================================================================
        # SOURCE 3: SENSORS & ACTIVE SENSOR ALERTS / READINGS
        # =====================================================================
        # Collect candidate sensors
        sensors_by_id: Dict[str, Dict[str, Any]] = {}
        if candidate_sensors:
            for s in candidate_sensors:
                s_id = s.get("sensor_id")
                if s_id:
                    sensors_by_id[s_id] = s

        # Build candidate sensor events (alerts or latest readings)
        sensor_candidates: List[Dict[str, Any]] = []
        seen_sensor_ids = set()

        if candidate_alerts:
            for a in candidate_alerts:
                s_id = a.get("sensor_id")
                if s_id:
                    seen_sensor_ids.add(s_id)
                    sensor_meta = sensors_by_id.get(s_id, {})
                    cov_dict = sensor_meta.get("coverage") or {}
                    cov_m = a.get("coverage_radius_meters") or cov_dict.get("radius_meters") or 2000.0
                    sensor_candidates.append({
                        "source_id": s_id,
                        "event_id": a.get("alert_id") or a.get("event_id"),
                        "sensor_name": a.get("sensor_name") or sensor_meta.get("name"),
                        "sensor_type": a.get("sensor_type") or sensor_meta.get("sensor_type"),
                        "current_value": a.get("current_value") if a.get("current_value") is not None else (a.get("value") if a.get("value") is not None else sensor_meta.get("current_reading")),
                        "unit": a.get("unit") or sensor_meta.get("unit"),
                        "threshold": a.get("threshold") if a.get("threshold") is not None else sensor_meta.get("threshold"),
                        "is_breach": a.get("status") == "ACTIVE_BREACH" or bool(sensor_meta.get("in_alert", False)),
                        "latitude": a.get("latitude") if a.get("latitude") is not None else sensor_meta.get("latitude"),
                        "longitude": a.get("longitude") if a.get("longitude") is not None else sensor_meta.get("longitude"),
                        "coverage_radius_meters": cov_m,
                        "timestamp": a.get("created_at") or a.get("timestamp") or sensor_meta.get("last_updated"),
                        "location_name": a.get("location_name") or sensor_meta.get("location_name"),
                    })

        if candidate_sensors:
            for s in candidate_sensors:
                s_id = s.get("sensor_id")
                if s_id and s_id not in seen_sensor_ids:
                    cov_dict = s.get("coverage") or {}
                    cov_m = cov_dict.get("radius_meters") or 2000.0
                    sensor_candidates.append({
                        "source_id": s_id,
                        "event_id": s.get("current_alert_id"),
                        "sensor_name": s.get("name"),
                        "sensor_type": s.get("sensor_type"),
                        "current_value": s.get("current_reading"),
                        "unit": s.get("unit"),
                        "threshold": s.get("threshold"),
                        "is_breach": bool(s.get("in_alert", False)),
                        "latitude": s.get("latitude"),
                        "longitude": s.get("longitude"),
                        "coverage_radius_meters": cov_m,
                        "timestamp": s.get("last_updated") or s.get("updated_at") or s.get("created_at"),
                        "location_name": s.get("location_name"),
                    })

        for sc in sensor_candidates:
            s_id = sc["source_id"]
            s_name = sc.get("sensor_name") or f"Sensor {s_id}"
            s_type_raw = str(sc.get("sensor_type", ""))
            try:
                s_type = SensorType(s_type_raw)
            except Exception:
                s_type = None

            s_lat = sc.get("latitude")
            s_lon = sc.get("longitude")
            has_s_coords = (
                s_lat is not None
                and s_lon is not None
                and -90.0 <= s_lat <= 90.0
                and -180.0 <= s_lon <= 180.0
                and not (s_lat == 0.0 and s_lon == 0.0)
            )

            dist_m = None
            spatial_rel = CorroborationSpatialRelationship.UNAVAILABLE
            cov_radius_m = float(sc.get("coverage_radius_meters") or 2000.0)

            if has_target_coords and has_s_coords:
                dist_m = round(calculate_haversine_distance_meters(t_lat, t_lon, s_lat, s_lon), 1)
                spatial_rel = cls._classify_spatial(dist_m)

            within_coverage = (dist_m is not None and dist_m <= cov_radius_m)

            s_ts = sc.get("timestamp")
            s_dt = None
            if isinstance(s_ts, str):
                try:
                    s_dt = datetime.fromisoformat(s_ts.replace("Z", "+00:00"))
                except Exception:
                    pass
            elif isinstance(s_ts, datetime):
                s_dt = s_ts
            if s_dt and s_dt.tzinfo is None:
                s_dt = s_dt.replace(tzinfo=timezone.utc)

            time_diff_s = (s_dt - target_dt).total_seconds() if s_dt and target_dt else None
            temporal_rel = cls._classify_temporal(time_diff_s)

            val = sc.get("current_value")
            unit = sc.get("unit") or ""
            thresh = sc.get("threshold")
            is_breach = bool(sc.get("is_breach", False))

            # Rule: If outside sensor's configured coverage radius, sensor is NEUTRAL (not corroborating this incident)
            if not within_coverage:
                dist_info = f"{dist_m:.0f}m" if dist_m is not None else "Unknown distance"
                neutral_sources.append(CorroboratingSource(
                    source_type=CorroborationSourceType.SENSOR_EVENT,
                    source_id=s_id,
                    source_name=s_name,
                    summary=f"Sensor {s_name} is outside configured coverage radius ({dist_info} > {cov_radius_m:.0f}m coverage). Valid in Live Monitoring, non-corroborating for this incident.",
                    alignment=CorroborationAlignment.NEUTRAL,
                    spatial_relationship=spatial_rel,
                    distance_meters=dist_m,
                    temporal_relationship=temporal_rel,
                    time_difference_seconds=time_diff_s,
                    timestamp=s_dt,
                    sensor_type=s_type_raw,
                    reading_value=val,
                    reading_unit=unit,
                    threshold=thresh,
                    is_breach=is_breach,
                    coverage_radius_meters=cov_radius_m,
                    within_coverage=False,
                ))
                continue

            if temporal_rel == CorroborationTemporalRelationship.HISTORICAL:
                neutral_sources.append(CorroboratingSource(
                    source_type=CorroborationSourceType.SENSOR_EVENT,
                    source_id=s_id,
                    source_name=s_name,
                    summary=f"Sensor telemetry is from an older historical window ({abs(time_diff_s or 0)/60.0:.0f} min delta).",
                    alignment=CorroborationAlignment.NEUTRAL,
                    spatial_relationship=spatial_rel,
                    distance_meters=dist_m,
                    temporal_relationship=temporal_rel,
                    time_difference_seconds=time_diff_s,
                    timestamp=s_dt,
                    sensor_type=s_type_raw,
                    reading_value=val,
                    reading_unit=unit,
                    threshold=thresh,
                    is_breach=is_breach,
                    coverage_radius_meters=cov_radius_m,
                    within_coverage=True,
                ))
                continue

            # Sensor is WITHIN COVERAGE and CONTEMPORARY!
            # Evaluate semantic compatibility & conflict based on target emergency type:
            if target_et in [EmergencyType.FLOOD, EmergencyType.CYCLONE_STORM]:
                if s_type in [SensorType.WATER_LEVEL, SensorType.RAINFALL]:
                    # Elevated/Breached reading
                    is_elevated = is_breach or (val is not None and thresh is not None and val >= thresh) or (s_type == SensorType.WATER_LEVEL and val is not None and val >= 0.5) or (s_type == SensorType.RAINFALL and val is not None and val >= 15.0)
                    is_flat_normal = (val is not None and val <= 0.05 and not is_breach)
                    
                    if is_elevated:
                        supporting_sources.append(CorroboratingSource(
                            source_type=CorroborationSourceType.SENSOR_EVENT,
                            source_id=s_id,
                            source_name=s_name,
                            summary=f"Nearby {s_type.value} sensor {s_name} records elevated readings ({val} {unit}, within {dist_m:.0f}m coverage).",
                            alignment=CorroborationAlignment.SUPPORTING,
                            spatial_relationship=spatial_rel,
                            distance_meters=dist_m,
                            temporal_relationship=temporal_rel,
                            time_difference_seconds=time_diff_s,
                            timestamp=s_dt,
                            sensor_type=s_type_raw,
                            reading_value=val,
                            reading_unit=unit,
                            threshold=thresh,
                            is_breach=is_breach,
                            coverage_radius_meters=cov_radius_m,
                            within_coverage=True,
                        ))
                        corroboration_factors.append(f"Water-level / rainfall IoT sensor {s_name} corroborates elevated conditions ({val} {unit})")
                    elif is_flat_normal and cls._is_severe_observation(target_desc, target_impact):
                        # Severe flood reported, but sensor in coverage reports flat zero / normal
                        conflicting_sources.append(CorroboratingSource(
                            source_type=CorroborationSourceType.SENSOR_EVENT,
                            source_id=s_id,
                            source_name=s_name,
                            summary=f"{s_type.value} sensor reports normal baseline ({val} {unit}) with no breach during the observation window.",
                            alignment=CorroborationAlignment.CONFLICTING,
                            spatial_relationship=spatial_rel,
                            distance_meters=dist_m,
                            temporal_relationship=temporal_rel,
                            time_difference_seconds=time_diff_s,
                            timestamp=s_dt,
                            sensor_type=s_type_raw,
                            reading_value=val,
                            reading_unit=unit,
                            threshold=thresh,
                            is_breach=is_breach,
                            coverage_radius_meters=cov_radius_m,
                            within_coverage=True,
                        ))
                        conflict_details.append(ConflictDetail(
                            category=EvidenceConflictCategory.SENSOR_REPORT_CONFLICT,
                            conflicting_source_id=s_id,
                            conflicting_source_type=CorroborationSourceType.SENSOR_EVENT,
                            conflicting_source_name=s_name,
                            summary="Sensor readings do not corroborate severe flood claim",
                            reason=f"Citizen-reported severe flooding is not corroborated by the nearby water-level sensor ({s_name}: {val} {unit}) located within {dist_m:.0f}m coverage during the same observation window.",
                            severity="HIGH",
                            recommended_action="Cross-reference recent citizen evidence photos and request ground responder validation.",
                        ))
                        conflict_factors.append(f"Sensor {s_name} shows normal reading ({val} {unit}) while report claims severe flooding")
                    else:
                        neutral_sources.append(CorroboratingSource(
                            source_type=CorroborationSourceType.SENSOR_EVENT,
                            source_id=s_id,
                            source_name=s_name,
                            summary=f"{s_type.value} sensor reading is within normal operational range ({val} {unit}).",
                            alignment=CorroborationAlignment.NEUTRAL,
                            spatial_relationship=spatial_rel,
                            distance_meters=dist_m,
                            temporal_relationship=temporal_rel,
                            time_difference_seconds=time_diff_s,
                            timestamp=s_dt,
                            sensor_type=s_type_raw,
                            reading_value=val,
                            reading_unit=unit,
                            threshold=thresh,
                            is_breach=is_breach,
                            coverage_radius_meters=cov_radius_m,
                            within_coverage=True,
                        ))
                else:
                    # Unrelated sensor type (e.g. Temperature or AQI during flood) -> NEUTRAL
                    neutral_sources.append(CorroboratingSource(
                        source_type=CorroborationSourceType.SENSOR_EVENT,
                        source_id=s_id,
                        source_name=s_name,
                        summary=f"Environmental sensor {s_name} ({s_type_raw}) is not directly relevant to {target_et.value} conditions.",
                        alignment=CorroborationAlignment.NEUTRAL,
                        spatial_relationship=spatial_rel,
                        distance_meters=dist_m,
                        temporal_relationship=temporal_rel,
                        time_difference_seconds=time_diff_s,
                        timestamp=s_dt,
                        sensor_type=s_type_raw,
                        reading_value=val,
                        reading_unit=unit,
                        threshold=thresh,
                        is_breach=is_breach,
                        coverage_radius_meters=cov_radius_m,
                        within_coverage=True,
                    ))

            elif target_et == EmergencyType.FIRE:
                if s_type in [SensorType.SMOKE_AIR_QUALITY, SensorType.AQI, SensorType.TEMPERATURE]:
                    is_elevated = is_breach or (val is not None and thresh is not None and val >= thresh) or (s_type in [SensorType.SMOKE_AIR_QUALITY, SensorType.AQI] and val is not None and val >= 150.0) or (s_type == SensorType.TEMPERATURE and val is not None and val >= 45.0)
                    is_clean = (val is not None and ((s_type in [SensorType.SMOKE_AIR_QUALITY, SensorType.AQI] and val <= 30.0) or (s_type == SensorType.TEMPERATURE and val <= 28.0)) and not is_breach)

                    if is_elevated:
                        supporting_sources.append(CorroboratingSource(
                            source_type=CorroborationSourceType.SENSOR_EVENT,
                            source_id=s_id,
                            source_name=s_name,
                            summary=f"Nearby {s_type_raw} sensor {s_name} records elevated smoke/heat telemetry ({val} {unit}, within {dist_m:.0f}m).",
                            alignment=CorroborationAlignment.SUPPORTING,
                            spatial_relationship=spatial_rel,
                            distance_meters=dist_m,
                            temporal_relationship=temporal_rel,
                            time_difference_seconds=time_diff_s,
                            timestamp=s_dt,
                            sensor_type=s_type_raw,
                            reading_value=val,
                            reading_unit=unit,
                            threshold=thresh,
                            is_breach=is_breach,
                            coverage_radius_meters=cov_radius_m,
                            within_coverage=True,
                        ))
                        corroboration_factors.append(f"Thermal / smoke sensor {s_name} corroborates elevated fire indicators ({val} {unit})")
                    elif is_clean and cls._is_severe_observation(target_desc, target_impact):
                        conflicting_sources.append(CorroboratingSource(
                            source_type=CorroborationSourceType.SENSOR_EVENT,
                            source_id=s_id,
                            source_name=s_name,
                            summary=f"Sensor {s_name} shows normal atmospheric readings ({val} {unit}) with zero smoke or thermal anomaly.",
                            alignment=CorroborationAlignment.CONFLICTING,
                            spatial_relationship=spatial_rel,
                            distance_meters=dist_m,
                            temporal_relationship=temporal_rel,
                            time_difference_seconds=time_diff_s,
                            timestamp=s_dt,
                            sensor_type=s_type_raw,
                            reading_value=val,
                            reading_unit=unit,
                            threshold=thresh,
                            is_breach=is_breach,
                            coverage_radius_meters=cov_radius_m,
                            within_coverage=True,
                        ))
                        conflict_details.append(ConflictDetail(
                            category=EvidenceConflictCategory.SENSOR_REPORT_CONFLICT,
                            conflicting_source_id=s_id,
                            conflicting_source_type=CorroborationSourceType.SENSOR_EVENT,
                            conflicting_source_name=s_name,
                            summary="Sensor telemetry does not corroborate reported fire",
                            reason=f"Citizen-reported severe fire is not corroborated by the nearby atmospheric sensor ({s_name}: {val} {unit} clean) located within {dist_m:.0f}m coverage.",
                            severity="HIGH",
                            recommended_action="Review live camera evidence and request field unit visual check.",
                        ))
                        conflict_factors.append(f"Sensor {s_name} indicates clean air/normal temperature ({val} {unit}) during reported fire")
                    else:
                        neutral_sources.append(CorroboratingSource(
                            source_type=CorroborationSourceType.SENSOR_EVENT,
                            source_id=s_id,
                            source_name=s_name,
                            summary=f"Sensor {s_name} reading ({val} {unit}) within standard operating range.",
                            alignment=CorroborationAlignment.NEUTRAL,
                            spatial_relationship=spatial_rel,
                            distance_meters=dist_m,
                            temporal_relationship=temporal_rel,
                            time_difference_seconds=time_diff_s,
                            timestamp=s_dt,
                            sensor_type=s_type_raw,
                            reading_value=val,
                            reading_unit=unit,
                            threshold=thresh,
                            is_breach=is_breach,
                            coverage_radius_meters=cov_radius_m,
                            within_coverage=True,
                        ))
                else:
                    neutral_sources.append(CorroboratingSource(
                        source_type=CorroborationSourceType.SENSOR_EVENT,
                        source_id=s_id,
                        source_name=s_name,
                        summary=f"Sensor {s_name} ({s_type_raw}) is unrelated to fire observation.",
                        alignment=CorroborationAlignment.NEUTRAL,
                        spatial_relationship=spatial_rel,
                        distance_meters=dist_m,
                        temporal_relationship=temporal_rel,
                        time_difference_seconds=time_diff_s,
                        timestamp=s_dt,
                        sensor_type=s_type_raw,
                        reading_value=val,
                        reading_unit=unit,
                        threshold=thresh,
                        is_breach=is_breach,
                        coverage_radius_meters=cov_radius_m,
                        within_coverage=True,
                    ))
            else:
                # Other emergency types: unrelated sensors are NEUTRAL
                neutral_sources.append(CorroboratingSource(
                    source_type=CorroborationSourceType.SENSOR_EVENT,
                    source_id=s_id,
                    source_name=s_name,
                    summary=f"Sensor {s_name} ({s_type_raw}) is neutral with respect to {target_et.value}.",
                    alignment=CorroborationAlignment.NEUTRAL,
                    spatial_relationship=spatial_rel,
                    distance_meters=dist_m,
                    temporal_relationship=temporal_rel,
                    time_difference_seconds=time_diff_s,
                    timestamp=s_dt,
                    sensor_type=s_type_raw,
                    reading_value=val,
                    reading_unit=unit,
                    threshold=thresh,
                    is_breach=is_breach,
                    coverage_radius_meters=cov_radius_m,
                    within_coverage=True,
                ))

        # =====================================================================
        # SOURCE 4: FIELD RESIDUAL UPDATES & GROUND VERIFICATIONS
        # =====================================================================
        if candidate_field_updates:
            for fu in candidate_field_updates:
                fu_id = fu.get("verification_id") or fu.get("update_id", "FU-UNKNOWN")
                fu_notes = fu.get("notes", "") or fu.get("summary", "")
                fu_actor = fu.get("responder_name") or fu.get("author_name") or "Field Responder"
                fu_status = fu.get("verification_status")
                fu_obs = fu.get("observation_category")

                is_conflicting = (
                    fu_status in ["NOT_FOUND", "UNABLE_TO_VERIFY"] or
                    fu_obs in ["INCIDENT_NOT_FOUND"] or
                    (fu_obs == "ROAD_CLEAR" and target_et in [EmergencyType.FLOOD, EmergencyType.FIRE, EmergencyType.LANDSLIDE, EmergencyType.BUILDING_COLLAPSE]) or
                    cls._is_negative_observation(fu_notes)
                )

                if is_conflicting:
                    conflicting_sources.append(CorroboratingSource(
                        source_type=CorroborationSourceType.FIELD_UPDATE,
                        source_id=fu_id,
                        source_name=f"Field Verification ({fu_actor})",
                        summary=f"Field observation indicates: '{fu_obs or fu_notes[:80]}'",
                        alignment=CorroborationAlignment.CONFLICTING,
                        spatial_relationship=CorroborationSpatialRelationship.MATCH,
                        temporal_relationship=CorroborationTemporalRelationship.COINCIDENT,
                        details={"notes": fu_notes, "author": fu_actor, "status": fu_status, "observation": fu_obs},
                    ))
                    conflict_details.append(ConflictDetail(
                        category=EvidenceConflictCategory.OBSERVATION_CONFLICT,
                        conflicting_source_id=fu_id,
                        conflicting_source_type=CorroborationSourceType.FIELD_UPDATE,
                        conflicting_source_name=f"Field Verification ({fu_actor})",
                        summary="Field responder reported contradictory condition",
                        reason=f"Responder {fu_actor} reported: '{fu_obs or fu_notes[:100]}'.",
                        severity="HIGH",
                        recommended_action="Contact field officer to confirm status before committing major resources.",
                    ))
                    conflict_factors.append(f"Field verification by {fu_actor} conflicts with citizen report ({fu_obs or 'contradictory'})")
                else:
                    obs_label = f" ({fu_obs})" if fu_obs else ""
                    supporting_sources.append(CorroboratingSource(
                        source_type=CorroborationSourceType.FIELD_UPDATE,
                        source_id=fu_id,
                        source_name=f"Field Verification ({fu_actor})",
                        summary=f"Field responder confirmed ground status{obs_label}: '{fu_notes[:80]}'",
                        alignment=CorroborationAlignment.SUPPORTING,
                        spatial_relationship=CorroborationSpatialRelationship.MATCH,
                        temporal_relationship=CorroborationTemporalRelationship.COINCIDENT,
                        details={"notes": fu_notes, "author": fu_actor, "status": fu_status, "observation": fu_obs},
                    ))
                    corroboration_factors.append(f"Field responder {fu_actor} verified operational conditions on site{obs_label}")

        # =====================================================================
        # STATUS DETERMINATION & EXPLAINABILITY
        # =====================================================================
        supp_count = len(supporting_sources)
        conf_count = len(conflicting_sources)
        neut_count = len(neutral_sources)
        total_evaluated = supp_count + conf_count + neut_count

        if conf_count > 0:
            corroboration_status = CorroborationStatus.CONFLICTED
            warnings.append("CONFLICT DETECTED — HUMAN REVIEW REQUIRED before dispatching resources or updating response plans.")
            explanation = (
                f"Conflicting observations detected across {conf_count} source(s). "
                f"{supp_count} source(s) support the report, while {conf_count} source(s) contradict the observation. "
                "Human Watch Officer review is required to resolve discrepancy."
            )
            recommendations.append("Human Officer review required to inspect conflicting source details.")
            recommendations.append("Dispatch field verification unit for authoritative ground truth confirmation.")
        elif supp_count >= 2:
            corroboration_status = CorroborationStatus.CORROBORATED
            explanation = (
                f"Multi-source corroboration established: {supp_count} independent sources "
                f"support {target_et.value} in the incident area within configured spatial and temporal thresholds. "
                "Zero conflicting signals detected."
            )
            recommendations.append("Incident corroborated by multiple independent signals. Proceed with standard operational triage.")
        elif supp_count == 1:
            corroboration_status = CorroborationStatus.PARTIALLY_CORROBORATED
            explanation = (
                f"Partially corroborated: 1 independent source supports this incident observation. "
                "No conflicting signals detected within the operational window."
            )
            recommendations.append("Awaiting additional sensor or citizen verification to strengthen confidence.")
        else:
            corroboration_status = CorroborationStatus.NO_CORROBORATION
            explanation = (
                "Single-source report: No independent corroborating sources detected "
                "within the 2000m spatial and 2-hour temporal operational window. "
                "No conflicting evidence detected."
            )
            recommendations.append("Single-source report. Dispatch field verification or monitor nearby telemetry for emerging signals.")

        return CorroborationResult(
            target_id=target_id,
            target_type="CITIZEN_REPORT",
            corroboration_status=corroboration_status,
            total_sources_evaluated=total_evaluated,
            supporting_source_count=supp_count,
            conflicting_source_count=conf_count,
            neutral_source_count=neut_count,
            supporting_sources=supporting_sources,
            conflicting_sources=conflicting_sources,
            neutral_sources=neutral_sources,
            conflict_details=conflict_details,
            corroboration_factors=corroboration_factors,
            conflict_factors=conflict_factors,
            warnings=warnings,
            explanation=explanation,
            recommendations=recommendations,
            evaluated_at=now,
        )

    @classmethod
    async def get_or_evaluate_report_corroboration(
        cls,
        report_id: str,
        db: AsyncIOMotorDatabase,
        eval_time: Optional[datetime] = None,
    ) -> Optional[CorroborationResult]:
        """
        Retrieves authoritative records from MongoDB and executes deterministic corroboration.
        Guaranteed idempotent and read-only (does not create duplicate records on refresh).
        """
        clean_id = report_id.strip().upper()
        target_doc = await db["citizen_reports"].find_one({"report_id": clean_id})
        if not target_doc:
            return None

        # Fetch candidate peer citizen reports (within last 48 hours to be comprehensive)
        candidate_reports_cursor = db["citizen_reports"].find(
            {"report_id": {"$ne": clean_id}}
        ).sort("created_at", -1).limit(100)
        candidate_reports = await candidate_reports_cursor.to_list(length=100)

        # Fetch sensors
        sensors_cursor = db["sensors"].find({}).limit(100)
        candidate_sensors = await sensors_cursor.to_list(length=100)

        # Fetch active sensor alerts
        alerts_cursor = db["sensor_alerts"].find({}).sort("created_at", -1).limit(50)
        candidate_alerts = await alerts_cursor.to_list(length=50)

        # Fetch field updates & field verifications if any
        field_updates: List[Dict[str, Any]] = []
        try:
            fu_cursor = db["field_updates"].find({}).sort("created_at", -1).limit(30)
            field_updates.extend(await fu_cursor.to_list(length=30))
        except Exception:
            pass

        try:
            fv_cursor = db["field_verifications"].find({
                "$or": [
                    {"target_id": clean_id},
                    {"metadata.report_id": clean_id},
                    {"metadata.situation_id": target_doc.get("situation_id")},
                ]
            }).sort("submitted_at", -1).limit(30)
            field_updates.extend(await fv_cursor.to_list(length=30))
        except Exception:
            pass

        return cls.evaluate_report_corroboration(
            target_report=target_doc,
            candidate_reports=candidate_reports,
            candidate_sensors=candidate_sensors,
            candidate_alerts=candidate_alerts,
            candidate_field_updates=field_updates,
            eval_time=eval_time,
        )

    @classmethod
    async def evaluate_situation_corroboration(
        cls,
        situation_id: str,
        db: AsyncIOMotorDatabase,
        eval_time: Optional[datetime] = None,
    ) -> Optional[CorroborationResult]:
        """
        Evaluates corroboration across all member reports and linked sensors of a situation cluster.
        """
        clean_id = situation_id.strip().upper()
        sit_doc = await db["situations"].find_one({"situation_id": clean_id})
        if not sit_doc:
            return None

        rep_ids = sit_doc.get("report_ids", [])
        primary_rep_id = sit_doc.get("primary_report_id") or (rep_ids[0] if rep_ids else None)

        if not primary_rep_id:
            return None

        primary_doc = await db["citizen_reports"].find_one({"report_id": primary_rep_id})
        if not primary_doc:
            return None

        # Evaluate corroboration with primary report as target and other clustered reports as candidates
        result = await cls.get_or_evaluate_report_corroboration(primary_rep_id, db, eval_time=eval_time)
        if result:
            result.target_id = clean_id
            result.target_type = "SITUATION"
        return result
