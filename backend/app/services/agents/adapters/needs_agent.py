import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from app.models.enums import AgentName, AgentRunStatus, NeedUrgency, ResourceType
from app.models.agent import AgentContext, AgentResult
from app.services.agents.base import BaseAgent
from app.services.ai_coordinator import generate_heuristic_ai_needs_suggestions


class NeedsAgent(BaseAgent):
    """
    Needs Agent Adapter.
    Analyzes emergency incident type, situation summary, and spatial context to recommend
    structured emergency supplies, rescue gear, and medical provisions.
    """

    @property
    def name(self) -> AgentName:
        return AgentName.NEEDS_AGENT

    @property
    def purpose(self) -> str:
        return "Determines emergency supply and equipment requirements based on incident characteristics."

    @property
    def required_inputs(self) -> List[str]:
        return ["emergency_type", "description"]

    async def execute(self, context: AgentContext) -> AgentResult:
        run_id = f"RUN-NDS-{uuid.uuid4().hex[:8].upper()}"
        warnings: List[str] = []
        evidence: List[str] = []
        constraints: List[str] = [
            "All suggested quantities are advisory estimates requiring human Emergency Officer confirmation."
        ]

        try:
            # 1. If explicit needs are already recorded in context, prioritize them as authoritative
            if context.existing_needs and len(context.existing_needs) > 0:
                authoritative_needs: List[Dict[str, Any]] = []
                covered_resource_types = set()

                for item in context.existing_needs:
                    item_dict = dict(item) if isinstance(item, dict) else item.model_dump()
                    r_type = item_dict.get("resource_type")
                    r_type_val = r_type.value if hasattr(r_type, "value") else str(r_type)
                    qty = float(item_dict.get("requested_quantity") or item_dict.get("quantity") or 1.0)
                    u_val = item_dict.get("urgency", NeedUrgency.HIGH)
                    urgency_str = u_val.value if hasattr(u_val, "value") else str(u_val)

                    normalized_need = {
                        "resource_type": r_type_val,
                        "quantity": qty,
                        "requested_quantity": qty,
                        "unit": item_dict.get("unit", "Units"),
                        "urgency": urgency_str,
                        "reasoning": item_dict.get("reasoning") or item_dict.get("reason") or "Officer-assessed operational requirement.",
                        "confidence": float(item_dict.get("confidence", 1.0)),
                        "source": item_dict.get("source", "OFFICER_NEEDS_ASSESSMENT"),
                        "officer_assessed": item_dict.get("officer_assessed", True),
                        "ai_inferred": item_dict.get("ai_inferred", False),
                    }
                    authoritative_needs.append(normalized_need)
                    covered_resource_types.add(r_type_val.upper())
                    evidence.append(f"Authoritative Requirement: {qty:g} {normalized_need['unit']} of {r_type_val} ({urgency_str}).")

                # Check heuristic engine for any missing critical categories not yet assessed by officer
                advisory_suggestions = generate_heuristic_ai_needs_suggestions(
                    emergency_type=context.emergency_type,
                    description=context.description,
                    location_summary=context.location_summary,
                )
                for s in advisory_suggestions:
                    s_type = s.resource_type.value if hasattr(s.resource_type, "value") else str(s.resource_type)
                    if s_type.upper() not in covered_resource_types:
                        # Append strictly as an advisory AI-inferred suggestion
                        authoritative_needs.append({
                            "resource_type": s_type,
                            "quantity": s.suggested_quantity,
                            "requested_quantity": s.suggested_quantity,
                            "unit": s.unit,
                            "urgency": s.urgency.value if hasattr(s.urgency, "value") else str(s.urgency),
                            "reasoning": f"[AI Advisory] {s.reasoning}",
                            "confidence": s.confidence,
                            "source": "AI_INFERRED_ADVISORY",
                            "officer_assessed": False,
                            "ai_inferred": True,
                        })
                        evidence.append(f"Advisory Suggestion: {s.suggested_quantity} {s.unit} of {s_type} (AI Recommended).")

                recommendation = f"Consolidated {len(authoritative_needs)} need items ({len(context.existing_needs)} Officer Assessed, {len(authoritative_needs) - len(context.existing_needs)} Advisory Suggestions)."

                return AgentResult(
                    agent_name=self.name,
                    run_id=run_id,
                    status=AgentRunStatus.COMPLETED,
                    recommendation=recommendation,
                    structured_output={
                        "needs": authoritative_needs,
                        "need_count": len(authoritative_needs),
                        "source": "OFFICER_NEEDS_ASSESSMENT",
                    },
                    confidence=0.98,
                    evidence=evidence,
                    warnings=warnings,
                    constraints=constraints,
                    generated_at=datetime.now(timezone.utc),
                )

            # 2. Generate expert heuristic needs suggestions if no officer assessment exists yet
            suggestions = generate_heuristic_ai_needs_suggestions(
                emergency_type=context.emergency_type,
                description=context.description,
                location_summary=context.location_summary,
            )

            needs_data: List[Dict[str, Any]] = []
            for s in suggestions:
                r_type_str = s.resource_type.value if hasattr(s.resource_type, "value") else str(s.resource_type)
                u_str = s.urgency.value if hasattr(s.urgency, "value") else str(s.urgency)
                needs_data.append({
                    "resource_type": r_type_str,
                    "quantity": s.suggested_quantity,
                    "requested_quantity": s.suggested_quantity,
                    "unit": s.unit,
                    "urgency": u_str,
                    "reasoning": s.reasoning,
                    "confidence": s.confidence,
                    "source": "HEURISTIC_NEEDS_ENGINE",
                    "officer_assessed": False,
                    "ai_inferred": True,
                })
                evidence.append(f"Recommended {s.suggested_quantity} {s.unit} of {r_type_str} ({u_str}).")

            # Check if LLM extracted additional specific needs from citizen text (e.g. boats, baby food)
            llm_extraction = context.parameters.get("llm_extraction") if context.parameters else None
            if llm_extraction and isinstance(llm_extraction, dict):
                reported_needs = llm_extraction.get("reported_needs") or []
                for rn in reported_needs:
                    if isinstance(rn, dict) and rn.get("need_type"):
                        evidence.append(f"Citizen Observation Reported Need: {rn.get('need_type')} (Urgency: {rn.get('urgency', 'MEDIUM')}).")

            recommendation = f"Generated {len(needs_data)} emergency relief supply suggestions tailored to {context.emergency_type}."

            return AgentResult(
                agent_name=self.name,
                run_id=run_id,
                status=AgentRunStatus.COMPLETED,
                recommendation=recommendation,
                structured_output={
                    "needs": needs_data,
                    "need_count": len(needs_data),
                    "source": "HEURISTIC_NEEDS_ENGINE",
                },
                confidence=0.90 if len(needs_data) > 0 else 0.70,
                evidence=evidence,
                warnings=warnings,
                constraints=constraints,
                generated_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            # Controlled fallback on internal exception
            fallback_needs = [
                {
                    "resource_type": ResourceType.FIRST_AID.value,
                    "quantity": 10.0,
                    "unit": "Standard Kits",
                    "urgency": NeedUrgency.HIGH.value,
                    "reasoning": "Standard emergency medical first aid kit allocation.",
                    "confidence": 0.6,
                },
                {
                    "resource_type": ResourceType.WATER.value,
                    "quantity": 100.0,
                    "unit": "Litres",
                    "urgency": NeedUrgency.HIGH.value,
                    "reasoning": "Standard initial hydration relief stock.",
                    "confidence": 0.6,
                }
            ]
            return AgentResult(
                agent_name=self.name,
                run_id=run_id,
                status=AgentRunStatus.FALLBACK,
                recommendation="Fallback needs generated using default emergency response kit.",
                structured_output={
                    "needs": fallback_needs,
                    "need_count": len(fallback_needs),
                    "source": "SAFETY_FALLBACK_DEFAULT",
                },
                confidence=0.5,
                evidence=["Safe fallback executed."],
                warnings=[f"Needs assessment handled exception: {str(e)}"],
                constraints=constraints,
                generated_at=datetime.now(timezone.utc),
            )
