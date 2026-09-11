import logging
import math
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.enums import (
    UserRole,
    FieldVerificationStatus,
    FieldObservationCategory,
    LocationMatchState,
    TimelineEventType,
    MonitoringEventType,
    EventSourceType,
    EvidenceValidationStatus,
)
from app.models.citizen import LocationPayload, LiveEvidenceRecord
from app.models.field_verification import (
    FieldVerificationCreateRequest,
    FieldVerificationRecord,
    generate_verification_id,
)
from app.services.timeline import record_timeline_event, generate_event_id

logger = logging.getLogger("resilience.field_verification")

# Spatial thresholds
SPATIAL_MATCH_THRESHOLD_METERS = 500.0
SPATIAL_NEAR_MATCH_THRESHOLD_METERS = 2000.0


def calculate_haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two points on Earth in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2) + \
        math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
    return dt


class FieldVerificationService:
    """
    Authoritative service for Field Officer & Responder Ground-Truth Live Verification.
    Enforces RBAC, real GPS validation, explainable ground observations,
    and seamless integration with Multi-Source Corroboration & Dynamic Replanning.
    """

    @classmethod
    async def verify_ground_truth(
        cls,
        req: FieldVerificationCreateRequest,
        actor: Dict[str, Any],
        db: AsyncIOMotorDatabase,
    ) -> FieldVerificationRecord:
        """
        Record a genuine field verification submitted by an authorized responder.
        """
        actor_role_val = actor.get("role")
        actor_id = actor.get("id") or actor.get("user_id")
        actor_name = actor.get("full_name") or "Authorized Responder"

        # RBAC Check: Only EMERGENCY_OFFICER, VOLUNTEER, or ADMIN
        try:
            role_enum = UserRole(actor_role_val)
        except Exception:
            raise ValueError(f"Invalid actor role '{actor_role_val}'. Unauthorized.")

        if role_enum not in [UserRole.EMERGENCY_OFFICER, UserRole.VOLUNTEER, UserRole.ADMIN]:
            raise ValueError(f"Role '{role_enum.value}' is not authorized to submit field verifications.")

        target_id_clean = req.target_id.strip().upper()
        now = datetime.now(timezone.utc)
        observed_at = ensure_utc(req.observed_at) or now

        # Retrieve target incident / situation to compute ground truth spatial distance
        target_lat: Optional[float] = None
        target_lon: Optional[float] = None
        sit_id_ref: Optional[str] = None
        report_id_ref: Optional[str] = None

        if req.target_type == "SITUATION" or target_id_clean.startswith("SIT-"):
            sit_doc = await db["situations"].find_one({"situation_id": target_id_clean})
            if not sit_doc:
                raise ValueError(f"Situation '{target_id_clean}' not found.")
            sit_id_ref = target_id_clean
            c_loc = sit_doc.get("center_location") or {}
            target_lat = c_loc.get("latitude")
            target_lon = c_loc.get("longitude")
        else:
            rep_doc = await db["citizen_reports"].find_one({"report_id": target_id_clean})
            if not rep_doc:
                raise ValueError(f"Emergency report '{target_id_clean}' not found.")
            report_id_ref = target_id_clean
            sit_id_ref = rep_doc.get("situation_id")
            r_loc = rep_doc.get("location") or {}
            target_lat = r_loc.get("latitude")
            target_lon = r_loc.get("longitude")

        # Spatial Matching Evaluation
        distance_meters: Optional[float] = None
        match_state: LocationMatchState = LocationMatchState.UNAVAILABLE

        if req.location and req.location.latitude is not None and req.location.longitude is not None:
            r_lat = float(req.location.latitude)
            r_lon = float(req.location.longitude)
            if target_lat is not None and target_lon is not None:
                distance_meters = round(calculate_haversine_distance_meters(target_lat, target_lon, r_lat, r_lon), 2)
                if distance_meters <= SPATIAL_MATCH_THRESHOLD_METERS:
                    match_state = LocationMatchState.MATCH
                elif distance_meters <= SPATIAL_NEAR_MATCH_THRESHOLD_METERS:
                    match_state = LocationMatchState.NEAR_MATCH
                else:
                    match_state = LocationMatchState.MISMATCH
            else:
                match_state = LocationMatchState.UNAVAILABLE
        else:
            match_state = LocationMatchState.UNAVAILABLE

        # Process optional photo evidence
        evidence_record: Optional[LiveEvidenceRecord] = None
        if req.evidence and req.evidence.image_base64:
            from app.services.evidence_validation import EvidenceValidationService
            evidence_rec, _, _ = await EvidenceValidationService.process_live_evidence(
                evidence_payload=req.evidence,
                report_location=req.location,
                report_id=target_id_clean,
                db=db,
            )
            evidence_record = evidence_rec

        verification_id = generate_verification_id()
        while await db["field_verifications"].find_one({"verification_id": verification_id}):
            verification_id = generate_verification_id()

        verification_doc: Dict[str, Any] = {
            "verification_id": verification_id,
            "target_id": target_id_clean,
            "target_type": "SITUATION" if sit_id_ref == target_id_clean else "CITIZEN_REPORT",
            "responder_id": actor_id,
            "responder_name": actor_name,
            "responder_role": role_enum.value,
            "verification_status": req.verification_status.value,
            "observation_category": req.observation_category.value,
            "notes": req.notes or "",
            "location": req.location.model_dump() if req.location else None,
            "distance_from_target_meters": distance_meters,
            "location_match_state": match_state.value,
            "evidence": evidence_record.model_dump() if evidence_record else None,
            "task_id": req.task_id,
            "observed_at": observed_at,
            "submitted_at": now,
            "created_at": now,
            "metadata": {
                "situation_id": sit_id_ref,
                "report_id": report_id_ref,
            },
        }

        await db["field_verifications"].insert_one(verification_doc)

        # Timeline Event Logging
        evt_type = TimelineEventType.FIELD_CONDITION_CHANGED if req.verification_status == FieldVerificationStatus.CONDITION_CHANGED else TimelineEventType.FIELD_VERIFICATION_SUBMITTED
        summary_text = (
            f"Field Verification [{req.verification_status.value}] submitted by {actor_name} ({role_enum.value}): "
            f"{req.observation_category.value}. Distance to scene: "
            f"{f'{distance_meters:.1f}m' if distance_meters is not None else 'Unavailable'} ({match_state.value})."
        )

        await record_timeline_event(
            db=db,
            report_id=target_id_clean,
            event_type=evt_type,
            details=summary_text,
            actor_id=actor_id,
            actor_name=actor_name,
            actor_role=role_enum,
            metadata={
                "verification_id": verification_id,
                "observation_category": req.observation_category.value,
                "verification_status": req.verification_status.value,
                "distance_meters": distance_meters,
                "match_state": match_state.value,
                "situation_id": sit_id_ref,
            },
        )

        # Emit Live Monitoring Event for Dynamic Replanning evaluation if material obstacle / escalation
        critical_categories = [
            FieldObservationCategory.ROAD_BLOCKED,
            FieldObservationCategory.FIRE_SPREADING,
            FieldObservationCategory.WATER_LEVEL_CHANGED,
            FieldObservationCategory.SHELTER_INACCESSIBLE,
            FieldObservationCategory.SEVERITY_CHANGED,
        ]
        if req.observation_category in critical_categories or req.verification_status == FieldVerificationStatus.CONDITION_CHANGED:
            try:
                from app.services.monitoring.monitoring_service import MonitoringService
                await MonitoringService.record_change_event(
                    event_type=MonitoringEventType.FIELD_UPDATE_RECEIVED,
                    source_type=EventSourceType.FIELD_UPDATE,
                    source_id=verification_id,
                    previous_state={},
                    new_state={
                        "verification_id": verification_id,
                        "observation_category": req.observation_category.value,
                        "verification_status": req.verification_status.value,
                        "notes": req.notes,
                        "target_id": target_id_clean,
                    },
                    situation_id=sit_id_ref,
                    location=req.location.model_dump() if req.location else None,
                    actor={
                        "id": actor_id,
                        "full_name": actor_name,
                        "role": role_enum.value,
                    },
                    db=db,
                )
            except Exception as mon_err:
                logger.warning(f"Monitoring notice on field verification {verification_id}: {mon_err}")

        return FieldVerificationRecord(
            verification_id=verification_id,
            target_id=target_id_clean,
            target_type=verification_doc["target_type"],
            responder_id=actor_id,
            responder_name=actor_name,
            responder_role=role_enum,
            verification_status=req.verification_status,
            observation_category=req.observation_category,
            notes=req.notes or "",
            location=req.location,
            distance_from_target_meters=distance_meters,
            location_match_state=match_state,
            evidence=evidence_record,
            task_id=req.task_id,
            observed_at=observed_at,
            submitted_at=now,
            created_at=now,
            metadata=verification_doc["metadata"],
        )

    @classmethod
    async def list_verifications(
        cls,
        target_id: Optional[str] = None,
        situation_id: Optional[str] = None,
        responder_id: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> Tuple[List[FieldVerificationRecord], int]:
        if db is None:
            return [], 0

        query: Dict[str, Any] = {}
        if target_id:
            query["target_id"] = target_id.strip().upper()
        if situation_id:
            query["$or"] = [
                {"target_id": situation_id.strip().upper()},
                {"metadata.situation_id": situation_id.strip().upper()},
            ]
        if responder_id:
            query["responder_id"] = responder_id.strip()

        total = await db["field_verifications"].count_documents(query)
        skip = (page - 1) * limit

        cursor = db["field_verifications"].find(query).sort("submitted_at", -1).skip(skip).limit(limit)
        items: List[FieldVerificationRecord] = []

        async for doc in cursor:
            items.append(FieldVerificationRecord(
                verification_id=doc["verification_id"],
                target_id=doc["target_id"],
                target_type=doc.get("target_type", "CITIZEN_REPORT"),
                responder_id=doc["responder_id"],
                responder_name=doc.get("responder_name", "Responder"),
                responder_role=UserRole(doc.get("responder_role", UserRole.VOLUNTEER.value)),
                verification_status=FieldVerificationStatus(doc.get("verification_status", FieldVerificationStatus.FIELD_VERIFIED.value)),
                observation_category=FieldObservationCategory(doc.get("observation_category", FieldObservationCategory.INCIDENT_CONFIRMED.value)),
                notes=doc.get("notes", ""),
                location=LocationPayload(**doc["location"]) if doc.get("location") else None,
                distance_from_target_meters=doc.get("distance_from_target_meters"),
                location_match_state=LocationMatchState(doc.get("location_match_state", LocationMatchState.UNAVAILABLE.value)),
                evidence=LiveEvidenceRecord(**doc["evidence"]) if doc.get("evidence") else None,
                task_id=doc.get("task_id"),
                observed_at=ensure_utc(doc.get("observed_at")),
                submitted_at=ensure_utc(doc.get("submitted_at")),
                created_at=ensure_utc(doc.get("created_at")),
                metadata=doc.get("metadata", {}),
            ))

        return items, total
