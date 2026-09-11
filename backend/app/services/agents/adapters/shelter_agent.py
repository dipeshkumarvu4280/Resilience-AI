import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.models.enums import (
    AgentName,
    AgentRunStatus,
    SeverityLevel,
    NeedUrgency,
    ResourceType,
    ResourceStatus,
    ResourceCondition,
    ShelterConflictType,
)
from app.models.agent import (
    AgentContext,
    AgentResult,
    RecommendedShelter,
    ShelterCoordinationSummary,
)
from app.services.agents.base import BaseAgent
from app.services.resource_matching import haversine_distance_km

logger = logging.getLogger("resilience.agents.shelter_agent")

DISPLACEMENT_EMERGENCY_TYPES = {
    "Flood",
    "Cyclone / Storm",
    "Landslide",
    "Building Collapse",
    "Fire",
}


class ShelterCoordinationAgent(BaseAgent):
    """
    Shelter Coordination Agent Adapter.
    Evaluates disaster displacement risk, affected population requirements,
    and genuine shelter capacity in MongoDB.
    Computes explainable proximity and suitability rankings, handles multi-shelter
    allocations, detects operational conflicts, and produces advisory recommendations
    for Emergency Officer review without mutating inventory or occupancy.
    """

    @property
    def name(self) -> AgentName:
        return AgentName.SHELTER_AGENT

    @property
    def purpose(self) -> str:
        return (
            "Evaluates emergency shelter requirements, real facility capacity, "
            "distance, suitability, and multi-shelter distribution for affected populations."
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
        run_id = f"RUN-SHL-{uuid.uuid4().hex[:8].upper()}"
        warnings: List[str] = []
        evidence: List[str] = []
        constraints: List[str] = [
            "Shelter recommendations are strictly advisory and do not automatically mutate shelter capacity or occupancy.",
            "Authorized Emergency Officer must review and approve shelter coordination before field deployment.",
        ]

        try:
            # 1. Determine whether shelter coordination is required
            raw_needs = context.parameters.get("assessed_needs") or context.existing_needs or []
            emergency_type = context.emergency_type
            effective_priority_str = context.parameters.get("effective_priority") or (
                context.officer_severity_override.value if context.officer_severity_override else "MEDIUM"
            )

            # Check for explicit shelter need
            shelter_need_item = None
            for need in raw_needs:
                r_type = need.get("resource_type")
                if r_type in [ResourceType.SHELTER, ResourceType.SHELTER.value, "Shelter"]:
                    shelter_need_item = need
                    break

            # Determine displacement indicator
            has_displacement_risk = (
                emergency_type in DISPLACEMENT_EMERGENCY_TYPES
                or effective_priority_str in ["HIGH", "CRITICAL"]
                or shelter_need_item is not None
            )

            # Check if description/summary mentions displacement or evacuation
            text_corpus = f"{context.situation_title} {context.description} {context.location_summary}".lower()
            if any(term in text_corpus for term in ["evacuat", "displace", "homeless", "shelter", "camp", "flood", "submerge", "collapse"]):
                has_displacement_risk = True

            if not has_displacement_risk and not shelter_need_item:
                # Shelter is not required for this incident type
                summary = ShelterCoordinationSummary(
                    shelter_required=False,
                    requirement_reason=ShelterConflictType.SHELTER_NOT_REQUIRED.value,
                    affected_population=0,
                    population_confidence=1.0,
                    shelters_evaluated=0,
                    shelters_recommended=[],
                    total_capacity_available=0.0,
                    total_population_covered=0.0,
                    total_shortfall=0.0,
                    conflicts=[ShelterConflictType.SHELTER_NOT_REQUIRED.value],
                    officer_attention_required=False,
                    explanation=(
                        f"Shelter coordination not required for situation {context.situation_id} "
                        f"({emergency_type} with priority {effective_priority_str}). No displacement indicators detected."
                    ),
                    confidence=1.0,
                    generated_at=datetime.now(timezone.utc),
                    agent_version="1.0.0",
                )
                return AgentResult(
                    agent_name=self.name,
                    run_id=run_id,
                    status=AgentRunStatus.COMPLETED,
                    recommendation="No emergency shelter facilities required for this incident.",
                    structured_output=summary.model_dump(),
                    confidence=1.0,
                    evidence=["Zero displacement risk or shelter needs identified for current emergency profile."],
                    warnings=[],
                    constraints=constraints,
                    generated_at=datetime.now(timezone.utc),
                )

            # 2. Extract and evaluate affected population
            affected_pop: Optional[int] = None
            param_pop = context.parameters.get("affected_population") or context.parameters.get("estimated_affected_population")
            if param_pop is not None and int(param_pop) > 0:
                affected_pop = int(param_pop)
            elif shelter_need_item and float(shelter_need_item.get("requested_quantity", 0)) > 0:
                affected_pop = int(float(shelter_need_item.get("requested_quantity", 0)))
            elif context.report_count > 0:
                alt_pop = context.parameters.get("situation_affected_population")
                if alt_pop is not None and int(alt_pop) > 0:
                    affected_pop = int(alt_pop)

            conflicts: List[str] = []
            officer_attention_required = False

            if affected_pop is None or affected_pop <= 0:
                conflicts.append(ShelterConflictType.POPULATION_DATA_UNAVAILABLE.value)
                officer_attention_required = True
                warnings.append("Estimated affected population is unavailable or unassessed. Flagged for officer review.")
                evidence.append("Population data missing from situation assessment; deterministic capacity assignment paused.")

            # 3. Retrieve real shelter facilities from parameters / database
            raw_shelters = context.parameters.get("available_shelters") or context.available_resources or []
            shelter_records: List[Dict[str, Any]] = []
            for item in raw_shelters:
                r_type = item.get("resource_type")
                if r_type in [ResourceType.SHELTER, ResourceType.SHELTER.value, "Shelter"]:
                    shelter_records.append(item)

            evaluated_count = len(shelter_records)
            eligible_shelters: List[Dict[str, Any]] = []

            sit_lat = context.center_latitude
            sit_lon = context.center_longitude

            for s in shelter_records:
                shelter_id = s.get("resource_id") or s.get("shelter_id") or str(s.get("_id", "UNKNOWN"))
                name = s.get("name", "Emergency Shelter Facility")
                total_cap = float(s.get("quantity_total", s.get("total_capacity", 0.0)))
                qty_avail = float(s.get("quantity_available", s.get("available_capacity", total_cap)))
                status = str(s.get("status", "AVAILABLE")).upper()
                condition = str(s.get("condition", "GOOD")).upper()

                # Calculate occupancy and remaining capacity
                current_occ = max(0.0, total_cap - qty_avail) if s.get("current_occupancy") is None else float(s.get("current_occupancy", 0.0))
                remaining_cap = max(0.0, total_cap - current_occ)

                # Check data consistency
                if total_cap < 0 or current_occ < 0 or current_occ > total_cap or qty_avail > total_cap:
                    conflicts.append(ShelterConflictType.SHELTER_DATA_CONFLICT.value)
                    warnings.append(f"Shelter {name} ({shelter_id}) has inconsistent capacity data: Total={total_cap}, Occ={current_occ}, Avail={qty_avail}.")
                    continue

                # Check if shelter is full
                if remaining_cap <= 0:
                    conflicts.append(ShelterConflictType.SHELTER_FULL.value)
                    evidence.append(f"Shelter {name} ({shelter_id}) is at maximum capacity (0 beds remaining).")
                    continue

                # Check status availability and condition
                if status in ["UNAVAILABLE", "CLOSED", "OFFLINE", "MAINTENANCE"] or status not in ["AVAILABLE", "ACTIVE", "READY", "STANDBY"]:
                    if status == "CLOSED":
                        conflicts.append(ShelterConflictType.SHELTER_CLOSED.value)
                    else:
                        conflicts.append(ShelterConflictType.SHELTER_UNAVAILABLE.value)
                    evidence.append(f"Shelter {name} ({shelter_id}) excluded because status is {status}.")
                    continue

                if condition in ["POOR", "UNUSABLE", "DAMAGED"]:
                    conflicts.append(ShelterConflictType.SHELTER_SUITABILITY_CONFLICT.value)
                    evidence.append(f"Shelter {name} ({shelter_id}) excluded because facility condition is {condition}.")
                    continue

                # Distance calculation
                loc = s.get("location") or {}
                s_lat = loc.get("latitude")
                s_lon = loc.get("longitude")
                s_address = loc.get("address") or loc.get("street_address") or loc.get("city") or "Designated Evacuation Facility"
                accessibility = s.get("accessibility") or s.get("notes") or "Standard Accessibility"

                dist_km = 0.0
                if sit_lat is not None and sit_lon is not None and s_lat is not None and s_lon is not None:
                    try:
                        dist_km = haversine_distance_km(float(sit_lat), float(sit_lon), float(s_lat), float(s_lon))
                    except Exception as dist_err:
                        logger.warning(f"Error computing distance for shelter {shelter_id}: {dist_err}")
                        dist_km = 99.0

                if dist_km > 50.0:
                    conflicts.append(ShelterConflictType.SHELTER_DISTANCE_CONFLICT.value)
                    warnings.append(f"Shelter {name} is {dist_km} km away, exceeding standard 50km response threshold.")

                # Deterministic Ranking Score (0.0 - 100.0)
                # 1. Proximity score (0-40 pts): 40 pts at 0km, decays with distance
                dist_score = max(0.0, round(40.0 - (dist_km * 1.5), 2))

                # 2. Capacity score (0-30 pts): scaled by remaining capacity
                cap_score = min(30.0, round((remaining_cap / (total_cap if total_cap > 0 else 1.0)) * 30.0, 2))

                # 3. Status & Condition score (0-20 pts)
                stat_score = 20.0 if status == "AVAILABLE" else 10.0
                if condition == "GOOD":
                    stat_score += 0.0
                elif condition == "LIMITED":
                    stat_score -= 5.0
                elif condition == "DAMAGED":
                    stat_score -= 10.0
                    conflicts.append(ShelterConflictType.SHELTER_SUITABILITY_CONFLICT.value)
                stat_score = max(0.0, stat_score)

                # 4. Suitability & Accessibility score (0-10 pts)
                suit_score = 10.0
                if "wheelchair" in str(accessibility).lower() or "accessible" in str(accessibility).lower():
                    suit_score = 10.0
                elif "limited access" in str(accessibility).lower():
                    suit_score = 5.0
                    conflicts.append(ShelterConflictType.SHELTER_ACCESSIBILITY_CONFLICT.value)

                total_shelter_score = round(dist_score + cap_score + stat_score + suit_score, 1)

                eligible_shelters.append({
                    "shelter_id": shelter_id,
                    "shelter_name": name,
                    "distance_km": dist_km,
                    "total_capacity": total_cap,
                    "current_occupancy": current_occ,
                    "remaining_capacity": remaining_cap,
                    "status": status,
                    "condition": condition,
                    "address": s_address,
                    "latitude": s_lat,
                    "longitude": s_lon,
                    "accessibility": accessibility,
                    "suitability_score": total_shelter_score,
                    "ranking_factors": {
                        "proximity_score": dist_score,
                        "capacity_score": cap_score,
                        "condition_score": stat_score,
                        "suitability_score": suit_score,
                    },
                })

            # Sort eligible shelters by suitability score descending, then proximity ascending
            eligible_shelters.sort(key=lambda x: (-x["suitability_score"], x["distance_km"]))

            # 4. Capacity Allocation Recommendation & Multi-Shelter Split
            recommended_shelters: List[RecommendedShelter] = []
            target_pop = affected_pop if (affected_pop and affected_pop > 0) else 0
            remaining_needed = float(target_pop)
            total_cap_avail = sum(s["remaining_capacity"] for s in eligible_shelters)
            total_covered = 0.0

            if target_pop > 0:
                for s in eligible_shelters:
                    if remaining_needed <= 0:
                        break
                    alloc = min(s["remaining_capacity"], remaining_needed)
                    if alloc > 0:
                        coverage_pct = round((alloc / target_pop) * 100.0, 1)
                        rec_reason = (
                            f"Allocated {int(alloc)} persons based on {s['distance_km']} km proximity "
                            f"and {int(s['remaining_capacity'])} available bed capacity."
                        )
                        recommended_shelters.append(
                            RecommendedShelter(
                                shelter_id=s["shelter_id"],
                                shelter_name=s["shelter_name"],
                                distance_km=s["distance_km"],
                                total_capacity=s["total_capacity"],
                                current_occupancy=s["current_occupancy"],
                                remaining_capacity=s["remaining_capacity"],
                                recommended_occupancy=alloc,
                                coverage_percentage=coverage_pct,
                                suitability_score=s["suitability_score"],
                                ranking_factors=s["ranking_factors"],
                                recommendation_reason=rec_reason,
                                location_address=s["address"],
                                latitude=s["latitude"],
                                longitude=s["longitude"],
                                status=s["status"],
                                accessibility=s["accessibility"],
                            )
                        )
                        remaining_needed -= alloc
                        total_covered += alloc

                total_shortfall = max(0.0, target_pop - total_covered)

                if total_shortfall > 0:
                    conflicts.append(ShelterConflictType.SHELTER_CAPACITY_SHORTAGE.value)
                    officer_attention_required = True
                    warnings.append(
                        f"Shelter capacity shortfall detected: {int(total_shortfall)} of {target_pop} affected persons cannot be accommodated."
                    )
                    evidence.append(
                        f"Regional shelter shortfall of {int(total_shortfall)} persons requires officer consideration of emergency temporary encampments."
                    )

                if len(recommended_shelters) > 1:
                    evidence.append(
                        f"Multi-shelter split applied across {len(recommended_shelters)} facilities to safely distribute {int(total_covered)} evacuees."
                    )
            else:
                total_shortfall = 0.0

            if len(eligible_shelters) == 0 and target_pop > 0:
                conflicts.append(ShelterConflictType.NO_FEASIBLE_SHELTER.value)
                officer_attention_required = True
                warnings.append("Zero eligible emergency shelters available within the operational zone.")

            # Unique conflicts list preserving order
            unique_conflicts = list(dict.fromkeys(conflicts))

            explanation = (
                f"Evaluated {evaluated_count} shelter record(s) for situation {context.situation_id}. "
                f"Recommended {len(recommended_shelters)} shelter facility(ies) covering {int(total_covered)} / {target_pop if target_pop else 'N/A'} "
                f"affected individuals with {int(total_shortfall)} capacity shortfall."
            )

            summary = ShelterCoordinationSummary(
                shelter_required=True,
                requirement_reason="DISASTER_DISPLACEMENT_ASSESSMENT_ACTIVE",
                affected_population=affected_pop,
                population_confidence=1.0 if affected_pop else 0.0,
                shelters_evaluated=evaluated_count,
                shelters_recommended=recommended_shelters,
                total_capacity_available=total_cap_avail,
                total_population_covered=total_covered,
                total_shortfall=total_shortfall,
                conflicts=unique_conflicts,
                officer_attention_required=officer_attention_required,
                explanation=explanation,
                confidence=0.95 if target_pop > 0 and total_shortfall == 0 else 0.85,
                generated_at=datetime.now(timezone.utc),
                agent_version="1.0.0",
            )

            rec_text = (
                f"Recommend activating {len(recommended_shelters)} shelter facility(ies) to accommodate {int(total_covered)} evacuees."
                if recommended_shelters
                else "No shelter allocation recommended due to unavailable capacity or zero affected population."
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
            logger.exception(f"Unhandled exception in ShelterCoordinationAgent execute: {e}")
            summary = ShelterCoordinationSummary(
                shelter_required=True,
                requirement_reason="EXECUTION_ERROR_FALLBACK",
                affected_population=0,
                population_confidence=0.0,
                shelters_evaluated=0,
                shelters_recommended=[],
                total_capacity_available=0.0,
                total_population_covered=0.0,
                total_shortfall=0.0,
                conflicts=[ShelterConflictType.NO_FEASIBLE_SHELTER.value],
                officer_attention_required=True,
                explanation=f"Shelter coordination encountered an unexpected error: {str(e)}",
                confidence=0.0,
                generated_at=datetime.now(timezone.utc),
                agent_version="1.0.0",
            )
            return AgentResult(
                agent_name=self.name,
                run_id=run_id,
                status=AgentRunStatus.FALLBACK,
                recommendation="Shelter coordination evaluation paused due to internal error.",
                structured_output=summary.model_dump(),
                confidence=0.0,
                evidence=[],
                warnings=[f"Agent execution failed with exception: {str(e)}"],
                constraints=constraints,
                generated_at=datetime.now(timezone.utc),
            )
