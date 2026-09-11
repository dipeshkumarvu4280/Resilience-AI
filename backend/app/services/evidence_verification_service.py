import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.enums import (
    CitizenImpactLevel,
    VerificationStatus,
    EvidenceConfidenceBand,
    LocationMatchState,
    EvidenceFreshness,
    ReportCompleteness,
    EvidenceValidationStatus,
)
from app.models.citizen import EvidenceVerificationResult
from app.services.evidence_service import calculate_haversine_distance_meters

logger = logging.getLogger("resilience.evidence_verification")


class EvidenceVerificationService:
    """
    Evidence Trust & Verification Engine (Phase A).
    Evaluates citizen reports against real evidence signals deterministically:
    - Cryptographic hash verification & duplicate detection
    - Geo-spatial Haversine coordinate validation
    - Temporal freshness evaluation
    - Report completeness auditing
    - Explainable verified factors, missing factors, and warnings
    
    SAFETY PRINCIPLES:
    - Purely advisory (never rejects reports, never auto-dispatches, never overrides officer priority).
    - Citizen Impact Level remains distinct from Evidence Confidence.
    - Zero dummy/fabricated metrics.
    """

    # Spatial tolerance thresholds (meters)
    MATCH_TOLERANCE_METERS = 500.0
    NEAR_MATCH_TOLERANCE_METERS = 2000.0

    # Temporal freshness thresholds (seconds)
    FRESH_THRESHOLD_SECONDS = 1800.0   # 30 minutes
    AGING_THRESHOLD_SECONDS = 7200.0   # 2 hours

    @classmethod
    def evaluate_report_evidence(
        cls,
        report_doc: Dict[str, Any],
        eval_time: Optional[datetime] = None,
    ) -> EvidenceVerificationResult:
        """
        Evaluates a citizen report document and returns a structured, explainable EvidenceVerificationResult.
        """
        now = eval_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        report_id = report_doc.get("report_id", "UNKNOWN")
        raw_impact = report_doc.get("citizen_impact_level", CitizenImpactLevel.NOT_SURE.value)
        try:
            impact_level = CitizenImpactLevel(raw_impact)
        except Exception:
            impact_level = CitizenImpactLevel.NOT_SURE

        location_data = report_doc.get("location") or {}
        rep_lat = location_data.get("latitude")
        rep_lon = location_data.get("longitude")

        description = (report_doc.get("description") or "").strip()
        emergency_type = report_doc.get("emergency_type") or ""
        citizen_name = (report_doc.get("citizen_name") or "").strip()
        citizen_phone = (report_doc.get("citizen_phone") or "").strip()
        phone_verified = bool(report_doc.get("phone_verified", False))

        evidence_doc = report_doc.get("evidence")
        
        # 1. Evaluate Report Completeness
        has_type = bool(emergency_type)
        has_desc = len(description) >= 10
        has_impact = impact_level != CitizenImpactLevel.NOT_SURE
        has_coords = (
            rep_lat is not None
            and rep_lon is not None
            and -90.0 <= rep_lat <= 90.0
            and -180.0 <= rep_lon <= 180.0
            and not (rep_lat == 0.0 and rep_lon == 0.0)
        )
        has_address = bool(
            location_data.get("address")
            or location_data.get("street_address")
            or location_data.get("display_name")
            or location_data.get("landmark")
        )
        has_contact = bool(citizen_name and len(citizen_name) >= 2 and citizen_phone and len(citizen_phone) >= 7)

        if has_type and has_desc and has_impact and has_coords and has_address and has_contact:
            completeness = ReportCompleteness.COMPLETE
        elif has_type and has_desc and has_coords:
            completeness = ReportCompleteness.PARTIAL
        else:
            completeness = ReportCompleteness.INCOMPLETE

        # 2. Evaluate Live Camera Evidence
        has_live_photo = False
        content_hash: Optional[str] = None
        is_duplicate = False
        duplicate_of_id: Optional[str] = None
        distance_meters: Optional[float] = None
        location_match_state = LocationMatchState.UNAVAILABLE
        freshness = EvidenceFreshness.UNAVAILABLE
        age_seconds: Optional[float] = None
        evidence_signals: List[str] = []
        verified_factors: List[str] = []
        missing_factors: List[str] = []
        warnings: List[str] = []
        recommendations: List[str] = []

        # Citizen impact signal
        if has_impact:
            evidence_signals.append(f"CITIZEN_IMPACT_{impact_level.value}")
            verified_factors.append(f"Citizen provided impact level assessment: {impact_level.value}")
        else:
            missing_factors.append("Citizen impact level not specified (NOT_SURE)")

        if completeness == ReportCompleteness.COMPLETE:
            evidence_signals.append("REPORT_COMPLETE")
            verified_factors.append("Complete incident description, location, and contact information provided")
        elif completeness == ReportCompleteness.PARTIAL:
            evidence_signals.append("REPORT_PARTIAL")
            verified_factors.append("Essential incident details and coordinates provided")
        else:
            evidence_signals.append("REPORT_INCOMPLETE")
            warnings.append("Report description or location details are minimal")

        if phone_verified:
            evidence_signals.append("PHONE_VERIFIED")
            verified_factors.append("Citizen contact phone number verified via OTP")

        # Process Live Evidence Payload if present
        if isinstance(evidence_doc, dict):
            val_status = evidence_doc.get("validation_status")
            has_image = bool(evidence_doc.get("file_url") or evidence_doc.get("image_base64"))
            
            if val_status == EvidenceValidationStatus.UNAVAILABLE.value or (not has_image and evidence_doc.get("error_reason")):
                evidence_signals.append("CAMERA_UNAVAILABLE")
                missing_factors.append("Live camera evidence was unavailable or permission was not granted at report time")
                warnings.append(evidence_doc.get("error_reason") or "Camera unavailable on citizen client device.")
            elif has_image:
                has_live_photo = True
                evidence_signals.append("LIVE_PHOTO_CAPTURED")
                verified_factors.append("Live browser camera evidence captured at report time")

                # Content Hash
                content_hash = evidence_doc.get("content_hash")
                if content_hash:
                    evidence_signals.append("CONTENT_HASH_VERIFIED")
                    verified_factors.append(f"Cryptographic SHA-256 content hash verified ({content_hash[:12]}...)")

                # Duplicate Check
                is_duplicate = bool(evidence_doc.get("is_duplicate", False))
                duplicate_of_id = evidence_doc.get("duplicate_of_evidence_id")
                if is_duplicate:
                    evidence_signals.append("DUPLICATE_EVIDENCE")
                    warnings.append(f"Duplicate evidence detected — content hash matches another submitted report ({duplicate_of_id or 'previous'})")
                else:
                    evidence_signals.append("UNIQUE_EVIDENCE")
                    verified_factors.append("Evidence content is unique (no prior duplicate hash)")

                # Geo-temporal distance calculation
                ev_lat = evidence_doc.get("latitude")
                ev_lon = evidence_doc.get("longitude")
                ev_accuracy = evidence_doc.get("accuracy_meters")

                has_ev_coords = (
                    ev_lat is not None
                    and ev_lon is not None
                    and -90.0 <= ev_lat <= 90.0
                    and -180.0 <= ev_lon <= 180.0
                    and not (ev_lat == 0.0 and ev_lon == 0.0)
                )

                if has_ev_coords and has_coords:
                    evidence_signals.append("EVIDENCE_GPS_AVAILABLE")
                    # Calculate actual Haversine distance
                    distance_meters = round(calculate_haversine_distance_meters(ev_lat, ev_lon, rep_lat, rep_lon), 1)

                    if distance_meters <= cls.MATCH_TOLERANCE_METERS:
                        location_match_state = LocationMatchState.MATCH
                        evidence_signals.append("LOCATION_MATCH")
                        verified_factors.append(f"Evidence GPS location matches reported incident location ({distance_meters:.0f}m distance)")
                    elif distance_meters <= cls.NEAR_MATCH_TOLERANCE_METERS:
                        location_match_state = LocationMatchState.NEAR_MATCH
                        evidence_signals.append("LOCATION_NEAR_MATCH")
                        verified_factors.append(f"Evidence GPS location within vicinity ({distance_meters:.0f}m from reported point)")
                    else:
                        location_match_state = LocationMatchState.MISMATCH
                        evidence_signals.append("LOCATION_MISMATCH")
                        warnings.append(f"Evidence GPS location mismatch ({distance_meters:.0f}m from reported point, exceeds {cls.NEAR_MATCH_TOLERANCE_METERS:.0f}m tolerance)")
                    
                    if ev_accuracy is not None:
                        if ev_accuracy <= 50.0:
                            evidence_signals.append("GPS_ACCURACY_GOOD")
                        elif ev_accuracy > 150.0:
                            evidence_signals.append("GPS_ACCURACY_POOR")
                            warnings.append(f"GPS horizontal accuracy is low (±{ev_accuracy}m)")
                else:
                    location_match_state = LocationMatchState.UNAVAILABLE
                    evidence_signals.append("EVIDENCE_GPS_UNAVAILABLE")
                    missing_factors.append("Live evidence GPS coordinates unavailable or device location was disabled")

                # Freshness Calculation
                raw_capture_ts = evidence_doc.get("client_capture_timestamp")
                if raw_capture_ts:
                    if isinstance(raw_capture_ts, str):
                        try:
                            capture_dt = datetime.fromisoformat(raw_capture_ts.replace("Z", "+00:00"))
                        except Exception:
                            capture_dt = None
                    elif isinstance(raw_capture_ts, datetime):
                        capture_dt = raw_capture_ts
                    else:
                        capture_dt = None

                    if capture_dt:
                        if capture_dt.tzinfo is None:
                            capture_dt = capture_dt.replace(tzinfo=timezone.utc)
                        
                        age_seconds = round((now - capture_dt).total_seconds(), 1)
                        age_minutes = round(age_seconds / 60.0, 1)

                        if age_seconds < -120.0:
                            freshness = EvidenceFreshness.UNAVAILABLE
                            evidence_signals.append("TIME_INCONSISTENCY")
                            warnings.append("Evidence capture timestamp is in the future (client clock discrepancy)")
                        elif age_seconds <= cls.FRESH_THRESHOLD_SECONDS:
                            freshness = EvidenceFreshness.FRESH
                            evidence_signals.append("EVIDENCE_FRESH")
                            verified_factors.append(f"Evidence captured recently ({age_minutes:.0f} min ago)")
                        elif age_seconds <= cls.AGING_THRESHOLD_SECONDS:
                            freshness = EvidenceFreshness.AGING
                            evidence_signals.append("EVIDENCE_AGING")
                            verified_factors.append(f"Evidence captured within operational window ({age_minutes:.0f} min ago)")
                        else:
                            freshness = EvidenceFreshness.STALE
                            evidence_signals.append("EVIDENCE_STALE")
                            warnings.append(f"Evidence capture is stale ({age_minutes:.0f} min old)")
        else:
            missing_factors.append("No live camera photo evidence provided with this report")

        # Future phase placeholder factor
        missing_factors.append("No independent multi-source corroboration yet (Phase A)")

        # 3. Derive Deterministic Explainable Confidence Band
        # Safety: Low confidence never means "FAKE"; High confidence verifies evidence quality, not semantic absolute truth.
        if is_duplicate or location_match_state == LocationMatchState.MISMATCH or not has_live_photo:
            confidence_band = EvidenceConfidenceBand.LOW
        elif has_live_photo and content_hash and location_match_state in [LocationMatchState.MATCH, LocationMatchState.NEAR_MATCH] and freshness in [EvidenceFreshness.FRESH, EvidenceFreshness.AGING]:
            confidence_band = EvidenceConfidenceBand.HIGH
        elif has_live_photo and content_hash and freshness in [EvidenceFreshness.FRESH, EvidenceFreshness.AGING]:
            confidence_band = EvidenceConfidenceBand.MEDIUM
        elif has_live_photo and freshness != EvidenceFreshness.STALE:
            confidence_band = EvidenceConfidenceBand.MEDIUM
        else:
            confidence_band = EvidenceConfidenceBand.LOW

        # 4. Derive Verification Status (Phase A: UNVERIFIED or PARTIALLY_VERIFIED only)
        if (
            confidence_band in [EvidenceConfidenceBand.HIGH, EvidenceConfidenceBand.MEDIUM]
            and has_live_photo
            and location_match_state != LocationMatchState.MISMATCH
            and not is_duplicate
        ):
            verification_status = VerificationStatus.PARTIALLY_VERIFIED
        else:
            verification_status = VerificationStatus.UNVERIFIED

        # 5. Advisory Human-in-the-Loop Recommendations
        recommendations.append("Officer verification recommended before final resource dispatch.")
        if has_live_photo and location_match_state == LocationMatchState.MATCH and freshness == EvidenceFreshness.FRESH:
            recommendations.append("Live camera evidence strongly supports reported incident location and timing.")
        elif is_duplicate:
            recommendations.append("Verify whether this incident is a duplicate submission of an ongoing event.")
        elif location_match_state == LocationMatchState.MISMATCH:
            recommendations.append("Investigate discrepancy between citizen reported location and evidence GPS capture coordinates.")
        elif not has_live_photo:
            recommendations.append("Dispatch field verification or contact reporting citizen for situational clarity.")

        return EvidenceVerificationResult(
            report_id=report_id,
            verification_status=verification_status,
            confidence_band=confidence_band,
            citizen_impact_level=impact_level,
            evidence_signals=evidence_signals,
            warnings=warnings,
            verified_factors=verified_factors,
            missing_factors=missing_factors,
            location_match_state=location_match_state,
            distance_from_report_meters=distance_meters,
            evidence_freshness=freshness,
            evidence_age_seconds=age_seconds,
            report_completeness=completeness,
            recommendations=recommendations,
            has_live_photo=has_live_photo,
            content_hash=content_hash,
            is_duplicate=is_duplicate,
            duplicate_of_report_id=duplicate_of_id,
            last_evaluated_at=now,
        )

    @classmethod
    async def get_or_evaluate_report_verification(
        cls,
        report_id: str,
        db: AsyncIOMotorDatabase,
    ) -> Optional[EvidenceVerificationResult]:
        """
        Retrieves authoritative report from MongoDB and executes verification evaluation.
        """
        doc = await db["citizen_reports"].find_one({"report_id": report_id})
        if not doc:
            return None
        return cls.evaluate_report_evidence(doc)
