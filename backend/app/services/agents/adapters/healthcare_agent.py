import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from app.models.enums import (
    AgentName,
    AgentRunStatus,
    HealthcareConflictType,
    ResourceType,
    SeverityLevel,
)
from app.models.agent import (
    AgentContext,
    AgentResult,
    RecommendedHealthcareFacility,
    HealthcareCoordinationSummary,
)
from app.services.agents.base import BaseAgent
from app.services.resource_matching import haversine_distance_km

logger = logging.getLogger("resilience.agents.healthcare")


class HealthcareCoordinationAgent(BaseAgent):
    """
    Healthcare & Medical Coordination Agent.
    Evaluates situation casualty indicators, trauma severity, and emergency medical requirements.
    Deterministically matches and ranks genuine hospital and healthcare facilities based on
    proximity, available bed capacity, ICU availability, oxygen readiness, and trauma capability.
    Operates strictly in an ADVISORY capacity without mutating hospital records autonomously.
    """

    @property
    def name(self) -> AgentName:
        return AgentName.HEALTHCARE_AGENT

    @property
    def purpose(self) -> str:
        return (
            "Evaluates emergency casualty demands, ICU readiness, oxygen availability, "
            "and hospital capacities to recommend optimal patient distribution."
        )

    @property
    def dependencies(self) -> List[AgentName]:
        return [
            AgentName.PRIORITY_AGENT,
            AgentName.NEEDS_AGENT,
            AgentName.RESOURCE_COORDINATION_AGENT,
            AgentName.CONFLICT_RESOLUTION_AGENT,
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["situation_id"]

    async def execute(self, context: AgentContext) -> AgentResult:
        run_id = f"RUN-HLT-{uuid.uuid4().hex[:8].upper()}"
        evidence: List[str] = []
        warnings: List[str] = []
        constraints: List[str] = [
            "Advisory only: Human Emergency Officer approval required before formal hospital routing.",
            "Zero mutation: Medical facility capacities are never altered automatically.",
        ]

        try:
            emergency_type = context.emergency_type or "Other"
            effective_priority = context.officer_severity_override or context.parameters.get("effective_priority") or SeverityLevel.MEDIUM
            effective_priority_str = str(effective_priority.value if hasattr(effective_priority, "value") else effective_priority).upper()

            medical_need_item = next(
                (
                    n for n in context.existing_needs
                    if str(n.get("resource_type", "")).upper() in ["MEDICINE", "FIRST AID", "MEDICAL EQUIPMENT", "HEALTHCARE", "AMBULANCE"]
                ),
                None,
            )

            is_medical_disaster = emergency_type in [
                "Medical Emergency",
                "Building Collapse",
                "Road Accident",
                "Fire",
                "Landslide",
                "Cyclone / Storm",
                "Flood",
                "Missing / Trapped Person",
            ]

            is_high_priority = effective_priority_str in ["HIGH", "CRITICAL"]

            # 1. Determine if healthcare coordination is required
            medical_required = bool(
                is_medical_disaster
                or is_high_priority
                or medical_need_item
                or (context.parameters.get("estimated_casualties", 0) > 0)
                or (context.parameters.get("casualty_count", 0) > 0)
                or (context.parameters.get("injured_count", 0) > 0)
            )

            if not medical_required:
                summary = HealthcareCoordinationSummary(
                    medical_required=False,
                    requirement_reason=HealthcareConflictType.MEDICAL_NOT_REQUIRED.value,
                    estimated_casualties=0,
                    casualty_confidence=1.0,
                    facilities_evaluated=0,
                    facilities_recommended=[],
                    total_beds_available=0.0,
                    total_patients_covered=0.0,
                    total_shortfall=0.0,
                    conflicts=[HealthcareConflictType.MEDICAL_NOT_REQUIRED.value],
                    officer_attention_required=False,
                    explanation=(
                        f"Healthcare coordination not required for situation {context.situation_id} "
                        f"({emergency_type} with priority {effective_priority_str}). No casualty indicators detected."
                    ),
                    confidence=1.0,
                    generated_at=datetime.now(timezone.utc),
                    agent_version="1.0.0",
                )
                return AgentResult(
                    agent_name=self.name,
                    run_id=run_id,
                    status=AgentRunStatus.COMPLETED,
                    recommendation="No emergency healthcare facility activation required for this incident.",
                    structured_output=summary.model_dump(),
                    confidence=1.0,
                    evidence=["Zero casualty indicators or emergency medical needs identified for current incident."],
                    warnings=[],
                    constraints=constraints,
                    generated_at=datetime.now(timezone.utc),
                )

            # 2. Extract and evaluate estimated casualties / patients
            estimated_casualties: Optional[int] = None
            param_cas = (
                context.parameters.get("estimated_casualties")
                or context.parameters.get("casualty_count")
                or context.parameters.get("injured_count")
            )
            if param_cas is not None and int(param_cas) > 0:
                estimated_casualties = int(param_cas)
            elif medical_need_item and float(medical_need_item.get("requested_quantity", 0)) > 0:
                estimated_casualties = int(float(medical_need_item.get("requested_quantity", 0)))
            elif context.parameters.get("situation_casualties") is not None and int(context.parameters.get("situation_casualties")) > 0:
                estimated_casualties = int(context.parameters.get("situation_casualties"))

            conflicts: List[str] = []
            officer_attention_required = False

            if estimated_casualties is None or estimated_casualties <= 0:
                conflicts.append(HealthcareConflictType.CASUALTY_DATA_UNAVAILABLE.value)
                officer_attention_required = True
                warnings.append("Casualty and injury count is unassessed or unavailable. Flagged for officer review.")
                evidence.append("Casualty data missing from situation assessment; hospital bed assignment paused.")

            # 3. Load genuine facility records
            facility_records: List[Dict[str, Any]] = context.parameters.get("available_facilities") or []
            if not facility_records:
                # Reuse available_resources from context or MongoDB
                for r in context.available_resources:
                    rtype = str(r.get("resource_type", "")).upper()
                    cat = str(r.get("category", "")).upper()
                    name = str(r.get("name", "")).upper()
                    if rtype in ["HEALTHCARE", "MEDICINE", "MEDICAL EQUIPMENT"] or cat in ["HEALTHCARE", "HOSPITAL", "MEDICAL"] or "HOSPITAL" in name or "CLINIC" in name:
                        facility_records.append(r)

            evaluated_count = len(facility_records)
            sit_lat = context.center_latitude
            sit_lon = context.center_longitude

            eligible_facilities: List[Dict[str, Any]] = []

            for f in facility_records:
                facility_id = f.get("facility_id") or f.get("resource_id") or str(f.get("_id", "UNKNOWN"))
                name = f.get("facility_name") or f.get("name", "Emergency Medical Center")
                
                # Extract capabilities dict
                caps = f.get("capabilities", {})
                if not isinstance(caps, dict):
                    caps = {}

                total_beds = float(f.get("total_beds", f.get("quantity_total", 0.0)))
                occupied_beds = float(f.get("occupied_beds", f.get("current_occupancy", 0.0)))
                if "available_beds" in f:
                    avail_beds = float(f["available_beds"])
                elif "quantity_available" in f:
                    avail_beds = float(f["quantity_available"])
                else:
                    avail_beds = max(0.0, total_beds - occupied_beds)

                status = str(f.get("status", "ACTIVE")).upper()
                condition = str(f.get("condition", "EXCELLENT")).upper()

                # ICU availability
                if "available_icu_beds" in f:
                    icu_avail = int(f["available_icu_beds"])
                elif "total_icu_beds" in f and "occupied_icu_beds" in f:
                    icu_avail = max(0, int(f["total_icu_beds"]) - int(f["occupied_icu_beds"]))
                elif "icu_available" in f:
                    icu_avail = int(f["icu_available"])
                elif "icu_beds" in f:
                    icu_avail = int(f["icu_beds"])
                else:
                    icu_avail = 2 if total_beds >= 50 else 0

                # Oxygen availability
                oxygen_avail = bool(
                    caps.get("oxygen_support", f.get("oxygen_available", f.get("oxygen_available_capacity", 0) > 0 or total_beds > 0))
                )

                # Trauma & emergency capability
                trauma_cap = bool(
                    caps.get("trauma_care", f.get("trauma_capable", total_beds >= 30))
                )
                emergency_cap = bool(
                    caps.get("emergency_care", f.get("emergency_capable", status in ["ACTIVE", "AVAILABLE", "OPERATIONAL"]))
                )

                # Calculate remaining beds
                remaining_beds = max(0.0, avail_beds)

                # Check data consistency
                if total_beds < 0 or avail_beds < 0 or (occupied_beds > total_beds and total_beds > 0):
                    conflicts.append(HealthcareConflictType.FACILITY_DATA_CONFLICT.value)
                    warnings.append(f"Facility {name} ({facility_id}) has inconsistent bed capacity data: Total={total_beds}, Avail={avail_beds}, Occupied={occupied_beds}.")
                    continue

                # Check if facility is full
                if remaining_beds <= 0:
                    conflicts.append(HealthcareConflictType.FACILITY_FULL.value)
                    evidence.append(f"Facility {name} ({facility_id}) is at maximum capacity (0 beds available).")
                    continue

                # Check status availability
                if status in ["UNAVAILABLE", "CLOSED", "OFFLINE", "MAINTENANCE"] or status not in ["AVAILABLE", "ACTIVE", "READY", "STANDBY"]:
                    conflicts.append(HealthcareConflictType.FACILITY_UNAVAILABLE.value)
                    evidence.append(f"Facility {name} ({facility_id}) excluded because status is {status}.")
                    continue

                if condition in ["POOR", "UNUSABLE", "DAMAGED"]:
                    conflicts.append(HealthcareConflictType.FACILITY_UNAVAILABLE.value)
                    evidence.append(f"Facility {name} ({facility_id}) excluded because facility condition is {condition}.")
                    continue

                # Distance calculation
                loc = f.get("location") or {}
                f_lat = loc.get("latitude")
                f_lon = loc.get("longitude")
                f_address = loc.get("address") or loc.get("street_address") or loc.get("city") or "Designated Hospital Facility"

                dist_km = 0.0
                if sit_lat is not None and sit_lon is not None and f_lat is not None and f_lon is not None:
                    try:
                        dist_km = haversine_distance_km(float(sit_lat), float(sit_lon), float(f_lat), float(f_lon))
                    except Exception as dist_err:
                        logger.warning(f"Error computing distance for facility {facility_id}: {dist_err}")
                        dist_km = 99.0

                # Deterministic Ranking Score (0.0 - 100.0)
                # 1. Proximity score (0-40 pts): 40 pts at 0km, decays with distance
                dist_score = max(0.0, round(40.0 - (dist_km * 1.5), 2))

                # 2. Available bed score (0-30 pts)
                cap_score = min(30.0, round((remaining_beds / (total_beds if total_beds > 0 else 1.0)) * 30.0, 2))

                # 3. Critical capabilities score (0-30 pts)
                capability_score = 0.0
                if icu_avail > 0:
                    capability_score += 15.0
                else:
                    conflicts.append(HealthcareConflictType.ICU_UNAVAILABLE.value)

                if oxygen_avail:
                    capability_score += 10.0
                else:
                    conflicts.append(HealthcareConflictType.OXYGEN_UNAVAILABLE.value)

                if trauma_cap:
                    capability_score += 5.0
                else:
                    conflicts.append(HealthcareConflictType.TRAUMA_INCAPABLE.value)

                total_score = round(dist_score + cap_score + capability_score, 1)

                eligible_facilities.append({
                    "facility_id": facility_id,
                    "facility_name": name,
                    "distance_km": dist_km,
                    "total_beds": total_beds,
                    "available_beds": remaining_beds,
                    "icu_available": icu_avail,
                    "oxygen_available": oxygen_avail,
                    "trauma_capable": trauma_cap,
                    "emergency_capable": emergency_cap,
                    "suitability_score": total_score,
                    "ranking_factors": {
                        "proximity_score": dist_score,
                        "capacity_score": cap_score,
                        "capability_score": capability_score,
                    },
                    "address": f_address,
                    "latitude": f_lat,
                    "longitude": f_lon,
                    "status": status,
                })

            # Sort eligible facilities by suitability score descending, then distance ascending
            eligible_facilities.sort(key=lambda x: (-x["suitability_score"], x["distance_km"]))

            # 4. Multi-facility allocation
            recommended_facilities: List[RecommendedHealthcareFacility] = []
            total_beds_avail = sum(f["available_beds"] for f in eligible_facilities)
            total_covered = 0.0
            target_cas = estimated_casualties if (estimated_casualties and estimated_casualties > 0) else 0

            if target_cas > 0 and eligible_facilities:
                remaining_needed = float(target_cas)
                for fac in eligible_facilities:
                    if remaining_needed <= 0:
                        break
                    alloc = min(remaining_needed, fac["available_beds"])
                    if alloc > 0:
                        cov_pct = round((alloc / float(target_cas)) * 100.0, 1)
                        rec_reason = (
                            f"Ranked #{len(recommended_facilities) + 1} with score {fac['suitability_score']}/100. "
                            f"Located {fac['distance_km']} km away with {int(fac['available_beds'])} available beds "
                            f"(ICU={fac['icu_available']}, Oxygen={'Yes' if fac['oxygen_available'] else 'No'})."
                        )
                        recommended_facilities.append(
                            RecommendedHealthcareFacility(
                                facility_id=fac["facility_id"],
                                facility_name=fac["facility_name"],
                                facility_type="Hospital",
                                distance_km=fac["distance_km"],
                                total_beds=fac["total_beds"],
                                available_beds=fac["available_beds"],
                                allocated_patients=alloc,
                                coverage_percentage=cov_pct,
                                icu_available=fac["icu_available"],
                                oxygen_available=fac["oxygen_available"],
                                trauma_capable=fac["trauma_capable"],
                                emergency_capable=fac["emergency_capable"],
                                suitability_score=fac["suitability_score"],
                                ranking_factors=fac["ranking_factors"],
                                recommendation_reason=rec_reason,
                                location_address=fac["address"],
                                latitude=fac["latitude"],
                                longitude=fac["longitude"],
                                status=fac["status"],
                            )
                        )
                        remaining_needed -= alloc
                        total_covered += alloc

                total_shortfall = max(0.0, float(target_cas) - total_covered)

                if total_shortfall > 0:
                    conflicts.append(HealthcareConflictType.HEALTHCARE_CAPACITY_SHORTAGE.value)
                    officer_attention_required = True
                    warnings.append(
                        f"Medical bed shortage: {int(total_shortfall)} of {target_cas} patients cannot be accommodated in regional facilities."
                    )
                    evidence.append(
                        f"Hospital capacity shortfall of {int(total_shortfall)} patients requires field triage unit activation."
                    )

                if len(recommended_facilities) > 1:
                    evidence.append(
                        f"Multi-facility distribution applied across {len(recommended_facilities)} hospitals for {int(total_covered)} patients."
                    )
            else:
                total_shortfall = 0.0

            if len(eligible_facilities) == 0 and target_cas > 0:
                conflicts.append(HealthcareConflictType.NO_FEASIBLE_FACILITY.value)
                officer_attention_required = True
                warnings.append("Zero eligible emergency healthcare facilities available within response radius.")

            unique_conflicts = list(dict.fromkeys(conflicts))

            explanation = (
                f"Evaluated {evaluated_count} medical facility record(s) for situation {context.situation_id}. "
                f"Recommended {len(recommended_facilities)} hospital(s) accommodating {int(total_covered)} / {target_cas if target_cas else 'N/A'} "
                f"patients with {int(total_shortfall)} unaccommodated bed shortfall."
            )

            summary = HealthcareCoordinationSummary(
                medical_required=True,
                requirement_reason="EMERGENCY_MEDICAL_ASSESSMENT_ACTIVE",
                estimated_casualties=estimated_casualties,
                casualty_confidence=1.0 if estimated_casualties else 0.0,
                facilities_evaluated=evaluated_count,
                facilities_recommended=recommended_facilities,
                total_beds_available=total_beds_avail,
                total_patients_covered=total_covered,
                total_shortfall=total_shortfall,
                conflicts=unique_conflicts,
                officer_attention_required=officer_attention_required,
                explanation=explanation,
                confidence=0.95 if target_cas > 0 and total_shortfall == 0 else 0.85,
                generated_at=datetime.now(timezone.utc),
                agent_version="1.0.0",
            )

            rec_text = (
                f"Recommend routing {int(total_covered)} patients across {len(recommended_facilities)} medical facility(ies)."
                if recommended_facilities
                else "No hospital allocation recommended due to unavailable bed capacity or zero assessed casualties."
            )

            return AgentResult(
                agent_name=self.name,
                run_id=run_id,
                status=AgentRunStatus.COMPLETED,
                recommendation=rec_text,
                structured_output=summary.model_dump(),
                confidence=summary.confidence,
                evidence=evidence,
                warnings=warnings,
                constraints=constraints,
                generated_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.exception(f"Unhandled exception in HealthcareCoordinationAgent: {e}")
            summary = HealthcareCoordinationSummary(
                medical_required=True,
                requirement_reason="EXECUTION_ERROR_FALLBACK",
                estimated_casualties=0,
                casualty_confidence=0.0,
                facilities_evaluated=0,
                facilities_recommended=[],
                total_beds_available=0.0,
                total_patients_covered=0.0,
                total_shortfall=0.0,
                conflicts=[HealthcareConflictType.NO_FEASIBLE_FACILITY.value],
                officer_attention_required=True,
                explanation=f"Healthcare coordination encountered an unexpected error: {str(e)}",
                confidence=0.0,
                generated_at=datetime.now(timezone.utc),
                agent_version="1.0.0",
            )
            return AgentResult(
                agent_name=self.name,
                run_id=run_id,
                status=AgentRunStatus.FALLBACK,
                recommendation="Healthcare coordination evaluation paused due to internal error.",
                structured_output=summary.model_dump(),
                confidence=0.0,
                evidence=[],
                warnings=[f"Agent execution failed with exception: {str(e)}"],
                constraints=constraints,
                generated_at=datetime.now(timezone.utc),
            )
