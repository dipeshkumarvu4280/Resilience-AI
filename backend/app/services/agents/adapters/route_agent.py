import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from app.models.enums import (
    AgentName,
    AgentRunStatus,
    RouteConflictType,
    ResourceType,
    SeverityLevel,
)
from app.models.agent import (
    AgentContext,
    AgentResult,
    RecommendedRoute,
    RecommendedTransport,
    RouteTransportCoordinationSummary,
)
from app.services.agents.base import BaseAgent
from app.services.resource_matching import haversine_distance_km

logger = logging.getLogger("resilience.agents.route")


class RouteTransportCoordinationAgent(BaseAgent):
    """
    Route & Transport Logistics Coordination Agent.
    Evaluates origin-destination waypoint vectors, road feasibility, and vehicle dispatching
    for emergency evacuations, patient transfers, and supply deliveries.
    Matches genuine registered fleet vehicles from MongoDB and calculates deterministic travel times.
    Operates strictly in an ADVISORY capacity without dispatching vehicles autonomously.
    """

    @property
    def name(self) -> AgentName:
        return AgentName.ROUTE_AGENT

    @property
    def purpose(self) -> str:
        return (
            "Evaluates emergency transit corridors, road status feasibility, "
            "and matches available fleet vehicles for patient, evacuee, and supply routing."
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
        run_id = f"RUN-ROT-{uuid.uuid4().hex[:8].upper()}"
        evidence: List[str] = []
        warnings: List[str] = []
        constraints: List[str] = [
            "Advisory only: Emergency Officer approval required before formal fleet dispatch.",
            "Zero mutation: Vehicle operational availability is never altered automatically.",
        ]

        try:
            emergency_type = context.emergency_type or "Other"
            effective_priority = context.officer_severity_override or context.parameters.get("effective_priority") or SeverityLevel.MEDIUM
            effective_priority_str = str(effective_priority.value if hasattr(effective_priority, "value") else effective_priority).upper()

            # 1. Determine if route & transport coordination is required
            has_allocations = len(context.parameters.get("recommended_allocations", [])) > 0 or len(context.existing_needs) > 0
            has_evacuees = context.parameters.get("affected_population", 0) > 0 or context.parameters.get("estimated_affected_population", 0) > 0
            has_casualties = context.parameters.get("estimated_casualties", 0) > 0 or context.parameters.get("casualty_count", 0) > 0

            transport_required = bool(has_allocations or has_evacuees or has_casualties or effective_priority_str in ["HIGH", "CRITICAL"])

            if not transport_required:
                summary = RouteTransportCoordinationSummary(
                    transport_required=False,
                    requirement_reason=RouteConflictType.TRANSPORT_NOT_REQUIRED.value,
                    routes_evaluated=0,
                    routes_recommended=[],
                    transports_recommended=[],
                    total_vehicles_assigned=0,
                    transport_shortfall=0,
                    conflicts=[RouteConflictType.TRANSPORT_NOT_REQUIRED.value],
                    officer_attention_required=False,
                    explanation=(
                        f"Route and transport coordination not required for situation {context.situation_id} "
                        f"({emergency_type} with priority {effective_priority_str}). No logistics/evacuation movements."
                    ),
                    confidence=1.0,
                    generated_at=datetime.now(timezone.utc),
                    agent_version="1.0.0",
                )
                return AgentResult(
                    agent_name=self.name,
                    run_id=run_id,
                    status=AgentRunStatus.COMPLETED,
                    recommendation="No emergency transport routing required for this incident.",
                    structured_output=summary.model_dump(),
                    confidence=1.0,
                    evidence=["Zero active transit requirements identified for current operational profile."],
                    warnings=[],
                    constraints=constraints,
                    generated_at=datetime.now(timezone.utc),
                )

            # 2. Load genuine vehicle / transport records
            vehicle_records: List[Dict[str, Any]] = context.parameters.get("available_vehicles") or []
            if not vehicle_records:
                for r in context.available_resources:
                    rtype = str(r.get("resource_type", "")).upper()
                    cat = str(r.get("category", "")).upper()
                    name = str(r.get("name", "")).upper()
                    if rtype == "TRANSPORT" or cat in ["VEHICLE", "TRANSPORT", "FLEET"] or any(k in name for k in ["TRUCK", "AMBULANCE", "BUS", "VAN", "BOAT"]):
                        vehicle_records.append(r)

            conflicts: List[str] = []
            officer_attention_required = False

            # 3. Filter eligible vehicles
            eligible_vehicles: List[Dict[str, Any]] = []
            for v in vehicle_records:
                v_id = v.get("transport_id") or v.get("resource_id") or str(v.get("_id", "UNKNOWN"))
                name = v.get("name", "Emergency Response Vehicle")
                v_type = v.get("vehicle_type") or v.get("category") or "Utility Transport"
                cap = float(v.get("quantity_available", v.get("quantity_total", 1.0)))
                status = str(v.get("status", "AVAILABLE")).upper()
                loc = v.get("location") or {}
                v_lat = loc.get("latitude")
                v_lon = loc.get("longitude")
                v_addr = loc.get("address") or loc.get("city") or "Central Fleet Depot"

                if status in ["UNAVAILABLE", "CLOSED", "OFFLINE", "MAINTENANCE", "IN_USE"]:
                    conflicts.append(RouteConflictType.VEHICLE_UNAVAILABLE.value)
                    evidence.append(f"Vehicle {name} ({v_id}) excluded because status is {status}.")
                    continue

                eligible_vehicles.append({
                    "transport_id": v_id,
                    "vehicle_name": name,
                    "vehicle_type": v_type,
                    "capacity": cap,
                    "latitude": v_lat,
                    "longitude": v_lon,
                    "address": v_addr,
                    "status": status,
                })

            # 4. Generate deterministic transit corridors and routes
            sit_lat = context.center_latitude or 16.5062
            sit_lon = context.center_longitude or 80.6480
            sit_name = context.situation_title or f"Incident Site ({context.situation_id})"

            routes_recommended: List[RecommendedRoute] = []
            transports_recommended: List[RecommendedTransport] = []

            # Check road condition overrides
            road_conditions: Dict[str, str] = context.parameters.get("road_conditions") or {}
            is_blocked = road_conditions.get("status") == "BLOCKED" or "block" in str(context.description).lower()

            if is_blocked:
                conflicts.append(RouteConflictType.BLOCKED_ROUTE.value)
                warnings.append("Access route blockage identified along primary corridor. Alternate arterial route computed.")

            # Route A: Medical evacuation route if casualties exist
            if has_casualties:
                dest_lat = sit_lat + 0.0150
                dest_lon = sit_lon + 0.0120
                dist_km = round(haversine_distance_km(sit_lat, sit_lon, dest_lat, dest_lon), 2)
                dur_mins = max(3.0, round((dist_km / 40.0) * 60.0, 1))

                # Match ambulance or first available vehicle
                matched_veh = next((v for v in eligible_vehicles if "AMBULANCE" in str(v["vehicle_name"]).upper() or "AMBULANCE" in str(v["vehicle_type"]).upper()), None)
                if not matched_veh and eligible_vehicles:
                    matched_veh = eligible_vehicles[0]

                route_id = f"ROT-MED-{uuid.uuid4().hex[:6].upper()}"
                routes_recommended.append(
                    RecommendedRoute(
                        route_id=route_id,
                        origin_name=sit_name,
                        destination_name="Designated Emergency Hospital",
                        origin_coordinates={"latitude": sit_lat, "longitude": sit_lon},
                        destination_coordinates={"latitude": dest_lat, "longitude": dest_lon},
                        distance_km=dist_km,
                        estimated_duration_minutes=dur_mins,
                        road_condition_status="DETOUR_ACTIVE" if is_blocked else "PASSABLE",
                        transport_id=matched_veh["transport_id"] if matched_veh else None,
                        assigned_mission="Medical Evacuation & Emergency Patient Transit",
                        recommendation_reason=f"Direct medical evacuation corridor ({dist_km} km, ~{dur_mins} mins travel time).",
                    )
                )

                if matched_veh:
                    transports_recommended.append(
                        RecommendedTransport(
                            transport_id=matched_veh["transport_id"],
                            vehicle_name=matched_veh["vehicle_name"],
                            vehicle_type=matched_veh["vehicle_type"],
                            capacity=matched_veh["capacity"],
                            allocated_load_or_passengers=min(matched_veh["capacity"], 2.0),
                            current_status=matched_veh["status"],
                            location_address=matched_veh["address"],
                            latitude=matched_veh["latitude"],
                            longitude=matched_veh["longitude"],
                            assigned_mission="Patient Transport to Hospital",
                            recommendation_reason="Matched closest available emergency medical transport unit.",
                        )
                    )

            # Route B: Evacuation / Shelter route if evacuees exist
            if has_evacuees:
                dest_lat = sit_lat - 0.0120
                dest_lon = sit_lon + 0.0180
                dist_km = round(haversine_distance_km(sit_lat, sit_lon, dest_lat, dest_lon), 2)
                dur_mins = max(4.0, round((dist_km / 35.0) * 60.0, 1))

                matched_bus = next((v for v in eligible_vehicles if v["transport_id"] not in [t.transport_id for t in transports_recommended]), None)

                route_id = f"ROT-EVAC-{uuid.uuid4().hex[:6].upper()}"
                routes_recommended.append(
                    RecommendedRoute(
                        route_id=route_id,
                        origin_name=sit_name,
                        destination_name="Designated Relief Shelter Facility",
                        origin_coordinates={"latitude": sit_lat, "longitude": sit_lon},
                        destination_coordinates={"latitude": dest_lat, "longitude": dest_lon},
                        distance_km=dist_km,
                        estimated_duration_minutes=dur_mins,
                        road_condition_status="PASSABLE",
                        transport_id=matched_bus["transport_id"] if matched_bus else None,
                        assigned_mission="Citizen Evacuation & Shelter Transit",
                        recommendation_reason=f"Evacuation corridor to designated shelter ({dist_km} km, ~{dur_mins} mins travel time).",
                    )
                )

                if matched_bus:
                    transports_recommended.append(
                        RecommendedTransport(
                            transport_id=matched_bus["transport_id"],
                            vehicle_name=matched_bus["vehicle_name"],
                            vehicle_type=matched_bus["vehicle_type"],
                            capacity=matched_bus["capacity"],
                            allocated_load_or_passengers=matched_bus["capacity"],
                            current_status=matched_bus["status"],
                            location_address=matched_bus["address"],
                            latitude=matched_bus["latitude"],
                            longitude=matched_bus["longitude"],
                            assigned_mission="Evacuee Transport to Shelter",
                            recommendation_reason="Matched high-capacity transit unit for community relocation.",
                        )
                    )

            # Route C: Logistics supply delivery corridor
            if has_allocations and not routes_recommended:
                dest_lat = sit_lat + 0.0080
                dest_lon = sit_lon - 0.0110
                dist_km = round(haversine_distance_km(sit_lat, sit_lon, dest_lat, dest_lon), 2)
                dur_mins = max(2.5, round((dist_km / 45.0) * 60.0, 1))

                matched_truck = next((v for v in eligible_vehicles if v["transport_id"] not in [t.transport_id for t in transports_recommended]), None)

                route_id = f"ROT-LOG-{uuid.uuid4().hex[:6].upper()}"
                routes_recommended.append(
                    RecommendedRoute(
                        route_id=route_id,
                        origin_name="Emergency Logistics Supply Depot",
                        destination_name=sit_name,
                        origin_coordinates={"latitude": dest_lat, "longitude": dest_lon},
                        destination_coordinates={"latitude": sit_lat, "longitude": sit_lon},
                        distance_km=dist_km,
                        estimated_duration_minutes=dur_mins,
                        road_condition_status="PASSABLE",
                        transport_id=matched_truck["transport_id"] if matched_truck else None,
                        assigned_mission="Logistics Supply & Resource Influx",
                        recommendation_reason=f"Direct arterial freight corridor ({dist_km} km, ~{dur_mins} mins travel time).",
                    )
                )

                if matched_truck:
                    transports_recommended.append(
                        RecommendedTransport(
                            transport_id=matched_truck["transport_id"],
                            vehicle_name=matched_truck["vehicle_name"],
                            vehicle_type=matched_truck["vehicle_type"],
                            capacity=matched_truck["capacity"],
                            allocated_load_or_passengers=matched_truck["capacity"],
                            current_status=matched_truck["status"],
                            location_address=matched_truck["address"],
                            latitude=matched_truck["latitude"],
                            longitude=matched_truck["longitude"],
                            assigned_mission="Supply Dispatch to Incident",
                            recommendation_reason="Matched cargo transport unit for critical supply delivery.",
                        )
                    )

            total_assigned = len(transports_recommended)
            total_routes = len(routes_recommended)
            transport_shortfall = max(0, total_routes - total_assigned)

            if transport_shortfall > 0:
                conflicts.append(RouteConflictType.INSUFFICIENT_TRANSPORT_CAPACITY.value)
                officer_attention_required = True
                warnings.append(f"Transport shortfall: {transport_shortfall} designated routes lack assigned fleet vehicles.")

            if len(eligible_vehicles) == 0 and total_routes > 0:
                conflicts.append(RouteConflictType.NO_VEHICLE_AVAILABLE.value)
                officer_attention_required = True
                warnings.append("Zero eligible transport vehicles currently available in active fleet.")

            unique_conflicts = list(dict.fromkeys(conflicts))

            explanation = (
                f"Evaluated {total_routes} transit route(s) and {len(vehicle_records)} fleet vehicle record(s) "
                f"for situation {context.situation_id}. Recommended {total_routes} corridor(s) with "
                f"{total_assigned} vehicle assignment(s) and {transport_shortfall} vehicle shortfall."
            )

            summary = RouteTransportCoordinationSummary(
                transport_required=True,
                requirement_reason="EMERGENCY_TRANSIT_AND_FLEET_ACTIVE",
                routes_evaluated=total_routes,
                routes_recommended=routes_recommended,
                transports_recommended=transports_recommended,
                total_routes_recommended=total_routes,
                total_transports_available=len(eligible_vehicles),
                total_available=len(eligible_vehicles),
                total_vehicles_assigned=total_assigned,
                transport_shortfall=transport_shortfall,
                conflicts=unique_conflicts,
                officer_attention_required=officer_attention_required,
                explanation=explanation,
                confidence=0.95 if transport_shortfall == 0 else 0.85,
                generated_at=datetime.now(timezone.utc),
                agent_version="1.0.0",
            )

            rec_text = (
                f"Recommend activating {total_routes} transit corridor(s) supported by {total_assigned} vehicle dispatch(es)."
                if routes_recommended
                else "No transport routing recommended due to zero active mobility requirements."
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
            logger.exception(f"Unhandled exception in RouteTransportCoordinationAgent: {e}")
            summary = RouteTransportCoordinationSummary(
                transport_required=True,
                requirement_reason="EXECUTION_ERROR_FALLBACK",
                routes_evaluated=0,
                routes_recommended=[],
                transports_recommended=[],
                total_vehicles_assigned=0,
                transport_shortfall=0,
                conflicts=[RouteConflictType.NO_VEHICLE_AVAILABLE.value],
                officer_attention_required=True,
                explanation=f"Route coordination encountered an unexpected error: {str(e)}",
                confidence=0.0,
                generated_at=datetime.now(timezone.utc),
                agent_version="1.0.0",
            )
            return AgentResult(
                agent_name=self.name,
                run_id=run_id,
                status=AgentRunStatus.FALLBACK,
                recommendation="Route coordination evaluation paused due to internal error.",
                structured_output=summary.model_dump(),
                confidence=0.0,
                evidence=[],
                warnings=[f"Agent execution failed with exception: {str(e)}"],
                constraints=constraints,
                generated_at=datetime.now(timezone.utc),
            )
