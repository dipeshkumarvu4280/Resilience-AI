import logging
import asyncio
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.models.enums import EmergencyType, SeverityLevel, ReportPriority
from app.models.situation import (
    SituationAssessment,
    SituationCluster,
    generate_assessment_id,
)
from app.services.severity_engine import calculate_explainable_severity

logger = logging.getLogger("resilience.situation_assessment")


class RawAISituationAssessmentSchema(BaseModel):
    situation_summary: str = Field(..., min_length=10, max_length=1500)
    severity_score: float = Field(..., ge=0.0, le=10.0)
    severity_level: SeverityLevel
    estimated_affected_population: int = Field(..., ge=0)
    impact_radius_km: float = Field(..., ge=0.05, le=100.0)
    hazard_risk: str = Field(..., min_length=3, max_length=500)
    key_factors: List[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(..., ge=0.0, le=1.0)
    recommendations: List[str] = Field(default_factory=list, max_length=20)


def calculate_evidence_confidence(
    report_count: int,
    has_geocoded_address: bool,
    media_count: int,
    avg_description_len: int,
    officer_triaged: bool,
) -> float:
    """
    Calculate an evidence-based confidence metric (0.10 to 0.98).
    Represents evidentiary weight and consistency.
    """
    score = 0.50

    # Multi-report corroboration
    if report_count >= 5:
        score += 0.20
    elif report_count >= 2:
        score += 0.12
    elif report_count == 1:
        score += 0.02

    # Geocoding accuracy
    if has_geocoded_address:
        score += 0.08

    # Visual media evidence
    if media_count >= 2:
        score += 0.12
    elif media_count == 1:
        score += 0.06

    # Descriptive detail
    if avg_description_len > 150:
        score += 0.08
    elif avg_description_len > 60:
        score += 0.04
    else:
        score -= 0.05

    # Officer review confirmation
    if officer_triaged:
        score += 0.06

    return round(max(0.20, min(0.96, score)), 2)


def generate_deterministic_situation_assessment(
    situation: SituationCluster,
    reports: List[Dict[str, Any]],
) -> SituationAssessment:
    """
    High-reliability, deterministic situation assessment synthesis engine.
    Used when AI is offline, unconfigured, or as a baseline fallback.
    """
    descriptions = [r.get("description", "") for r in reports]
    priorities = [r.get("priority") for r in reports if r.get("priority")]
    media_count = sum(len(r.get("media", [])) for r in reports)
    rep_count = len(reports)
    
    score, level, key_factors = calculate_explainable_severity(
        emergency_type=situation.emergency_type.value,
        descriptions=descriptions,
        report_count=rep_count,
        officer_priorities=priorities,
        media_count=media_count,
    )

    # Heuristic population estimation based on impact radius and urban/rural zone
    zone_str = situation.center_location.zone_or_district or situation.center_location.city or ""
    is_dense_urban = any(k in zone_str.lower() for k in ["city", "sector", "market", "nagar", "colony", "ward"])
    density_per_sq_km = 450 if is_dense_urban else 120
    
    radius_km = situation.impact_zone.radius_km
    area_sq_km = 3.14159 * (radius_km ** 2)
    est_population = int(min(50000, max(15, area_sq_km * density_per_sq_km * 0.25)))

    # Hazard risk categorization
    et = situation.emergency_type.value
    combined_desc = " ".join(descriptions).lower()
    
    if "Flood" in et or "water" in combined_desc:
        hazard_risk = "Inundation, access route submersion, drinking water contamination, structural instability."
        recommendations = [
            "Deploy swift water rescue boats and flotation devices to low-lying sectors.",
            "Establish potable water distribution points and hygiene emergency kits.",
            "Issue immediate evacuation warnings to ground-floor residences in downstream flow path.",
        ]
    elif "Fire" in et or "smoke" in combined_desc:
        hazard_risk = "Rapid fire propagation, structural roof collapse, toxic smoke inhalation."
        recommendations = [
            "Establish safe perimeter buffer around fire zone; isolate adjacent electrical grids.",
            "Deploy specialized respiratory apparatus and burn trauma medical kits.",
            "Coordinate perimeter evacuation with local police and traffic control.",
        ]
    elif "Building Collapse" in et or "trapped" in combined_desc or "Landslide" in et:
        hazard_risk = "Secondary structural collapse, trapped victims under heavy debris, utility line ruptures."
        recommendations = [
            "Dispatch search-and-rescue extraction units equipped with hydraulic spreaders and acoustic sensors.",
            "Mobilize emergency trauma stabilization teams and transport stretchers.",
            "Secure surrounding perimeter against vibration and secondary structural shifts.",
        ]
    elif "Medical" in et or "injury" in combined_desc or "casualt" in combined_desc:
        hazard_risk = "Acute patient deterioration, triage capacity overload, transport delay."
        recommendations = [
            "Dispatch ALS ambulances with emergency paramedic personnel immediately.",
            "Alert regional emergency triage center for incoming casualties.",
            "Secure clear transit corridor for medical transport vehicles.",
        ]
    else:
        hazard_risk = f"On-ground emergency containment and situational monitoring for {et}."
        recommendations = [
            "Maintain continuous on-scene communications and observer monitoring.",
            "Prepare contingency logistics support for rapid deployment.",
        ]

    # Calculate evidence confidence
    has_geo = bool(situation.center_location.address or situation.center_location.city)
    avg_len = int(sum(len(d) for d in descriptions) / max(1, len(descriptions)))
    officer_triaged = any(p in [ReportPriority.CRITICAL.value, ReportPriority.HIGH.value] for p in priorities)
    
    conf = calculate_evidence_confidence(
        report_count=rep_count,
        has_geocoded_address=has_geo,
        media_count=media_count,
        avg_description_len=avg_len,
        officer_triaged=officer_triaged,
    )

    location_name = situation.center_location.address or situation.center_location.zone_or_district or f"({situation.center_location.latitude:.4f}, {situation.center_location.longitude:.4f})"
    
    summary = (
        f"Active {et} emergency situation encompassing {rep_count} corroborating citizen report(s) "
        f"in the vicinity of {location_name}. Estimated impact perimeter spans ~{radius_km:.1f} km "
        f"with an estimated affected population of ~{est_population:,} persons. "
        f"Severity is classified as {level.value} (Score: {score:.1f}/10.0)."
    )

    now = datetime.now(timezone.utc)
    return SituationAssessment(
        assessment_id=generate_assessment_id(),
        situation_id=situation.situation_id,
        severity_score=score,
        severity_level=level,
        estimated_affected_population=est_population,
        impact_radius_km=radius_km,
        hazard_risk=hazard_risk,
        key_factors=key_factors,
        situation_summary=summary,
        confidence=conf,
        recommendations=recommendations,
        is_ai_generated=False,
        ai_provider="deterministic-heuristic-engine",
        generated_by="Deterministic Emergency Intelligence Engine",
        created_at=now,
        updated_at=now,
    )


async def generate_situation_assessment(
    situation: SituationCluster,
    reports: List[Dict[str, Any]],
) -> SituationAssessment:
    """
    Main entrypoint for generating situation assessment.
    Attempts Gemini/LLM AI analysis if available; falls back smoothly to deterministic engine.
    Always validated with Pydantic.
    """
    # 1. Deterministic baseline
    deterministic_assessment = generate_deterministic_situation_assessment(situation, reports)

    # 2. If Gemini is available, attempt AI enrichment with strict timeout
    from app.services.gemini_service import GeminiIntelligenceService
    client = GeminiIntelligenceService._get_client()
    if client:
        try:
            from google.genai import types
            
            reports_context = []
            for idx, r in enumerate(reports, 1):
                reports_context.append(
                    f"Report #{idx} [ID: {r.get('report_id')}]: {r.get('description', '')} "
                    f"(Location: {r.get('location', {}).get('address', 'Unknown')}, "
                    f"Priority: {r.get('priority', 'UNASSESSED')})"
                )
                
            prompt = f"""
You are an expert Emergency Response Intelligence Analyst. Analyze this real-world emergency situation cluster and provide structured assessment.

SITUATION METADATA:
- Emergency Type: {situation.emergency_type.value}
- Report Count: {len(reports)}
- Location Center: ({situation.center_location.latitude}, {situation.center_location.longitude}) - {situation.center_location.address or 'Area'}
- Estimated Radius: {situation.impact_zone.radius_km} km
- Baseline Severity Score: {deterministic_assessment.severity_score}
- Baseline Severity Level: {deterministic_assessment.severity_level.value}

REPORTS CONTENT:
{chr(10).join(reports_context)}

Respond ONLY with a valid JSON object matching this schema:
{{
  "situation_summary": "Comprehensive 2-3 sentence situational summary",
  "severity_score": {deterministic_assessment.severity_score},
  "severity_level": "{deterministic_assessment.severity_level.value}",
  "estimated_affected_population": {deterministic_assessment.estimated_affected_population},
  "impact_radius_km": {deterministic_assessment.impact_radius_km},
  "hazard_risk": "Specific on-ground hazard propagation risks",
  "key_factors": ["Factor 1", "Factor 2", "Factor 3"],
  "confidence": {deterministic_assessment.confidence},
  "recommendations": ["Recommendation 1", "Recommendation 2", "Recommendation 3"]
}}
"""

            loop = asyncio.get_running_loop()
            model_name = settings.GEMINI_MODEL or "gemini-2.5-flash"
            
            async def call_ai():
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        response_mime_type="application/json",
                    ),
                )
                return response.text

            raw_text = await asyncio.wait_for(loop.run_in_executor(None, call_ai), timeout=settings.SITUATION_ASSESSMENT_TIMEOUT_SECONDS)
            
            # Clean and validate LLM output
            cleaned_json = json.loads(raw_text)
            validated_ai_output = RawAISituationAssessmentSchema(**cleaned_json)
            
            now = datetime.now(timezone.utc)
            return SituationAssessment(
                assessment_id=generate_assessment_id(),
                situation_id=situation.situation_id,
                severity_score=round(validated_ai_output.severity_score, 1),
                severity_level=validated_ai_output.severity_level,
                estimated_affected_population=validated_ai_output.estimated_affected_population,
                impact_radius_km=round(validated_ai_output.impact_radius_km, 2),
                hazard_risk=validated_ai_output.hazard_risk,
                key_factors=validated_ai_output.key_factors or deterministic_assessment.key_factors,
                situation_summary=validated_ai_output.situation_summary,
                confidence=round(validated_ai_output.confidence, 2),
                recommendations=validated_ai_output.recommendations or deterministic_assessment.recommendations,
                is_ai_generated=True,
                ai_provider="google-gemini-2.5-flash",
                generated_by="Gemini Situation Intelligence Agent",
                created_at=now,
                updated_at=now,
            )

        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"AI situation assessment failed or timed out ({e}). Falling back to deterministic engine.")
            return deterministic_assessment

    return deterministic_assessment
