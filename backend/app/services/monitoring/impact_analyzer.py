import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.enums import (
    MonitoringEventType,
    EventSourceType,
    ImpactLevel,
    PlanValidityStatus,
    OperationalDomain,
    AgentName,
    CoordinationPlanStatus,
    SeverityLevel,
)
from app.models.monitoring import MonitoringEvent, ChangeImpactResult
from app.models.agent import CoordinationPlan

logger = logging.getLogger("resilience.monitoring.impact_analyzer")

# Authoritative topological execution order from CentralOrchestrator
TOPOLOGICAL_AGENT_ORDER = [
    AgentName.PRIORITY_AGENT,
    AgentName.NEEDS_AGENT,
    AgentName.RESOURCE_COORDINATION_AGENT,
    AgentName.SHELTER_AGENT,
    AgentName.HEALTHCARE_AGENT,
    AgentName.VOLUNTEER_AGENT,
    AgentName.ROUTE_AGENT,
    AgentName.CONFLICT_RESOLUTION_AGENT,
]


class ChangeImpactAnalyzer:
    """
    Deterministic Change Impact Analyzer.
    Evaluates normalized monitoring events against active Situations and Response Plans.
    Determines violated constraints, mathematical shortfalls, plan validity status,
    and dependency-aware affected agent sets without executing agents or mutating plans.
    """

    @classmethod
    async def analyze_impact(
        cls,
        event: MonitoringEvent,
        situation: Optional[Dict[str, Any]] = None,
        active_plan: Optional[CoordinationPlan] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> ChangeImpactResult:
        impact_id = f"IMP-{uuid.uuid4().hex[:10].upper()}"

        changed_entity = f"{event.source_type.value}:{event.source_id}"
        changed_fields = list(event.changed_fields)
        previous_state = dict(event.previous_state)
        new_state = dict(event.new_state)

        affected_domains: List[OperationalDomain] = []
        affected_agents_set: set[AgentName] = set()
        affected_plan_components: List[str] = []
        violated_constraints: List[str] = []
        shortfalls: Dict[str, float] = {}
        officer_attention_required = False
        impact_level = ImpactLevel.NONE
        plan_status = PlanValidityStatus.UNAFFECTED
        reasons: List[str] = []

        # -----------------------------------------------------------------
        # DOMAIN 1: RESOURCE INVENTORY CHANGES
        # -----------------------------------------------------------------
        if event.source_type == EventSourceType.RESOURCE_INVENTORY:
            affected_domains.append(OperationalDomain.RESOURCE)
            r_type = new_state.get("resource_type") or previous_state.get("resource_type") or "Resource"
            r_name = new_state.get("name") or previous_state.get("name") or event.source_id

            qty_before = float(previous_state.get("quantity_available", previous_state.get("quantity_total", 0.0)))
            qty_after = float(new_state.get("quantity_available", new_state.get("quantity_total", 0.0)))
            status_after = str(new_state.get("status", "AVAILABLE")).upper()

            # Check if active plan depends on this resource
            matched_alloc = None
            if active_plan:
                for alloc in active_plan.recommended_allocations:
                    if (
                        alloc.matched_resource_id == event.source_id
                        or alloc.resource_type.value.lower() == str(r_type).lower()
                    ):
                        matched_alloc = alloc
                        break

            if matched_alloc:
                req_qty = float(matched_alloc.allocated_quantity or matched_alloc.quantity_required)
                affected_plan_components.append(
                    f"Resource allocation: {matched_alloc.resource_type.value} ({r_name}) allocated {req_qty} {matched_alloc.unit}"
                )

                if status_after == "UNAVAILABLE":
                    impact_level = ImpactLevel.CRITICAL
                    plan_status = PlanValidityStatus.INVALIDATED
                    officer_attention_required = True
                    violated_constraints.append(f"Allocated resource {r_name} is now marked UNAVAILABLE.")
                    shortfall = req_qty
                    shortfalls[f"{r_name}_{r_type}"] = shortfall
                    affected_agents_set.update([AgentName.RESOURCE_COORDINATION_AGENT, AgentName.CONFLICT_RESOLUTION_AGENT])
                    reasons.append(f"Allocated resource {r_name} became unavailable; active response plan cannot fulfill {req_qty} {matched_alloc.unit}.")
                elif qty_after < req_qty:
                    shortfall = max(0.0, req_qty - qty_after)
                    shortfalls[f"{r_name}_{r_type}"] = shortfall
                    impact_level = ImpactLevel.HIGH if shortfall > 0 else ImpactLevel.MEDIUM
                    plan_status = PlanValidityStatus.INVALIDATED if shortfall > 0 else PlanValidityStatus.POTENTIALLY_AFFECTED
                    officer_attention_required = True
                    violated_constraints.append(
                        f"Resource {r_name} available inventory decreased from {qty_before} to {qty_after}, resulting in a shortfall of {shortfall} {matched_alloc.unit}."
                    )
                    affected_agents_set.update([AgentName.RESOURCE_COORDINATION_AGENT, AgentName.CONFLICT_RESOLUTION_AGENT])
                    reasons.append(f"Inventory reduction in {r_name} causes a {shortfall} unit shortfall against active plan requirement of {req_qty}.")
                else:
                    impact_level = ImpactLevel.LOW
                    plan_status = PlanValidityStatus.POTENTIALLY_AFFECTED
                    reasons.append(f"Resource {r_name} inventory changed from {qty_before} to {qty_after} but remains sufficient for active plan requirement ({req_qty}).")
            else:
                # Resource changed, but not currently allocated to this active plan
                impact_level = ImpactLevel.LOW if abs(qty_after - qty_before) > 0 else ImpactLevel.NONE
                reasons.append(f"Resource {r_name} state updated ({qty_before} -> {qty_after}, status: {status_after}). No direct allocation conflict with active plan.")

        # -----------------------------------------------------------------
        # DOMAIN 7: CITIZEN REPORT INTAKE
        # -----------------------------------------------------------------
        elif event.source_type == EventSourceType.CITIZEN_REPORT:
            affected_domains.append(OperationalDomain.SITUATION)
            impact_level = ImpactLevel.LOW
            reasons.append(f"Citizen report {event.source_id} intake recorded.")

        # -----------------------------------------------------------------
        # DOMAIN 8: SIMULATED SENSOR INTAKE & THRESHOLD BREACHES
        # -----------------------------------------------------------------
        elif event.source_type == EventSourceType.SIMULATED_SENSOR:
            affected_domains.append(OperationalDomain.SITUATION)
            s_name = new_state.get("name") or event.metadata.get("sensor_name") or event.source_id
            curr_val = event.metadata.get("current_value")
            thresh = event.metadata.get("threshold")
            unit = event.metadata.get("unit", "")

            if event.event_type == MonitoringEventType.SENSOR_THRESHOLD_BREACHED:
                affected_plan_components.append(f"Sensor monitoring: {s_name} ({curr_val} {unit} > {thresh} {unit})")
                impact_level = ImpactLevel.HIGH if event.severity == SeverityLevel.CRITICAL else ImpactLevel.MEDIUM
                plan_status = PlanValidityStatus.REQUIRES_OFFICER_REVIEW
                officer_attention_required = True
                violated_constraints.append(f"Sensor threshold breached for {s_name}: {curr_val} {unit} exceeds threshold of {thresh} {unit}.")
                affected_agents_set.update([
                    AgentName.PRIORITY_AGENT,
                    AgentName.NEEDS_AGENT,
                    AgentName.RESOURCE_COORDINATION_AGENT,
                    AgentName.CONFLICT_RESOLUTION_AGENT,
                ])
                reasons.append(f"Sensor threshold breach at {s_name} indicates escalating environmental hazard ({curr_val} {unit} vs threshold {thresh} {unit}).")
            elif event.event_type == MonitoringEventType.SENSOR_RECOVERED:
                impact_level = ImpactLevel.LOW
                plan_status = PlanValidityStatus.POTENTIALLY_AFFECTED
                reasons.append(f"Sensor {s_name} recovered to safe operating threshold ({curr_val} {unit} <= {thresh} {unit}).")
            else:
                impact_level = ImpactLevel.NONE
                reasons.append(f"Sensor {s_name} reading recorded ({curr_val} {unit}).")

        # -----------------------------------------------------------------
        # DOMAIN 2: SHELTER FACILITY CHANGES
        # -----------------------------------------------------------------
        elif event.source_type == EventSourceType.SHELTER_FACILITY:
            affected_domains.append(OperationalDomain.SHELTER)
            s_name = new_state.get("name") or previous_state.get("name") or event.source_id
            tot_cap = float(new_state.get("quantity_total", previous_state.get("quantity_total", 0.0)))
            occ_before = float(previous_state.get("current_occupancy", 0.0))
            occ_after = float(new_state.get("current_occupancy", 0.0))
            status_after = str(new_state.get("status", "AVAILABLE")).upper()

            rem_before = max(0.0, tot_cap - occ_before)
            rem_after = max(0.0, tot_cap - occ_after)

            matched_shelter = None
            if active_plan:
                for shl in active_plan.recommended_shelters:
                    if shl.shelter_id == event.source_id:
                        matched_shelter = shl
                        break

            if matched_shelter:
                allocated_pop = float(getattr(matched_shelter, "recommended_occupancy", getattr(matched_shelter, "allocated_population", 0.0)))
                affected_plan_components.append(
                    f"Shelter allocation: {s_name} ({matched_shelter.shelter_id}) allocated {allocated_pop} beds/people"
                )

                if status_after in ["UNAVAILABLE", "CLOSED"]:
                    impact_level = ImpactLevel.CRITICAL
                    plan_status = PlanValidityStatus.INVALIDATED
                    officer_attention_required = True
                    violated_constraints.append(f"Shelter {s_name} is now {status_after}.")
                    shortfalls[f"{s_name}_shelter_capacity"] = allocated_pop
                    affected_agents_set.update([AgentName.SHELTER_AGENT, AgentName.CONFLICT_RESOLUTION_AGENT])
                    reasons.append(f"Assigned shelter {s_name} became {status_after}, invalidating shelter allocation of {allocated_pop} persons.")
                elif rem_after < allocated_pop:
                    shortfall = max(0.0, allocated_pop - rem_after)
                    shortfalls[f"{s_name}_shelter_capacity"] = shortfall
                    impact_level = ImpactLevel.CRITICAL if shortfall > 0 else ImpactLevel.HIGH
                    plan_status = PlanValidityStatus.INVALIDATED
                    officer_attention_required = True
                    violated_constraints.append(
                        f"Shelter {s_name} remaining capacity reduced to {rem_after} (occupancy: {occ_after}/{tot_cap}), failing active plan requirement of {allocated_pop} (shortfall: {shortfall})."
                    )
                    affected_agents_set.update([AgentName.SHELTER_AGENT, AgentName.CONFLICT_RESOLUTION_AGENT])
                    reasons.append(f"Shelter {s_name} capacity breach: remaining capacity {rem_after} is less than planned allocation {allocated_pop}.")
                else:
                    impact_level = ImpactLevel.LOW
                    plan_status = PlanValidityStatus.POTENTIALLY_AFFECTED
                    reasons.append(f"Shelter {s_name} occupancy changed ({occ_before} -> {occ_after}) but remaining capacity ({rem_after}) satisfies planned allocation ({allocated_pop}).")
            else:
                impact_level = ImpactLevel.LOW if abs(occ_after - occ_before) > 0 else ImpactLevel.NONE
                reasons.append(f"Shelter {s_name} capacity updated ({occ_before} -> {occ_after} occupancy). Not assigned in active plan.")

        # -----------------------------------------------------------------
        # DOMAIN 3: HEALTHCARE FACILITY CHANGES
        # -----------------------------------------------------------------
        elif event.source_type == EventSourceType.HEALTHCARE_FACILITY:
            affected_domains.append(OperationalDomain.HEALTHCARE)
            h_name = new_state.get("facility_name") or previous_state.get("facility_name") or event.source_id
            beds_before = float(previous_state.get("available_beds", 0.0))
            beds_after = float(new_state.get("available_beds", 0.0))
            status_after = str(new_state.get("facility_status", "OPERATIONAL")).upper()

            matched_fac = None
            if active_plan:
                for fac in active_plan.recommended_facilities:
                    if fac.facility_id == event.source_id:
                        matched_fac = fac
                        break

            if matched_fac:
                allocated_casualties = float(getattr(matched_fac, "allocated_patients", getattr(matched_fac, "allocated_casualties", 0.0)))
                affected_plan_components.append(
                    f"Healthcare allocation: {h_name} allocated {allocated_casualties} casualties"
                )

                if status_after in ["UNAVAILABLE", "OUTAGE", "CLOSED"]:
                    impact_level = ImpactLevel.CRITICAL
                    plan_status = PlanValidityStatus.INVALIDATED
                    officer_attention_required = True
                    violated_constraints.append(f"Healthcare facility {h_name} is now {status_after}.")
                    shortfalls[f"{h_name}_medical_beds"] = allocated_casualties
                    affected_agents_set.update([
                        AgentName.HEALTHCARE_AGENT,
                        AgentName.ROUTE_AGENT,
                        AgentName.CONFLICT_RESOLUTION_AGENT,
                    ])
                    reasons.append(f"Assigned hospital {h_name} is {status_after}, requiring casualty rerouting and medical replanning.")
                elif beds_after < allocated_casualties:
                    shortfall = max(0.0, allocated_casualties - beds_after)
                    shortfalls[f"{h_name}_medical_beds"] = shortfall
                    impact_level = ImpactLevel.HIGH
                    plan_status = PlanValidityStatus.INVALIDATED
                    officer_attention_required = True
                    violated_constraints.append(
                        f"Hospital {h_name} available beds decreased from {beds_before} to {beds_after}, causing medical shortfall of {shortfall} beds."
                    )
                    affected_agents_set.update([
                        AgentName.HEALTHCARE_AGENT,
                        AgentName.CONFLICT_RESOLUTION_AGENT,
                    ])
                    reasons.append(f"Hospital {h_name} available beds ({beds_after}) insufficient for planned casualty allocation ({allocated_casualties}).")
                else:
                    impact_level = ImpactLevel.LOW
                    plan_status = PlanValidityStatus.POTENTIALLY_AFFECTED
                    reasons.append(f"Hospital {h_name} bed capacity changed ({beds_before} -> {beds_after}) but remains sufficient for {allocated_casualties} casualties.")
            else:
                impact_level = ImpactLevel.LOW if abs(beds_after - beds_before) > 0 else ImpactLevel.NONE
                reasons.append(f"Healthcare facility {h_name} capacity updated ({beds_before} -> {beds_after}). Not assigned in active plan.")

        # -----------------------------------------------------------------
        # DOMAIN 4: VOLUNTEER & PERSONNEL CHANGES
        # -----------------------------------------------------------------
        elif event.source_type == EventSourceType.VOLUNTEER_NETWORK:
            affected_domains.append(OperationalDomain.VOLUNTEER)
            v_name = new_state.get("full_name") or previous_state.get("full_name") or event.source_id
            avail_after = str(new_state.get("availability", "Available Immediately"))
            status_after = str(new_state.get("status", "ACTIVE")).upper()

            matched_vol = None
            if active_plan:
                for vol in active_plan.recommended_volunteers:
                    if vol.volunteer_id == event.source_id:
                        matched_vol = vol
                        break

            if matched_vol:
                vol_mission = str(getattr(matched_vol, "assigned_operation", getattr(matched_vol, "assigned_mission", "Emergency Operation")))
                affected_plan_components.append(
                    f"Volunteer assignment: {v_name} assigned to mission '{vol_mission}'"
                )

                if status_after != "ACTIVE" or "Unavailable" in avail_after:
                    impact_level = ImpactLevel.HIGH
                    plan_status = PlanValidityStatus.POTENTIALLY_AFFECTED
                    officer_attention_required = True
                    violated_constraints.append(f"Assigned volunteer responder {v_name} is now {avail_after} / {status_after}.")
                    shortfalls[f"{v_name}_personnel"] = 1.0
                    affected_agents_set.update([AgentName.VOLUNTEER_AGENT, AgentName.CONFLICT_RESOLUTION_AGENT])
                    reasons.append(f"Assigned volunteer {v_name} became unavailable for field mission '{vol_mission}'.")
                else:
                    impact_level = ImpactLevel.LOW
                    plan_status = PlanValidityStatus.POTENTIALLY_AFFECTED
                    reasons.append(f"Volunteer {v_name} profile updated, remains active and available.")
            else:
                impact_level = ImpactLevel.LOW if status_after != "ACTIVE" else ImpactLevel.NONE
                reasons.append(f"Volunteer {v_name} state updated (status: {status_after}, availability: {avail_after}). Not assigned in active plan.")

        # -----------------------------------------------------------------
        # DOMAIN 5: TRANSPORT FLEET & ROUTE NETWORK
        # -----------------------------------------------------------------
        elif event.source_type in [EventSourceType.TRANSPORT_FLEET, EventSourceType.ROUTE_NETWORK]:
            affected_domains.extend([OperationalDomain.TRANSPORT, OperationalDomain.ROUTE])
            veh_name = new_state.get("vehicle_name") or previous_state.get("vehicle_name") or event.source_id
            status_after = str(new_state.get("status", "AVAILABLE")).upper()
            road_status_after = str(new_state.get("road_condition_status", "PASSABLE")).upper()

            matched_trans = None
            matched_route = None
            if active_plan:
                for t in active_plan.recommended_transports:
                    if t.transport_id == event.source_id:
                        matched_trans = t
                        break
                for r in active_plan.recommended_routes:
                    if r.route_id == event.source_id or r.transport_id == event.source_id:
                        matched_route = r
                        break

            if matched_trans or matched_route:
                if matched_trans:
                    affected_plan_components.append(f"Transport assignment: {veh_name} on mission '{matched_trans.assigned_mission}'")
                if matched_route:
                    affected_plan_components.append(f"Route assignment: {matched_route.origin_name} -> {matched_route.destination_name}")

                if status_after in ["UNAVAILABLE", "MAINTENANCE", "ASSIGNED_OTHER"] or road_status_after in ["BLOCKED", "IMPASSABLE", "FLOODED"]:
                    impact_level = ImpactLevel.CRITICAL
                    plan_status = PlanValidityStatus.INVALIDATED
                    officer_attention_required = True
                    violated_constraints.append(f"Transport/route asset {veh_name} is {status_after} / road condition is {road_status_after}.")
                    shortfalls[f"{veh_name}_transport"] = 1.0
                    affected_agents_set.update([
                        AgentName.ROUTE_AGENT,
                        AgentName.CONFLICT_RESOLUTION_AGENT,
                    ])
                    reasons.append(f"Transport or transit corridor for {veh_name} is compromised ({status_after}/{road_status_after}).")
                else:
                    impact_level = ImpactLevel.LOW
                    plan_status = PlanValidityStatus.POTENTIALLY_AFFECTED
                    reasons.append(f"Transport/Route asset {veh_name} updated ({status_after}/{road_status_after}), remains operational.")
            else:
                impact_level = ImpactLevel.LOW
                reasons.append(f"Transport/Route entity {veh_name} updated. Not utilized in current active plan.")

        # -----------------------------------------------------------------
        # DOMAIN 6: SITUATION INTELLIGENCE & SEVERITY
        # -----------------------------------------------------------------
        elif event.source_type == EventSourceType.SITUATION_INTELLIGENCE:
            affected_domains.append(OperationalDomain.SITUATION)
            sit_id = event.situation_id or event.source_id
            sev_before = previous_state.get("severity_level") or previous_state.get("computed_severity_level")
            sev_after = new_state.get("severity_level") or new_state.get("computed_severity_level")

            # Check if officer override is active
            officer_override = new_state.get("officer_override_severity") or previous_state.get("officer_override_severity")

            if officer_override:
                reasons.append(f"Situation {sit_id} has explicit Officer Severity Override: {officer_override}. Officer override remains authoritative.")
                impact_level = ImpactLevel.LOW
                plan_status = PlanValidityStatus.POTENTIALLY_AFFECTED
            elif sev_after and sev_before and sev_after != sev_before:
                # Real severity change
                affected_plan_components.append(f"Situation {sit_id} severity transitioned from {sev_before} to {sev_after}")
                if sev_after in ["HIGH", "CRITICAL"]:
                    impact_level = ImpactLevel.HIGH
                    plan_status = PlanValidityStatus.REQUIRES_OFFICER_REVIEW
                    officer_attention_required = True
                    violated_constraints.append(f"Situation severity escalated to {sev_after}. Response plan requirements must be re-evaluated.")
                    # Severity escalation cascades across entire pipeline
                    affected_agents_set.update(TOPOLOGICAL_AGENT_ORDER)
                    reasons.append(f"Severity escalation ({sev_before} -> {sev_after}) invalidates baseline threat model, requiring full downstream review.")
                else:
                    impact_level = ImpactLevel.MEDIUM
                    plan_status = PlanValidityStatus.POTENTIALLY_AFFECTED
                    affected_agents_set.update([AgentName.PRIORITY_AGENT, AgentName.NEEDS_AGENT, AgentName.CONFLICT_RESOLUTION_AGENT])
                    reasons.append(f"Situation severity adjusted ({sev_before} -> {sev_after}).")
            else:
                impact_level = ImpactLevel.LOW
                reasons.append(f"Situation intelligence updated for {sit_id}.")

        # -----------------------------------------------------------------
        # DOMAIN 7: CITIZEN REPORT INTAKE
        # -----------------------------------------------------------------
        elif event.source_type == EventSourceType.CITIZEN_REPORT:
            rep_id = event.source_id
            if situation:
                affected_domains.append(OperationalDomain.SITUATION)
                affected_plan_components.append(f"Incident report {rep_id} attached to situation {situation.get('situation_id')}")
                impact_level = ImpactLevel.MEDIUM
                plan_status = PlanValidityStatus.POTENTIALLY_AFFECTED
                affected_agents_set.update([AgentName.PRIORITY_AGENT, AgentName.NEEDS_AGENT, AgentName.CONFLICT_RESOLUTION_AGENT])
                reasons.append(f"New citizen report {rep_id} fused into active situation {situation.get('situation_id')}. Downstream needs may expand.")
            else:
                impact_level = ImpactLevel.NONE
                plan_status = PlanValidityStatus.UNAFFECTED
                reasons.append(f"Standalone citizen report {rep_id} logged. Not yet fused into an active situation or plan.")

        # -----------------------------------------------------------------
        # DOMAIN 8: OFFICER DECISIONS
        # -----------------------------------------------------------------
        elif event.source_type == EventSourceType.OFFICER_DECISION:
            action = new_state.get("action") or event.event_type.value
            impact_level = ImpactLevel.LOW
            plan_status = PlanValidityStatus.UNAFFECTED
            reasons.append(f"Emergency Officer performed decision action: {action}. Human authority recorded.")

        # -----------------------------------------------------------------
        # DOMAIN 9: SENSOR NETWORK & STALE DATA INTELLIGENCE
        # -----------------------------------------------------------------
        elif event.source_type == EventSourceType.SIMULATED_SENSOR:
            affected_domains.append(OperationalDomain.SITUATION)
            sensor_id = event.source_id
            s_name = event.metadata.get("sensor_name", sensor_id)
            if event.event_type == MonitoringEventType.SENSOR_DATA_STALE:
                impact_level = ImpactLevel.MEDIUM if situation else ImpactLevel.LOW
                plan_status = PlanValidityStatus.POTENTIALLY_AFFECTED
                reasons.append(f"Sensor {s_name} data is now STALE. Sensor evidence reliability reduced; historical context only.")
            elif event.event_type == MonitoringEventType.SENSOR_THRESHOLD_BREACHED:
                impact_level = ImpactLevel.HIGH if situation else ImpactLevel.MEDIUM
                plan_status = PlanValidityStatus.POTENTIALLY_AFFECTED
                affected_agents_set.update([AgentName.PRIORITY_AGENT, AgentName.NEEDS_AGENT])
                reasons.append(f"Critical sensor threshold breached for {s_name}.")
            elif event.event_type == MonitoringEventType.SENSOR_RECOVERED:
                impact_level = ImpactLevel.LOW
                plan_status = PlanValidityStatus.POTENTIALLY_AFFECTED
                reasons.append(f"Sensor {s_name} reading recovered to normal baseline.")
            else:
                impact_level = ImpactLevel.LOW
                reasons.append(f"Sensor event recorded for {s_name}.")

        # Default fallback explanation
        explanation = " ".join(reasons) if reasons else f"Operational change detected in {changed_entity}."

        # Compute topological dependency chain for affected agents
        dependency_chain = [agent for agent in TOPOLOGICAL_AGENT_ORDER if agent in affected_agents_set]

        return ChangeImpactResult(
            impact_id=impact_id,
            event_id=event.event_id,
            situation_id=event.situation_id,
            coordination_plan_id=event.coordination_plan_id,
            impact_level=impact_level,
            plan_status=plan_status,
            changed_entity=changed_entity,
            changed_fields=changed_fields,
            previous_state=previous_state,
            new_state=new_state,
            affected_domains=list(set(affected_domains)),
            affected_agents=list(affected_agents_set),
            dependency_chain=dependency_chain,
            affected_plan_components=affected_plan_components,
            violated_constraints=violated_constraints,
            shortfalls=shortfalls,
            officer_attention_required=officer_attention_required,
            explanation=explanation,
            analyzed_at=datetime.utcnow(),
        )
