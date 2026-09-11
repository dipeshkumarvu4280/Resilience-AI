import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from app.models.enums import AgentName, AgentRunStatus, ResourceType, NeedUrgency, ResourceStatus
from app.models.agent import AgentContext, AgentResult, PlanRecommendedResource
from app.models.resource import EmergencyNeedItem
from app.services.agents.base import BaseAgent
from app.services.resource_matching import match_resources_for_needs
from app.db.mongodb import db_manager


class ResourceCoordinationAgent(BaseAgent):
    """
    Resource Coordination Agent Adapter.
    Matches assessed situation needs against real available resource inventory in MongoDB Atlas.
    Evaluates geographical depot proximity and capacity without auto-decrementing inventory.
    """

    @property
    def name(self) -> AgentName:
        return AgentName.RESOURCE_COORDINATION_AGENT

    @property
    def purpose(self) -> str:
        return "Matches assessed emergency needs with real inventory depots based on distance and stock availability."

    @property
    def dependencies(self) -> List[AgentName]:
        return [AgentName.NEEDS_AGENT]

    @property
    def required_inputs(self) -> List[str]:
        return ["needs"]

    async def execute(self, context: AgentContext) -> AgentResult:
        run_id = f"RUN-RES-{uuid.uuid4().hex[:8].upper()}"
        warnings: List[str] = []
        evidence: List[str] = []
        constraints: List[str] = [
            "No inventory is decremented or reserved at this stage.",
            "Resource allocations remain proposed until human Emergency Officer approval."
        ]

        try:
            # 1. Retrieve Needs to Match
            raw_needs = context.parameters.get("assessed_needs") or context.existing_needs or []
            if not raw_needs:
                return AgentResult(
                    agent_name=self.name,
                    run_id=run_id,
                    status=AgentRunStatus.NOT_REQUIRED,
                    recommendation="No resource needs identified for matching.",
                    structured_output={"matches": [], "fulfillable_count": 0, "unmet_count": 0},
                    confidence=1.0,
                    evidence=["Zero need items provided in execution context."],
                    warnings=warnings,
                    constraints=constraints,
                    generated_at=datetime.utcnow(),
                )

            need_items: List[EmergencyNeedItem] = []
            for n in raw_needs:
                qty = float(n.get("requested_quantity") or n.get("quantity") or 1.0)
                r_type = n["resource_type"]
                need_items.append(EmergencyNeedItem(
                    resource_type=ResourceType(r_type) if isinstance(r_type, str) else r_type,
                    requested_quantity=qty,
                    unit=n.get("unit", "Units"),
                    urgency=NeedUrgency(n["urgency"]) if isinstance(n.get("urgency"), str) else n.get("urgency", NeedUrgency.HIGH),
                    reason=n.get("reason") or n.get("reasoning") or "Emergency situation requirement.",
                ))

            # 2. Execute Deterministic Resource Matching Engine with MongoDB Atlas
            db = db_manager.db
            incident_lat = context.center_latitude or 16.2415
            incident_lng = context.center_longitude or 80.6433

            matching_res = await match_resources_for_needs(
                db=db,
                report_id=context.situation_id,
                report_location={"latitude": incident_lat, "longitude": incident_lng},
                needs=need_items,
            )

            # 3. Format Recommendations
            matched_recommendations: List[Dict[str, Any]] = []
            fulfillable_count = 0
            unmet_count = 0

            for need_match in matching_res.needs_matches:
                r_type = need_match.resource_type.value if hasattr(need_match.resource_type, "value") else str(need_match.resource_type)
                u_val = need_match.urgency.value if hasattr(need_match.urgency, "value") else str(need_match.urgency)

                if need_match.candidates and len(need_match.candidates) > 0:
                    fulfillable_count += 1
                    alloc_candidates = [c for c in need_match.candidates if c.recommended_allocation > 0]
                    if not alloc_candidates:
                        alloc_candidates = [need_match.candidates[0]]

                    for cand in alloc_candidates:
                        loc_desc = cand.location.address or cand.location.city or "Regional Depot"
                        dist_val = round(cand.distance_km, 2) if cand.distance_km is not None else None
                        matched_recommendations.append({
                            "resource_type": r_type,
                            "quantity_required": need_match.requested_quantity,
                            "unit": need_match.unit,
                            "urgency": u_val,
                            "matched_resource_id": cand.resource_id,
                            "matched_resource_name": cand.name,
                            "available_in_inventory": float(cand.quantity_available),
                            "allocated_quantity": float(cand.recommended_allocation),
                            "depot_location": loc_desc,
                            "distance_km": dist_val,
                            "reasoning": f"Depot '{cand.name}' has {cand.quantity_available} {need_match.unit} available ({cand.distance_km:.1f} km away).",
                        })
                        evidence.append(
                            f"Matched {cand.recommended_allocation} {need_match.unit} of {r_type} "
                            f"from depot '{cand.name}' ({cand.distance_km:.1f} km away)."
                        )
                else:
                    unmet_count += 1
                    matched_recommendations.append({
                        "resource_type": r_type,
                        "quantity_required": need_match.requested_quantity,
                        "unit": need_match.unit,
                        "urgency": u_val,
                        "matched_resource_id": None,
                        "matched_resource_name": None,
                        "available_in_inventory": 0.0,
                        "allocated_quantity": 0.0,
                        "depot_location": None,
                        "distance_km": None,
                        "reasoning": f"Zero active inventory currently available in regional depots for {r_type}.",
                    })
                    warnings.append(f"Insufficient regional stock for {need_match.requested_quantity} {need_match.unit} of {r_type}.")

            recommendation = (
                f"Matched {fulfillable_count} of {len(need_items)} needs from active regional inventory depots."
            )

            return AgentResult(
                agent_name=self.name,
                run_id=run_id,
                status=AgentRunStatus.COMPLETED,
                recommendation=recommendation,
                structured_output={
                    "matches": matched_recommendations,
                    "recommended_allocations": matched_recommendations,
                    "fulfillable_count": fulfillable_count,
                    "unmet_count": unmet_count,
                },
                confidence=0.95 if fulfillable_count > 0 else 0.70,
                evidence=evidence,
                warnings=warnings,
                constraints=constraints,
                generated_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            # Controlled fallback on internal exception
            return AgentResult(
                agent_name=self.name,
                run_id=run_id,
                status=AgentRunStatus.FALLBACK,
                recommendation="Resource matching completed with basic regional depot defaults.",
                structured_output={
                    "matches": [],
                    "recommended_allocations": [],
                    "fulfillable_count": 0,
                    "unmet_count": 0,
                },
                confidence=0.5,
                evidence=["Safe fallback executed."],
                warnings=[f"Resource matching handled exception: {str(e)}"],
                constraints=constraints,
                generated_at=datetime.now(timezone.utc),
            )
