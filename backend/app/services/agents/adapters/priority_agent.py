import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.models.enums import AgentName, AgentRunStatus, SeverityLevel, HazardCategory
from app.models.agent import AgentContext, AgentResult
from app.services.agents.base import BaseAgent
from app.services.severity_engine import calculate_explainable_severity


class PriorityAgent(BaseAgent):
    """
    Evidence-Aware Priority Agent Adapter.
    
    ARCHITECTURE PRINCIPLES:
    - Assesses incident priority and situational urgency by synthesizing:
      1. Deterministic emergency severity calculations
      2. Multimodal structured visual evidence (Gemini Vision)
      3. Text-to-Image factual claim consistency
      4. Cryptographic and geo-temporal evidence trust
      5. Multi-source corroboration and conflict signals
    - Highest-Impact Safety Rule: Visual absence of a hazard does NOT delete or erase
      unobserved citizen claims (e.g., trapped persons or vulnerable groups).
    - AUTHORITATIVE OFFICER OVERRIDE: Human Emergency Officer decisions are 100% authoritative
      and never overridden by automated heuristics or AI models.
    """

    @property
    def name(self) -> AgentName:
        return AgentName.PRIORITY_AGENT

    @property
    def purpose(self) -> str:
        return "Evaluates situational severity, multimodal visual evidence, and hazard categories while strictly preserving officer authority."

    @property
    def required_inputs(self) -> List[str]:
        return ["emergency_type", "description"]

    async def execute(self, context: AgentContext) -> AgentResult:
        run_id = f"RUN-PRI-{uuid.uuid4().hex[:8].upper()}"
        warnings: List[str] = []
        evidence: List[str] = []
        constraints: List[str] = []
        evidence_factors: List[str] = []
        unverified_claims: List[str] = []
        uncertainties: List[str] = []

        try:
            # 1. Authoritative Officer Severity Override Check
            if context.officer_severity_override:
                effective_severity = context.officer_severity_override
                score = 10.0 if effective_severity == SeverityLevel.CRITICAL else (
                    8.0 if effective_severity == SeverityLevel.HIGH else (
                        5.0 if effective_severity == SeverityLevel.MEDIUM else 2.5
                    )
                )
                evidence.append(f"Authoritative human Emergency Officer override applied: {effective_severity.value}")
                evidence_factors.append(f"Officer designated priority as {effective_severity.value}")
                recommendation = f"Incident priority classified as {effective_severity.value} via Emergency Officer override."
                
                return AgentResult(
                    agent_name=self.name,
                    run_id=run_id,
                    status=AgentRunStatus.COMPLETED,
                    recommendation=recommendation,
                    structured_output={
                        "severity_level": effective_severity.value,
                        "severity_score": score,
                        "hazard_category": self._infer_hazard_category(context.emergency_type, context.description).value,
                        "is_officer_override": True,
                        "effective_priority": effective_severity.value,
                        "evidence_aware": False,
                        "evidence_factors": evidence_factors,
                        "unverified_claims": [],
                        "uncertainties": [],
                    },
                    confidence=1.0,
                    evidence=evidence,
                    warnings=warnings,
                    constraints=["Officer severity override must not be modified by automated heuristic loops."],
                    generated_at=datetime.now(timezone.utc),
                )

            # 2. Deterministic Baseline Severity Calculation
            severity_score, severity_level, key_factors = calculate_explainable_severity(
                emergency_type=context.emergency_type,
                descriptions=[context.description],
                report_count=context.report_count,
            )

            confidence = 0.95 if context.report_count >= 2 else 0.85
            hazard_cat = self._infer_hazard_category(context.emergency_type, context.description)

            evidence.append(f"Fused report volume: {context.report_count} incident reports.")
            evidence.append(f"Deterministic baseline severity score: {severity_score:.1f}/10 ({severity_level.value}).")
            for factor in key_factors:
                evidence.append(factor)
                evidence_factors.append(factor)

            # 3. Process LLM Text Extraction (if present)
            params = context.parameters or {}
            llm_extraction = params.get("llm_extraction")
            if isinstance(llm_extraction, dict):
                vulnerable_groups = llm_extraction.get("vulnerable_groups") or []
                for vg in vulnerable_groups:
                    if isinstance(vg, dict) and vg.get("group_type"):
                        cnt = vg.get("estimated_count")
                        cnt_str = f" ({cnt} reported)" if cnt else ""
                        msg = f"Vulnerable population indicator reported in text: {vg.get('group_type')}{cnt_str}"
                        evidence.append(msg)
                        evidence_factors.append(msg)

            # 4. Multimodal Structured Visual Evidence Integration
            visual_evidence_present = False
            consistency_label = "NOT_EVALUATED"

            visual_doc = params.get("visual_evidence")
            # Also check list of member visual evidences if available
            member_visuals = params.get("member_visual_evidence") or []
            if not visual_doc and member_visuals and len(member_visuals) > 0:
                visual_doc = member_visuals[0]

            if isinstance(visual_doc, dict) and visual_doc.get("status") == "SUCCESS":
                visual_evidence_present = True
                hazard_type_val = visual_doc.get("hazard_type", "UNKNOWN")
                consistency_label = visual_doc.get("text_image_consistency", "INCONCLUSIVE")
                visible_impacts = visual_doc.get("visible_impacts") or []
                claim_evals = visual_doc.get("claim_evaluations") or []
                infra_conds = visual_doc.get("infrastructure_conditions") or []
                vis_uncertainties = visual_doc.get("uncertainties") or []

                evidence.append(f"Visual Evidence Analysis: {hazard_type_val} (Consistency: {consistency_label}).")
                evidence_factors.append(f"Live camera photo shows observable {hazard_type_val} conditions.")

                # A. Evaluate specific claim consistency
                for claim in claim_evals:
                    if isinstance(claim, dict):
                        c_text = claim.get("claim_text", "")
                        c_status = claim.get("status", "")
                        c_obs = claim.get("visual_observation", "")

                        if c_status == "SUPPORTED":
                            evidence_factors.append(f"Claim visually confirmed: \"{c_text}\" ({c_obs})")
                        elif c_status == "NOT_OBSERVABLE":
                            unverified_claims.append(f"Claim \"{c_text}\" not observable in captured frame ({c_obs})")
                        elif c_status == "CONTRADICTED":
                            unverified_claims.append(f"Visual inconsistency on claim \"{c_text}\": {c_obs}")
                            warnings.append(f"Visual evidence contradicts claim: \"{c_text}\"")

                # B. Evaluate infrastructure & access conditions
                for infra in infra_conds:
                    if isinstance(infra, dict):
                        itype = infra.get("infrastructure_type")
                        cond = infra.get("condition")
                        is_blocked = infra.get("is_access_blocked", False)
                        if is_blocked or cond in ["SUBMERGED", "COLLAPSED", "BLOCKED", "DAMAGED"]:
                            evidence_factors.append(f"Infrastructure {itype} visibly {cond} (Access Blocked: {is_blocked})")
                            # If severe infrastructure blockage is confirmed, adjust severity weight conservatively
                            if is_blocked and severity_score < 7.5:
                                severity_score = min(8.5, severity_score + 1.0)
                                if severity_score >= 8.0:
                                    severity_level = SeverityLevel.HIGH

                # C. Record visual impacts & uncertainties
                for imp in visible_impacts:
                    evidence_factors.append(f"Visual impact observable: {imp}")

                for unc in vis_uncertainties:
                    uncertainties.append(unc)
            elif isinstance(visual_doc, dict) and visual_doc.get("status") in ["TEMPORARILY_UNAVAILABLE", "UNAVAILABLE"]:
                consistency_label = "UNAVAILABLE"
                visual_evidence_present = False

            # 5. Process Evidence Trust & Geo-Temporal Verification (Phase A)
            ev_verification = params.get("evidence_verification")
            if isinstance(ev_verification, dict):
                loc_match = ev_verification.get("location_match_state")
                freshness = ev_verification.get("evidence_freshness")
                has_photo = ev_verification.get("has_live_photo", False)
                if loc_match in ["MATCH", "NEAR_MATCH"]:
                    evidence_factors.append("Evidence geolocation matches citizen report location.")
                elif loc_match == "MISMATCH":
                    warnings.append("Evidence coordinates show moderate spatial discrepancy with report.")
                if freshness == "FRESH":
                    evidence_factors.append("Evidence capture timestamp is fresh (captured < 30m).")
                elif freshness == "STALE":
                    warnings.append("Evidence was captured > 30m before intake.")

            # 6. Highest-Impact Reconciliation Logic
            # If critical life-safety claims were reported (e.g. trapped/vulnerable) but not seen on camera,
            # we PRESERVE them under the Highest-Impact safety rule.
            if unverified_claims:
                evidence.append(f"Unverified claims preserved under safety rule: {len(unverified_claims)} items.")

            # Construct explainable recommendation summary
            factor_summary = "; ".join(evidence_factors[:4]) if evidence_factors else "Standard impact indicators"
            recommendation = (
                f"Situation classified as {severity_level.value} priority ({severity_score:.1f}/10). "
                f"Key factors: {factor_summary}."
            )

            return AgentResult(
                agent_name=self.name,
                run_id=run_id,
                status=AgentRunStatus.COMPLETED,
                recommendation=recommendation,
                structured_output={
                    "severity_level": severity_level.value,
                    "severity_score": severity_score,
                    "hazard_category": hazard_cat.value,
                    "is_officer_override": False,
                    "effective_priority": severity_level.value,
                    "evidence_aware": visual_evidence_present,
                    "text_image_consistency": consistency_label,
                    "evidence_factors": evidence_factors,
                    "unverified_claims": unverified_claims,
                    "uncertainties": uncertainties,
                },
                confidence=confidence,
                evidence=evidence,
                warnings=warnings,
                constraints=constraints,
                generated_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            # Controlled fallback on internal exception
            fallback_sev = SeverityLevel.MEDIUM
            return AgentResult(
                agent_name=self.name,
                run_id=run_id,
                status=AgentRunStatus.FALLBACK,
                recommendation=f"Fallback priority assessment: {fallback_sev.value} (heuristic engine exception handled).",
                structured_output={
                    "severity_level": fallback_sev.value,
                    "severity_score": 5.0,
                    "hazard_category": HazardCategory.GENERAL_SAFETY.value,
                    "is_officer_override": False,
                    "effective_priority": fallback_sev.value,
                    "evidence_aware": False,
                    "evidence_factors": ["Safe fallback triggered."],
                    "unverified_claims": [],
                    "uncertainties": [f"Exception: {str(e)}"],
                },
                confidence=0.5,
                evidence=["Safe fallback triggered."],
                warnings=[f"Priority assessment handled exception: {str(e)}"],
                constraints=constraints,
                generated_at=datetime.now(timezone.utc),
            )

    def _infer_hazard_category(self, emergency_type: str, description: str) -> HazardCategory:
        text = f"{emergency_type} {description}".lower()
        if "fire" in text or "smoke" in text or "burn" in text:
            return HazardCategory.FIRE_EXPANSION
        if "flood" in text or "water" in text or "submerged" in text:
            return HazardCategory.FLOODING_WATER_LEVEL
        if "collapse" in text or "rubble" in text or "debris" in text or "landslide" in text:
            return HazardCategory.STRUCTURAL_COLLAPSE
        if "trapped" in text or "casualty" in text or "injured" in text:
            return HazardCategory.CASUALTIES_TRAPPED
        if "chemical" in text or "gas" in text or "leak" in text:
            return HazardCategory.HAZARDOUS_MATERIALS
        if "power" in text or "electric" in text or "grid" in text:
            return HazardCategory.POWER_COMM_FAILURE
        if "storm" in text or "cyclone" in text or "wind" in text:
            return HazardCategory.WEATHER_ESCALATION
        return HazardCategory.GENERAL_SAFETY
