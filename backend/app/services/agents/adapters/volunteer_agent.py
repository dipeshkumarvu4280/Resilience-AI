import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from app.models.enums import (
    AgentName,
    AgentRunStatus,
    VolunteerConflictType,
    VolunteerSkill,
    VolunteerAvailability,
    SeverityLevel,
)
from app.models.agent import (
    AgentContext,
    AgentResult,
    RecommendedVolunteerAssignment,
    VolunteerCoordinationSummary,
)
from app.services.agents.base import BaseAgent
from app.services.resource_matching import haversine_distance_km

logger = logging.getLogger("resilience.agents.volunteer")


class VolunteerCoordinationAgent(BaseAgent):
    """
    Volunteer & Field Operations Coordination Agent.
    Evaluates field support requirements (search and rescue, first aid triage, shelter support,
    and emergency distribution) against authentic registered volunteers in MongoDB.
    Deterministically matches volunteers by verified skills, availability status, and zone proximity.
    Operates strictly in an ADVISORY capacity without mutating volunteer records autonomously.
    """

    @property
    def name(self) -> AgentName:
        return AgentName.VOLUNTEER_AGENT

    @property
    def purpose(self) -> str:
        return (
            "Evaluates field operational needs and matches certified, available volunteer "
            "responders by skill, availability, and geographic zone."
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
        run_id = f"RUN-VOL-{uuid.uuid4().hex[:8].upper()}"
        evidence: List[str] = []
        warnings: List[str] = []
        constraints: List[str] = [
            "Advisory only: Emergency Officer review is mandatory prior to field dispatch.",
            "Zero mutation: Volunteer availability and assignment records are never altered autonomously.",
        ]

        try:
            emergency_type = context.emergency_type or "Other"
            effective_priority = context.officer_severity_override or context.parameters.get("effective_priority") or SeverityLevel.MEDIUM
            effective_priority_str = str(effective_priority.value if hasattr(effective_priority, "value") else effective_priority).upper()

            # 1. Determine required skills and volunteer demand from situation profile
            required_skills: List[str] = []
            if emergency_type in ["Building Collapse", "Landslide", "Missing / Trapped Person"]:
                required_skills.extend([VolunteerSkill.SEARCH_AND_RESCUE.value, VolunteerSkill.FIRST_AID.value])
            elif emergency_type in ["Flood", "Cyclone / Storm"]:
                required_skills.extend([VolunteerSkill.SHELTER_MANAGEMENT.value, VolunteerSkill.LOGISTICS.value, VolunteerSkill.SEARCH_AND_RESCUE.value])
            elif emergency_type in ["Fire"]:
                required_skills.extend([VolunteerSkill.FIRST_AID.value, VolunteerSkill.LOGISTICS.value])
            elif emergency_type in ["Medical Emergency", "Road Accident"]:
                required_skills.extend([VolunteerSkill.FIRST_AID.value, VolunteerSkill.MEDICAL_SUPPORT.value])
            else:
                required_skills.append(VolunteerSkill.OTHER.value)

            # Check if volunteers are required
            is_active_operation = effective_priority_str in ["HIGH", "CRITICAL"] or len(context.existing_needs) > 0 or context.report_count >= 1
            volunteers_required = is_active_operation and emergency_type != "Minor Incident"

            if not volunteers_required:
                summary = VolunteerCoordinationSummary(
                    volunteers_required=False,
                    requirement_reason=VolunteerConflictType.VOLUNTEER_NOT_REQUIRED.value,
                    estimated_volunteers_needed=0,
                    volunteers_evaluated=0,
                    volunteers_recommended=[],
                    total_volunteers_assigned=0,
                    total_shortfall=0,
                    conflicts=[VolunteerConflictType.VOLUNTEER_NOT_REQUIRED.value],
                    officer_attention_required=False,
                    explanation=(
                        f"Volunteer field deployment not required for situation {context.situation_id} "
                        f"({emergency_type} with priority {effective_priority_str}). Incident contained."
                    ),
                    confidence=1.0,
                    generated_at=datetime.now(timezone.utc),
                    agent_version="1.0.0",
                )
                return AgentResult(
                    agent_name=self.name,
                    run_id=run_id,
                    status=AgentRunStatus.COMPLETED,
                    recommendation="No field volunteer activation required for this incident.",
                    structured_output=summary.model_dump(),
                    confidence=1.0,
                    evidence=["Zero field assistance requirements identified for current operational profile."],
                    warnings=[],
                    constraints=constraints,
                    generated_at=datetime.now(timezone.utc),
                )

            # Derive estimated volunteer demand
            demand_param = context.parameters.get("volunteers_needed") or context.parameters.get("estimated_volunteers_needed")
            if demand_param is not None and int(demand_param) > 0:
                needed_count = int(demand_param)
            else:
                # Deterministic baseline: 2 for medium, 4 for high, 6 for critical
                if effective_priority_str == "CRITICAL":
                    needed_count = 6
                elif effective_priority_str == "HIGH":
                    needed_count = 4
                else:
                    needed_count = 2

            # 2. Load genuine volunteer records
            volunteer_records: List[Dict[str, Any]] = context.parameters.get("available_volunteers") or []
            evaluated_count = len(volunteer_records)

            conflicts: List[str] = []
            officer_attention_required = False
            eligible_volunteers: List[Dict[str, Any]] = []

            sit_lat = context.center_latitude
            sit_lon = context.center_longitude
            sit_zone = context.location_summary or ""

            for v in volunteer_records:
                v_id = v.get("volunteer_id") or v.get("user_id") or str(v.get("_id", "UNKNOWN"))
                name = v.get("full_name") or v.get("name", "Registered Volunteer Responder")
                prof = v.get("volunteer_profile") or {}
                skills = prof.get("skills") or v.get("skills") or []
                avail = prof.get("availability") or v.get("availability") or VolunteerAvailability.IMMEDIATE.value
                zone = prof.get("zone_or_district") or v.get("zone_or_district") or v.get("district") or ""
                phone = v.get("phone")
                is_active = v.get("is_active", True)

                # Check active status
                if not is_active:
                    conflicts.append(VolunteerConflictType.VOLUNTEER_UNAVAILABLE.value)
                    evidence.append(f"Volunteer {name} ({v_id}) excluded because account is inactive.")
                    continue

                # Check availability status
                if avail in [VolunteerAvailability.UNAVAILABLE.value, "Unavailable", "UNAVAILABLE"]:
                    conflicts.append(VolunteerConflictType.VOLUNTEER_UNAVAILABLE.value)
                    evidence.append(f"Volunteer {name} ({v_id}) excluded because current availability is {avail}.")
                    continue

                # Skill evaluation
                matched_skill = None
                for req in required_skills:
                    if any(req.lower() in s.lower() or s.lower() in req.lower() for s in skills):
                        matched_skill = req
                        break

                if not matched_skill and skills:
                    matched_skill = skills[0]
                elif not matched_skill:
                    matched_skill = VolunteerSkill.OTHER.value

                # Deterministic suitability score (0-100 pts)
                # 1. Skill match score (0-40 pts)
                skill_score = 40.0 if any(req.lower() in str(skills).lower() for req in required_skills) else 20.0

                # 2. Availability score (0-30 pts)
                if avail == VolunteerAvailability.IMMEDIATE.value or "Immediate" in avail:
                    avail_score = 30.0
                elif avail == VolunteerAvailability.STANDBY.value or "Standby" in avail:
                    avail_score = 20.0
                else:
                    avail_score = 10.0

                # 3. Zone / Geographic score (0-30 pts)
                dist_km = None
                loc = v.get("location") or {}
                v_lat = loc.get("latitude")
                v_lon = loc.get("longitude")
                if sit_lat is not None and sit_lon is not None and v_lat is not None and v_lon is not None:
                    try:
                        dist_km = haversine_distance_km(float(sit_lat), float(sit_lon), float(v_lat), float(v_lon))
                        geo_score = max(0.0, round(30.0 - (dist_km * 1.0), 1))
                    except Exception:
                        geo_score = 15.0
                elif sit_zone and zone and (sit_zone.lower() in zone.lower() or zone.lower() in sit_zone.lower()):
                    geo_score = 30.0
                else:
                    geo_score = 15.0

                total_score = round(skill_score + avail_score + geo_score, 1)

                eligible_volunteers.append({
                    "volunteer_id": v_id,
                    "volunteer_name": name,
                    "matched_skill": matched_skill,
                    "skills": skills,
                    "availability": avail,
                    "zone": zone,
                    "phone": phone,
                    "distance_km": dist_km,
                    "suitability_score": total_score,
                })

            # Sort eligible volunteers by score descending
            eligible_volunteers.sort(key=lambda x: -x["suitability_score"])

            # 3. Match up to needed_count volunteers
            recommended_assignments: List[RecommendedVolunteerAssignment] = []
            for ev in eligible_volunteers[:needed_count]:
                # Assign operation based on matched skill
                op_name = "Field Response Operations"
                if "Search" in ev["matched_skill"]:
                    op_name = "Search & Rescue Operations"
                elif "First Aid" in ev["matched_skill"] or "Medical" in ev["matched_skill"]:
                    op_name = "First Aid & Medical Triage"
                elif "Shelter" in ev["matched_skill"]:
                    op_name = "Evacuation Shelter Support"
                elif "Logistics" in ev["matched_skill"]:
                    op_name = "Emergency Relief Distribution"

                rec_reason = (
                    f"Matched with score {ev['suitability_score']}/100. "
                    f"Certified in {', '.join(ev['skills']) if ev['skills'] else 'General Support'} "
                    f"({ev['availability']})."
                )

                recommended_assignments.append(
                    RecommendedVolunteerAssignment(
                        volunteer_id=ev["volunteer_id"],
                        volunteer_name=ev["volunteer_name"],
                        role_or_skill=ev["matched_skill"],
                        assigned_operation=op_name,
                        location_zone=ev["zone"] or context.location_summary,
                        distance_km=ev["distance_km"],
                        suitability_score=ev["suitability_score"],
                        availability_status=ev["availability"],
                        recommendation_reason=rec_reason,
                        phone=ev["phone"],
                    )
                )

            total_assigned = len(recommended_assignments)
            total_shortfall = max(0, needed_count - total_assigned)

            if total_shortfall > 0:
                conflicts.append(VolunteerConflictType.VOLUNTEER_SHORTAGE.value)
                officer_attention_required = True
                warnings.append(
                    f"Volunteer field shortfall: {total_shortfall} of {needed_count} required responders cannot be sourced from active registry."
                )
                evidence.append(
                    f"Field operations shortfall of {total_shortfall} volunteers flagged for mutual aid request."
                )

            if len(eligible_volunteers) == 0 and needed_count > 0:
                conflicts.append(VolunteerConflictType.NO_FEASIBLE_VOLUNTEER.value)
                officer_attention_required = True
                warnings.append("Zero eligible active volunteers available in the operational zone.")

            unique_conflicts = list(dict.fromkeys(conflicts))

            explanation = (
                f"Evaluated {evaluated_count} registered volunteer(s) for situation {context.situation_id}. "
                f"Recommended {total_assigned} responder(s) covering {total_assigned} / {needed_count} "
                f"field assignments with {total_shortfall} responder shortfall."
            )

            summary = VolunteerCoordinationSummary(
                volunteers_required=True,
                requirement_reason="EMERGENCY_FIELD_OPERATIONS_ACTIVE",
                estimated_volunteers_needed=needed_count,
                volunteers_evaluated=evaluated_count,
                volunteers_recommended=recommended_assignments,
                total_volunteers_assigned=total_assigned,
                total_available=len(eligible_volunteers),
                total_volunteers_available=len(eligible_volunteers),
                total_shortfall=total_shortfall,
                conflicts=unique_conflicts,
                officer_attention_required=officer_attention_required,
                explanation=explanation,
                confidence=0.95 if total_shortfall == 0 else 0.85,
                generated_at=datetime.now(timezone.utc),
                agent_version="1.0.0",
            )

            rec_text = (
                f"Recommend dispatching {total_assigned} registered field volunteer(s) across {total_assigned} response tasks."
                if recommended_assignments
                else "No volunteer deployment recommended due to zero available registered responders."
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
            logger.exception(f"Unhandled exception in VolunteerCoordinationAgent: {e}")
            summary = VolunteerCoordinationSummary(
                volunteers_required=True,
                requirement_reason="EXECUTION_ERROR_FALLBACK",
                estimated_volunteers_needed=0,
                volunteers_evaluated=0,
                volunteers_recommended=[],
                total_volunteers_assigned=0,
                total_shortfall=0,
                conflicts=[VolunteerConflictType.NO_FEASIBLE_VOLUNTEER.value],
                officer_attention_required=True,
                explanation=f"Volunteer coordination encountered an unexpected error: {str(e)}",
                confidence=0.0,
                generated_at=datetime.now(timezone.utc),
                agent_version="1.0.0",
            )
            return AgentResult(
                agent_name=self.name,
                run_id=run_id,
                status=AgentRunStatus.FALLBACK,
                recommendation="Volunteer coordination evaluation paused due to internal error.",
                structured_output=summary.model_dump(),
                confidence=0.0,
                evidence=[],
                warnings=[f"Agent execution failed with exception: {str(e)}"],
                constraints=constraints,
                generated_at=datetime.now(timezone.utc),
            )
