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
    ConflictType,
    ResolutionStrategy,
    ConflictStatus,
    ResourceStatus,
    ResourceCondition,
)
from app.models.agent import (
    AgentContext,
    AgentResult,
    DetectedConflict,
    ConflictResolutionSummary,
    PlanRecommendedResource,
)
from app.services.agents.base import BaseAgent

logger = logging.getLogger("resilience.agents.conflict_agent")

_URGENCY_RANKS = {
    NeedUrgency.CRITICAL: 4,
    NeedUrgency.HIGH: 3,
    NeedUrgency.MEDIUM: 2,
    NeedUrgency.LOW: 1,
}


def _get_urgency_rank(urgency_val: Any) -> int:
    if isinstance(urgency_val, NeedUrgency):
        return _URGENCY_RANKS.get(urgency_val, 2)
    try:
        enum_val = NeedUrgency(str(urgency_val).upper())
        return _URGENCY_RANKS.get(enum_val, 2)
    except Exception:
        return 2


def _normalize_res_type(val: Any) -> str:
    if val is None:
        return ""
    if hasattr(val, "value"):
        val = val.value
    s = str(val).strip()
    if s.startswith("ResourceType."):
        s = s.replace("ResourceType.", "")
    return s.lower()


class ConflictResolutionAgent(BaseAgent):
    """
    Conflict Resolution Agent Adapter.
    Evaluates multi-agent coordination inputs for resource shortages, competing demands,
    inventory condition unfitness, and geographical constraints.
    Produces deterministic, explainable resolutions requiring Emergency Officer approval.
    """

    @property
    def name(self) -> AgentName:
        return AgentName.CONFLICT_RESOLUTION_AGENT

    @property
    def purpose(self) -> str:
        return "Analyzes potential resource shortages, competing allocations, status constraints, and geographic limits."

    @property
    def dependencies(self) -> List[AgentName]:
        return [
            AgentName.PRIORITY_AGENT,
            AgentName.NEEDS_AGENT,
            AgentName.RESOURCE_COORDINATION_AGENT,
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["assessed_needs", "recommended_allocations"]

    async def execute(self, context: AgentContext) -> AgentResult:
        run_id = f"RUN-CNF-{uuid.uuid4().hex[:8].upper()}"
        warnings: List[str] = []
        evidence: List[str] = []
        constraints: List[str] = [
            "Conflict resolution recommendations are strictly advisory and do not modify inventory state.",
            "Authoritative Emergency Officer priority overrides take precedence over automated heuristics.",
        ]

        try:
            # 1. Extract inputs from context
            raw_needs = context.parameters.get("assessed_needs") or context.existing_needs or []
            raw_allocations = context.parameters.get("recommended_allocations") or []
            effective_priority_str = context.parameters.get("effective_priority") or (
                context.officer_severity_override.value if context.officer_severity_override else "MEDIUM"
            )
            try:
                effective_priority = SeverityLevel(effective_priority_str)
            except Exception:
                effective_priority = SeverityLevel.MEDIUM

            # If officer override is active, note evidence
            if context.officer_severity_override:
                evidence.append(
                    f"Preserved authoritative officer priority override: {context.officer_severity_override.value}."
                )

            # 2. Run Deterministic Conflict Analysis
            conflicts: List[DetectedConflict] = []
            resolution_actions: List[str] = []
            affected_needs: List[str] = []
            affected_resources: List[str] = []
            shortages: List[Dict[str, Any]] = []

            # Structure working allocations for mutation analysis
            working_allocations: List[Dict[str, Any]] = []
            for alloc in raw_allocations:
                if isinstance(alloc, dict):
                    working_allocations.append(dict(alloc))
                elif hasattr(alloc, "model_dump"):
                    working_allocations.append(alloc.model_dump())
                elif hasattr(alloc, "dict"):
                    working_allocations.append(alloc.dict())

            # Map allocations by resource type and matched_resource_id
            alloc_by_id: Dict[str, List[Dict[str, Any]]] = {}
            for alloc in working_allocations:
                r_id = alloc.get("matched_resource_id")
                if r_id:
                    alloc_by_id.setdefault(r_id, []).append(alloc)

            # ----------------------------------------------------
            # Check A: Resource Shortage / Insufficient Quantity
            # ----------------------------------------------------
            for idx, need in enumerate(raw_needs):
                r_type_raw = need.get("resource_type")
                norm_type = _normalize_res_type(r_type_raw)
                display_type = (
                    r_type_raw.value if hasattr(r_type_raw, "value")
                    else (str(r_type_raw).replace("ResourceType.", "") if r_type_raw else "Resource")
                )
                req_qty = float(need.get("quantity") or need.get("requested_quantity") or 1.0)
                unit = need.get("unit", "Units")
                urgency = need.get("urgency", "HIGH")
                if hasattr(urgency, "value"):
                    urgency = urgency.value
                urgency_str = str(urgency).upper()

                # Find all corresponding allocations matching resource type
                matching_allocs = [
                    a for a in working_allocations
                    if _normalize_res_type(a.get("resource_type")) == norm_type
                ]

                # Calculate authoritative available inventory across matched allocations
                seen_depot_ids = set()
                total_avail_stock = 0.0
                matched_names: List[str] = []

                for a in matching_allocs:
                    r_id = a.get("matched_resource_id")
                    r_name = a.get("matched_resource_name")
                    avail = float(a.get("available_in_inventory") or 0.0)

                    if r_id:
                        if r_id not in seen_depot_ids:
                            seen_depot_ids.add(r_id)
                            total_avail_stock += avail
                        if r_name and r_name not in matched_names:
                            matched_names.append(r_name)
                    elif avail > 0:
                        total_avail_stock += avail

                logger.debug(
                    f"[ConflictAgent Check A] Need '{display_type}': required={req_qty}, "
                    f"available={total_avail_stock}, matched_depots={matched_names}"
                )

                if total_avail_stock == 0.0:
                    # Zero inventory available
                    conf_id = f"CNF-SHT-{uuid.uuid4().hex[:6].upper()}"
                    conf = DetectedConflict(
                        conflict_id=conf_id,
                        conflict_type=ConflictType.RESOURCE_SHORTAGE,
                        severity=SeverityLevel.HIGH if urgency_str in ["HIGH", "CRITICAL"] else SeverityLevel.MEDIUM,
                        description=f"Zero available inventory in regional depots for {req_qty:g} {unit} of {display_type}.",
                        affected_need=f"{display_type} ({req_qty:g} {unit})",
                        affected_resource=display_type,
                        detected_quantity=req_qty,
                        available_quantity=0.0,
                        shortfall=req_qty,
                        resolution_strategy=ResolutionStrategy.NO_FEASIBLE_RESOLUTION,
                        resolution_status=ConflictStatus.UNRESOLVED,
                        officer_attention_required=True,
                        explanation=(
                            f"No active inventory depot holds available stock of {display_type}. "
                            f"Full shortfall of {req_qty:g} {unit} escalated to Emergency Officer."
                        ),
                        alternative_options=[
                            "Request inter-agency mutual aid",
                            "Procure emergency stock from external vendors",
                            "Broadcast volunteer resource appeal",
                        ],
                    )
                    conflicts.append(conf)
                    affected_needs.append(f"{display_type} ({req_qty:g} {unit})")
                    affected_resources.append(display_type)
                    shortages.append({
                        "resource_type": display_type,
                        "requested": req_qty,
                        "available": 0.0,
                        "shortfall": req_qty,
                        "unit": unit,
                    })
                    resolution_actions.append(f"Escalate unfulfilled {display_type} demand ({req_qty:g} {unit}) to Officer.")
                    warnings.append(f"Unmet emergency demand: 0 of {req_qty:g} {unit} {display_type} available.")

                elif total_avail_stock < req_qty:
                    # Partial inventory available
                    shortfall = round(req_qty - total_avail_stock, 2)
                    conf_id = f"CNF-QTY-{uuid.uuid4().hex[:6].upper()}"
                    res_desc = ", ".join(matched_names) if matched_names else display_type
                    conf = DetectedConflict(
                        conflict_id=conf_id,
                        conflict_type=ConflictType.INSUFFICIENT_QUANTITY,
                        severity=SeverityLevel.HIGH if urgency_str in ["HIGH", "CRITICAL"] else SeverityLevel.MEDIUM,
                        description=(
                            f"Available inventory is insufficient for the assessed need "
                            f"({display_type}: Required {req_qty:g} {unit}, Available {total_avail_stock:g} {unit}, Shortfall {shortfall:g} {unit})."
                        ),
                        affected_need=f"{display_type} ({req_qty:g} {unit})",
                        affected_resource=res_desc,
                        detected_quantity=req_qty,
                        available_quantity=total_avail_stock,
                        shortfall=shortfall,
                        resolution_strategy=ResolutionStrategy.PARTIAL_ALLOCATION,
                        resolution_status=ConflictStatus.PARTIALLY_RESOLVED,
                        officer_attention_required=True,
                        explanation=(
                            f"Available inventory is insufficient for the assessed need. "
                            f"{total_avail_stock:g} {unit} is currently available in regional depots against a requirement of {req_qty:g} {unit}, "
                            f"resulting in a {shortfall:g} {unit} shortfall."
                        ),
                        alternative_options=[
                            "Approve partial deployment of available stock",
                            "Source balance from secondary regional depot",
                            "Request inter-agency mutual aid",
                        ],
                    )
                    conflicts.append(conf)
                    affected_needs.append(f"{display_type} ({req_qty:g} {unit})")
                    if res_desc:
                        affected_resources.append(res_desc)
                    shortages.append({
                        "resource_type": display_type,
                        "requested": req_qty,
                        "available": total_avail_stock,
                        "shortfall": shortfall,
                        "unit": unit,
                    })
                    resolution_actions.append(
                        f"Applied PARTIAL_ALLOCATION for {display_type}: {total_avail_stock:g}/{req_qty:g} {unit}."
                    )
                    warnings.append(f"Partial inventory for {display_type}: shortfall of {shortfall:g} {unit}.")
                else:
                    # Fully fulfilled by available inventory -> no conflict
                    logger.debug(
                        f"[ConflictAgent] Need '{display_type}' fully satisfied: "
                        f"required={req_qty}, available={total_avail_stock}"
                    )

            # ----------------------------------------------------
            # Check B: Competing Resource Demands Across Needs
            # ----------------------------------------------------
            for r_id, competing_allocs in alloc_by_id.items():
                if len(competing_allocs) > 1:
                    total_demanded = sum(float(a.get("quantity_required", 0.0)) for a in competing_allocs)
                    avail_stock = float(competing_allocs[0].get("available_in_inventory", 0.0))

                    if total_demanded > avail_stock:
                        conf_id = f"CNF-CMP-{uuid.uuid4().hex[:6].upper()}"
                        res_name = competing_allocs[0].get("matched_resource_name") or r_id
                        
                        # Sort by urgency ranking descending
                        sorted_competing = sorted(
                            competing_allocs,
                            key=lambda x: _get_urgency_rank(x.get("urgency")),
                            reverse=True
                        )

                        conf = DetectedConflict(
                            conflict_id=conf_id,
                            conflict_type=ConflictType.COMPETING_RESOURCE_DEMAND,
                            severity=SeverityLevel.HIGH,
                            description=(
                                f"Multiple emergency needs compete for depot '{res_name}' "
                                f"(Total Demanded: {total_demanded}, Available: {avail_stock})."
                            ),
                            affected_need=", ".join(str(a.get("resource_type")) for a in competing_allocs),
                            affected_resource=res_name,
                            detected_quantity=total_demanded,
                            available_quantity=avail_stock,
                            shortfall=total_demanded - avail_stock,
                            resolution_strategy=ResolutionStrategy.PRIORITY_FIRST,
                            resolution_status=ConflictStatus.PARTIALLY_RESOLVED,
                            officer_attention_required=True,
                            explanation=(
                                f"Prioritized higher-urgency requirements first ({sorted_competing[0].get('resource_type')}). "
                                f"Remaining stock partially distributed; lower-priority shortfall requires officer confirmation."
                            ),
                            alternative_options=[
                                "Accept priority-based ranking",
                                "Split inventory equally among competing units",
                                "Defer lower-priority demand",
                            ],
                        )
                        conflicts.append(conf)
                        affected_resources.append(res_name)
                        resolution_actions.append(
                            f"Resolved competition on '{res_name}' via PRIORITY_FIRST strategy."
                        )

            # ----------------------------------------------------
            # Check C: Geographic Suitability Mismatch
            # ----------------------------------------------------
            for alloc in working_allocations:
                dist_km = alloc.get("distance_km")
                if dist_km is not None and dist_km > 100.0:
                    conf_id = f"CNF-GEO-{uuid.uuid4().hex[:6].upper()}"
                    r_name = alloc.get("matched_resource_name") or str(alloc.get("resource_type"))
                    conf = DetectedConflict(
                        conflict_id=conf_id,
                        conflict_type=ConflictType.GEOGRAPHIC_MISMATCH,
                        severity=SeverityLevel.MEDIUM,
                        description=(
                            f"Matched depot '{r_name}' is located {dist_km:.1f} km away, "
                            f"exceeding standard 100 km rapid response transit radius."
                        ),
                        affected_need=str(alloc.get("resource_type")),
                        affected_resource=r_name,
                        detected_quantity=alloc.get("quantity_required"),
                        available_quantity=alloc.get("available_in_inventory"),
                        shortfall=None,
                        resolution_strategy=ResolutionStrategy.UNRESOLVED_ESCALATION,
                        resolution_status=ConflictStatus.ESCALATED,
                        officer_attention_required=True,
                        explanation=(
                            f"Depot transit distance ({dist_km:.1f} km) may introduce significant delivery delay. "
                            f"Escalated to Officer for route/transport approval."
                        ),
                        alternative_options=[
                            "Authorize long-range transport logistics",
                            "Query staging hubs in closer proximity",
                        ],
                    )
                    conflicts.append(conf)
                    affected_resources.append(r_name)
                    resolution_actions.append(f"Flagged geographic transit constraint ({dist_km:.1f} km) on {r_name}.")

            # ----------------------------------------------------
            # Check D: Shelter Capacity Shortfall
            # ----------------------------------------------------
            shl_sum = context.parameters.get("shelter_summary") if isinstance(context.parameters.get("shelter_summary"), dict) else {}
            shl_shortfall = float(context.parameters.get("shelter_shortfall") or shl_sum.get("total_shortfall") or 0.0)
            shl_req = float(shl_sum.get("affected_population") or 0.0)
            shl_avail = float(shl_sum.get("total_capacity_available") or 0.0)
            if shl_req <= 0.0 and shl_shortfall > 0.0:
                shl_req = shl_avail + shl_shortfall

            if shl_shortfall > 0:
                conf_id = f"CNF-SHL-{uuid.uuid4().hex[:6].upper()}"
                conf = DetectedConflict(
                    conflict_id=conf_id,
                    conflict_type=ConflictType.SHELTER_CAPACITY_CONFLICT,
                    severity=SeverityLevel.HIGH,
                    description=(
                        f"Emergency shelter capacity shortfall: {shl_avail:g} bed capacity available "
                        f"against requirement of {shl_req:g} evacuees ({shl_shortfall:g} bed shortfall)."
                    ),
                    affected_need="Emergency Shelter Beds",
                    affected_resource="Regional Shelter Network",
                    detected_quantity=shl_req,
                    available_quantity=shl_avail,
                    shortfall=shl_shortfall,
                    resolution_strategy=ResolutionStrategy.UNRESOLVED_ESCALATION,
                    resolution_status=ConflictStatus.ESCALATED,
                    officer_attention_required=True,
                    explanation=(
                        f"Emergency shelter capacity is insufficient. {shl_avail:g} bed capacity is currently available "
                        f"across regional shelters against an assessed need of {shl_req:g} evacuees, "
                        f"resulting in a {shl_shortfall:g} bed shortfall."
                    ),
                    alternative_options=["Authorize temporary encampment", "Request inter-district shelter aid"],
                )
                conflicts.append(conf)
                affected_needs.append("Emergency Shelter Beds")
                resolution_actions.append(f"Escalated shelter capacity shortfall of {int(shl_shortfall)} beds.")

            # ----------------------------------------------------
            # Check E: Healthcare / Medical Demand Conflict
            # ----------------------------------------------------
            hlt_sum = context.parameters.get("healthcare_summary") if isinstance(context.parameters.get("healthcare_summary"), dict) else {}
            med_shortfall = float(context.parameters.get("healthcare_shortfall") or hlt_sum.get("total_shortfall") or 0.0)
            med_req = float(hlt_sum.get("estimated_casualties") or 0.0)
            med_avail = float(hlt_sum.get("total_beds_available") or 0.0)
            if med_req <= 0.0 and med_shortfall > 0.0:
                med_req = med_avail + med_shortfall

            if med_shortfall > 0:
                conf_id = f"CNF-MED-{uuid.uuid4().hex[:6].upper()}"
                conf = DetectedConflict(
                    conflict_id=conf_id,
                    conflict_type=ConflictType.HEALTHCARE_TRANSPORT_MISMATCH,
                    severity=SeverityLevel.CRITICAL,
                    description=(
                        f"Medical bed capacity shortfall: {med_avail:g} emergency beds available "
                        f"against requirement of {med_req:g} casualties ({med_shortfall:g} patient shortfall)."
                    ),
                    affected_need="Emergency Hospital Beds / ICU",
                    affected_resource="Regional Hospital Network",
                    detected_quantity=med_req,
                    available_quantity=med_avail,
                    shortfall=med_shortfall,
                    resolution_strategy=ResolutionStrategy.UNRESOLVED_ESCALATION,
                    resolution_status=ConflictStatus.ESCALATED,
                    officer_attention_required=True,
                    explanation=(
                        f"Hospital capacity is insufficient for casualty demand. {med_avail:g} emergency beds "
                        f"are currently available in regional facilities against {med_req:g} casualties, "
                        f"resulting in a {med_shortfall:g} patient shortfall."
                    ),
                    alternative_options=["Deploy mobile field triage", "Airlift critical casualties to tertiary trauma centers"],
                )
                conflicts.append(conf)
                affected_needs.append("Emergency Hospital Beds / ICU")
                resolution_actions.append(f"Escalated medical bed deficit of {int(med_shortfall)} patients.")

            # ----------------------------------------------------
            # Check F: Volunteer Responder Shortfall
            # ----------------------------------------------------
            vol_sum = context.parameters.get("volunteer_summary") if isinstance(context.parameters.get("volunteer_summary"), dict) else {}
            vol_shortfall = float(context.parameters.get("volunteer_shortfall") or vol_sum.get("total_shortfall") or 0.0)
            vol_req = float(vol_sum.get("estimated_volunteers_needed") or vol_sum.get("volunteers_needed") or 0.0)
            vol_avail = float(
                vol_sum.get("total_volunteers_available")
                if vol_sum.get("total_volunteers_available") is not None
                else (
                    vol_sum.get("total_available")
                    if vol_sum.get("total_available") is not None
                    else (vol_sum.get("total_volunteers_assigned") or len(vol_sum.get("volunteers_recommended", [])) or 0.0)
                )
            )
            if vol_req <= 0.0 and vol_shortfall > 0.0:
                vol_req = vol_avail + vol_shortfall

            if vol_shortfall > 0:
                conf_id = f"CNF-VOL-{uuid.uuid4().hex[:6].upper()}"
                conf = DetectedConflict(
                    conflict_id=conf_id,
                    conflict_type=ConflictType.VOLUNTEER_AVAILABILITY_CONFLICT,
                    severity=SeverityLevel.MEDIUM,
                    description=(
                        f"Volunteer responder shortfall: {vol_avail:g} active volunteers available "
                        f"against requirement of {vol_req:g} personnel ({vol_shortfall:g} responder shortfall)."
                    ),
                    affected_need="Field Response Personnel",
                    affected_resource="Volunteer Network Registry",
                    detected_quantity=vol_req,
                    available_quantity=vol_avail,
                    shortfall=vol_shortfall,
                    resolution_strategy=ResolutionStrategy.UNRESOLVED_ESCALATION,
                    resolution_status=ConflictStatus.ESCALATED,
                    officer_attention_required=True,
                    explanation=(
                        f"Volunteer responder capacity is insufficient. {vol_avail:g} qualified active volunteers "
                        f"are currently available against {vol_req:g} required response assignments, "
                        f"resulting in a {vol_shortfall:g} responder shortfall."
                    ),
                    alternative_options=["Issue volunteer broadcast alert", "Mobilize civil defense personnel"],
                )
                conflicts.append(conf)
                affected_needs.append("Field Response Personnel")
                resolution_actions.append(f"Escalated volunteer shortfall of {int(vol_shortfall)} personnel.")

            # ----------------------------------------------------
            # Check G: Transport Fleet Shortfall
            # ----------------------------------------------------
            rot_sum = context.parameters.get("route_summary") if isinstance(context.parameters.get("route_summary"), dict) else {}
            trans_shortfall = float(context.parameters.get("transport_shortfall") or rot_sum.get("transport_shortfall") or 0.0)
            trans_req = float(
                rot_sum.get("total_routes_recommended")
                or rot_sum.get("routes_evaluated")
                or len(rot_sum.get("routes_recommended", []))
                or 0.0
            )
            trans_avail = float(
                rot_sum.get("total_transports_available")
                if rot_sum.get("total_transports_available") is not None
                else (
                    rot_sum.get("total_transports_recommended")
                    if rot_sum.get("total_transports_recommended") is not None
                    else (
                        rot_sum.get("total_available")
                        if rot_sum.get("total_available") is not None
                        else (rot_sum.get("total_vehicles_assigned") or len(rot_sum.get("transports_recommended", [])) or 0.0)
                    )
                )
            )
            if trans_req <= 0.0 and trans_shortfall > 0.0:
                trans_req = trans_avail + trans_shortfall

            if trans_shortfall > 0:
                conf_id = f"CNF-TRN-{uuid.uuid4().hex[:6].upper()}"
                conf = DetectedConflict(
                    conflict_id=conf_id,
                    conflict_type=ConflictType.INSUFFICIENT_QUANTITY,
                    severity=SeverityLevel.HIGH,
                    description=(
                        f"Fleet transport capacity shortfall: {trans_avail:g} vehicles available "
                        f"against requirement of {trans_req:g} transit routes ({trans_shortfall:g} vehicle shortfall)."
                    ),
                    affected_need="Fleet Transport Vehicles",
                    affected_resource="Emergency Vehicle Fleet",
                    detected_quantity=trans_req,
                    available_quantity=trans_avail,
                    shortfall=trans_shortfall,
                    resolution_strategy=ResolutionStrategy.UNRESOLVED_ESCALATION,
                    resolution_status=ConflictStatus.ESCALATED,
                    officer_attention_required=True,
                    explanation=(
                        f"Transport vehicle capacity is insufficient. {trans_avail:g} fleet vehicles "
                        f"are currently available against {trans_req:g} required transport routes, "
                        f"resulting in a {trans_shortfall:g} vehicle shortfall."
                    ),
                    alternative_options=["Mobilize auxiliary commercial transport", "Reallocate regional fleet"],
                )
                conflicts.append(conf)
                affected_needs.append("Fleet Transport Vehicles")
                affected_resources.append("Emergency Vehicle Fleet")
                resolution_actions.append(f"Escalated transport fleet shortfall of {int(trans_shortfall)} vehicles.")

            # ----------------------------------------------------
            # Check H: Route & Road Blockage Conflict
            # ----------------------------------------------------
            road_status = context.parameters.get("road_conditions", {}).get("status") if isinstance(context.parameters.get("road_conditions"), dict) else None
            if road_status == "BLOCKED":
                conf_id = f"CNF-ROT-{uuid.uuid4().hex[:6].upper()}"
                conf = DetectedConflict(
                    conflict_id=conf_id,
                    conflict_type=ConflictType.ROUTE_ROAD_BLOCKAGE,
                    severity=SeverityLevel.HIGH,
                    description="Primary transit corridor is blocked by debris/floodwaters.",
                    affected_need="Logistics & Evacuation Transit",
                    affected_resource="Arterial Road Network",
                    detected_quantity=1.0,
                    available_quantity=0.0,
                    shortfall=1.0,
                    resolution_strategy=ResolutionStrategy.ALTERNATIVE_RESOURCE,
                    resolution_status=ConflictStatus.PARTIALLY_RESOLVED,
                    officer_attention_required=True,
                    explanation="Primary corridor blocked; Route Transport Agent computed secondary arterial detour.",
                    alternative_options=["Approve secondary arterial detour", "Deploy road clearance engineering crew"],
                )
                conflicts.append(conf)
                affected_resources.append("Arterial Road Network")
                resolution_actions.append("Computed secondary arterial detour for blocked transit corridor.")

            # ----------------------------------------------------
            # 3. Build Summary Intelligence
            # ----------------------------------------------------
            resolved_count = sum(1 for c in conflicts if c.resolution_status in [ConflictStatus.RESOLVED, ConflictStatus.PARTIALLY_RESOLVED])
            unresolved_count = sum(1 for c in conflicts if c.resolution_status in [ConflictStatus.UNRESOLVED, ConflictStatus.ESCALATED])
            attention_required = any(c.officer_attention_required for c in conflicts)

            if len(conflicts) == 0:
                summary_explanation = "No coordination conflicts detected. All assessed emergency needs can be satisfied by current inventory."
                recommendation = "Deterministic conflict analysis complete: Zero resource or constraint conflicts detected."
                confidence = 0.98
                evidence.append("All requested resources successfully verified against active depot stock and distance constraints.")
            else:
                summary_explanation = (
                    f"Identified {len(conflicts)} coordination constraint(s): "
                    f"{resolved_count} addressed via deterministic strategies, "
                    f"{unresolved_count} requiring Emergency Officer attention."
                )
                recommendation = (
                    f"Conflict Resolution: {len(conflicts)} conflict(s) detected. "
                    f"{resolved_count} partially resolved; {unresolved_count} escalated for human review."
                )
                confidence = 0.90 if unresolved_count == 0 else 0.85
                evidence.append(f"Evaluated {len(raw_needs)} needs against {len(working_allocations)} matched allocations.")
                for act in resolution_actions:
                    evidence.append(act)

            summary = ConflictResolutionSummary(
                conflicts_detected=conflicts,
                conflicts_count=len(conflicts),
                resolved_conflicts=resolved_count,
                unresolved_conflicts=unresolved_count,
                resolution_actions=resolution_actions,
                affected_needs=list(dict.fromkeys(affected_needs)),
                affected_resources=list(dict.fromkeys(affected_resources)),
                shortages=shortages,
                officer_attention_required=attention_required,
                explanation=summary_explanation,
                confidence=confidence,
                generated_at=datetime.now(timezone.utc),
                agent_version="1.0.0",
            )

            return AgentResult(
                agent_name=self.name,
                run_id=run_id,
                status=AgentRunStatus.COMPLETED,
                recommendation=recommendation,
                structured_output=summary.model_dump(),
                confidence=confidence,
                evidence=evidence,
                warnings=warnings,
                constraints=constraints,
                generated_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.error(f"ConflictResolutionAgent exception: {e}", exc_info=True)
            fallback_conf = DetectedConflict(
                conflict_id=f"CNF-ERR-{uuid.uuid4().hex[:6].upper()}",
                conflict_type=ConflictType.UNKNOWN_CONFLICT,
                severity=SeverityLevel.HIGH,
                description=f"Automated conflict analysis encountered internal exception: {str(e)}",
                resolution_strategy=ResolutionStrategy.UNRESOLVED_ESCALATION,
                resolution_status=ConflictStatus.ESCALATED,
                officer_attention_required=True,
                explanation="Escalated directly to Emergency Officer for manual assessment.",
            )
            fallback_summary = ConflictResolutionSummary(
                conflicts_detected=[fallback_conf],
                conflicts_count=1,
                resolved_conflicts=0,
                unresolved_conflicts=1,
                resolution_actions=["Escalate directly to Emergency Officer."],
                officer_attention_required=True,
                explanation=f"Fallback conflict analysis: {str(e)}",
                confidence=0.5,
                generated_at=datetime.now(timezone.utc),
                agent_version="1.0.0",
            )
            return AgentResult(
                agent_name=self.name,
                run_id=run_id,
                status=AgentRunStatus.FALLBACK,
                recommendation="Conflict resolution agent executed in safe fallback mode.",
                structured_output=fallback_summary.model_dump(),
                confidence=0.5,
                evidence=["Safe fallback executed."],
                warnings=[f"Conflict analysis handled exception: {str(e)}"],
                constraints=constraints,
                generated_at=datetime.now(timezone.utc),
            )
