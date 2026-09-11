import os
import math
import hashlib
import base64
import secrets
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.models.enums import EvidenceValidationStatus, ReportTrustState
from app.models.citizen import LiveEvidencePayload, LiveEvidenceRecord, LocationPayload

logger = logging.getLogger("resilience.evidence")

EVIDENCE_UPLOAD_DIR = os.path.join(settings.UPLOAD_DIR, "citizen_evidence")
os.makedirs(EVIDENCE_UPLOAD_DIR, exist_ok=True)


def generate_evidence_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"EVD-{suffix}"


def calculate_haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculates the great circle distance between two points on earth in meters using Haversine formula.
    """
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class EvidenceValidationService:
    """
    Authoritative Evidence Processing, Geo-Temporal Validation & Trust Assessment Engine.
    Evaluates live browser camera evidence against citizen report claims with zero fake data.
    """

    @staticmethod
    def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        return calculate_haversine_distance_meters(lat1, lon1, lat2, lon2)

    @classmethod
    async def process_live_evidence(
        cls,
        evidence_payload: Optional[LiveEvidencePayload],
        report_location: LocationPayload,
        report_id: str,
        db: AsyncIOMotorDatabase,
    ) -> Tuple[Optional[LiveEvidenceRecord], ReportTrustState, List[str]]:
        """
        Processes captured live evidence, stores the image binary, computes SHA-256 content hash,
        detects duplicate evidence across reports, performs geo-temporal spatial validation,
        and generates explainable trust signals.
        """
        server_received_at = datetime.now(timezone.utc)

        # Case 1: No evidence payload provided
        if not evidence_payload:
            return None, ReportTrustState.NORMAL, []

        # Case 2: Explicit Camera Unavailable / Permission Denied fallback
        if evidence_payload.status == EvidenceValidationStatus.UNAVAILABLE or (
            not evidence_payload.image_base64 and evidence_payload.error_reason
        ):
            evidence_id = generate_evidence_id()
            signals = ["CAMERA_UNAVAILABLE", "EVIDENCE_UNAVAILABLE"]
            record = LiveEvidenceRecord(
                evidence_id=evidence_id,
                report_id=report_id,
                evidence_type="LIVE_CAMERA_PHOTO",
                source="BROWSER_CAMERA",
                file_url=None,
                filename=None,
                content_hash=None,
                client_capture_timestamp=evidence_payload.client_capture_timestamp,
                server_received_timestamp=server_received_at,
                latitude=evidence_payload.latitude,
                longitude=evidence_payload.longitude,
                accuracy_meters=evidence_payload.accuracy_meters,
                distance_from_report_meters=None,
                capture_session_id=evidence_payload.capture_session_id,
                validation_status=EvidenceValidationStatus.UNAVAILABLE,
                trust_signals=signals,
                is_duplicate=False,
                error_reason=evidence_payload.error_reason or "Camera permission denied or camera unavailable on client device.",
            )
            return record, ReportTrustState.NORMAL, signals

        # Case 3: Live Image Captured
        if not evidence_payload.image_base64:
            return None, ReportTrustState.NORMAL, []

        evidence_id = generate_evidence_id()
        trust_signals: List[str] = []

        # 1. Decode base64 image data
        image_data = evidence_payload.image_base64
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]

        try:
            image_bytes = base64.b64decode(image_data)
        except Exception as dec_err:
            logger.warning(f"Failed to decode base64 evidence image for report {report_id}: {dec_err}")
            record = LiveEvidenceRecord(
                evidence_id=evidence_id,
                report_id=report_id,
                evidence_type="LIVE_CAMERA_PHOTO",
                source="BROWSER_CAMERA",
                file_url=None,
                filename=None,
                content_hash=None,
                client_capture_timestamp=evidence_payload.client_capture_timestamp,
                server_received_timestamp=server_received_at,
                validation_status=EvidenceValidationStatus.REVIEW_REQUIRED,
                trust_signals=["INVALID_IMAGE_PAYLOAD"],
                is_duplicate=False,
                error_reason="Could not decode base64 image payload.",
            )
            return record, ReportTrustState.REVIEW_REQUIRED, ["INVALID_IMAGE_PAYLOAD"]

        # 2. Cryptographic Content Hash (SHA-256)
        content_hash = hashlib.sha256(image_bytes).hexdigest()
        trust_signals.append("LIVE_CAMERA_CAPTURED")

        # 3. Duplicate Evidence Detection
        is_duplicate = False
        duplicate_of_id: Optional[str] = None
        existing_doc = await db["citizen_reports"].find_one({
            "evidence.content_hash": content_hash,
            "report_id": {"$ne": report_id}
        })
        if existing_doc and existing_doc.get("evidence"):
            is_duplicate = True
            duplicate_of_id = existing_doc["evidence"].get("evidence_id")
            trust_signals.append("DUPLICATE_EVIDENCE")

        # 4. Save image binary to disk
        filename = f"{evidence_id}.jpg"
        file_path = os.path.join(EVIDENCE_UPLOAD_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(image_bytes)
        file_url = f"/uploads/citizen_evidence/{filename}"

        # 5. Geolocation Validation (Evidence Coordinates vs Citizen Report Coordinates)
        distance_meters: Optional[float] = None
        ev_lat = evidence_payload.latitude
        ev_lon = evidence_payload.longitude
        rep_lat = report_location.latitude
        rep_lon = report_location.longitude

        has_evidence_coords = (
            ev_lat is not None
            and ev_lon is not None
            and -90.0 <= ev_lat <= 90.0
            and -180.0 <= ev_lon <= 180.0
            and not (ev_lat == 0.0 and ev_lon == 0.0)
        )

        if has_evidence_coords:
            trust_signals.append("LOCATION_AVAILABLE")
            distance_meters = round(calculate_haversine_distance_meters(ev_lat, ev_lon, rep_lat, rep_lon), 1)

            # Check tolerance
            if distance_meters <= 1000.0:
                trust_signals.append("LOCATION_MATCHED")
            elif distance_meters > 5000.0:
                trust_signals.append("SEVERE_LOCATION_MISMATCH")
            else:
                trust_signals.append("LOCATION_MISMATCH")

            # Check GPS Accuracy
            if evidence_payload.accuracy_meters is not None:
                if evidence_payload.accuracy_meters <= 50.0:
                    trust_signals.append("GPS_ACCURACY_GOOD")
                elif evidence_payload.accuracy_meters > 150.0:
                    trust_signals.append("POOR_ACCURACY")
        else:
            trust_signals.append("GPS_UNAVAILABLE")

        # 6. Temporal Freshness Validation
        client_ts = evidence_payload.client_capture_timestamp
        if client_ts:
            # Ensure timezone awareness
            if client_ts.tzinfo is None:
                client_ts = client_ts.replace(tzinfo=timezone.utc)

            time_delta_sec = (server_received_at - client_ts).total_seconds()
            if time_delta_sec < -120.0:
                # Client clock in the future
                trust_signals.append("TIME_INCONSISTENCY")
            elif time_delta_sec > 1800.0:
                # Evidence older than 30 minutes
                trust_signals.append("STALE_CAPTURE")
            elif time_delta_sec <= 300.0:
                trust_signals.append("FRESH_CAPTURE")

        # 7. Derive Evidence Validation Status & Overall Report Trust State
        validation_status = EvidenceValidationStatus.VALIDATED
        trust_state = ReportTrustState.NORMAL

        if is_duplicate or "SEVERE_LOCATION_MISMATCH" in trust_signals:
            validation_status = EvidenceValidationStatus.LOW_CONFIDENCE
            trust_state = ReportTrustState.LOW_CONFIDENCE
        elif (
            "LOCATION_MISMATCH" in trust_signals
            or "TIME_INCONSISTENCY" in trust_signals
            or "STALE_CAPTURE" in trust_signals
            or "POOR_ACCURACY" in trust_signals
        ):
            validation_status = EvidenceValidationStatus.REVIEW_REQUIRED
            trust_state = ReportTrustState.REVIEW_REQUIRED

        record = LiveEvidenceRecord(
            evidence_id=evidence_id,
            report_id=report_id,
            evidence_type="LIVE_CAMERA_PHOTO",
            source="BROWSER_CAMERA",
            file_url=file_url,
            filename=filename,
            content_hash=content_hash,
            client_capture_timestamp=client_ts,
            server_received_timestamp=server_received_at,
            latitude=ev_lat if has_evidence_coords else None,
            longitude=ev_lon if has_evidence_coords else None,
            accuracy_meters=evidence_payload.accuracy_meters,
            distance_from_report_meters=distance_meters,
            capture_session_id=evidence_payload.capture_session_id,
            validation_status=validation_status,
            trust_signals=trust_signals,
            is_duplicate=is_duplicate,
            duplicate_of_evidence_id=duplicate_of_id,
            error_reason=None,
        )

        return record, trust_state, trust_signals
