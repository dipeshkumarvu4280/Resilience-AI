import re
from typing import List, Dict, Tuple, Optional
from app.models.enums import EmergencyType, SeverityLevel, ReportPriority

# Centralized base severity weights per emergency type (scale 1.0 to 10.0)
BASE_EMERGENCY_SEVERITY: Dict[str, float] = {
    EmergencyType.BUILDING_COLLAPSE.value: 7.5,
    EmergencyType.CYCLONE_STORM.value: 7.0,
    EmergencyType.FLOOD.value: 6.5,
    EmergencyType.FIRE.value: 6.5,
    EmergencyType.LANDSLIDE.value: 6.5,
    EmergencyType.MISSING_TRAPPED.value: 6.0,
    EmergencyType.MEDICAL_EMERGENCY.value: 5.0,
    EmergencyType.ROAD_ACCIDENT.value: 4.5,
    EmergencyType.OTHER.value: 3.5,
}

# Critical situational keywords and their explainable severity weights
SITUATIONAL_INDICATORS: List[Tuple[str, float, str]] = [
    (r"\b(trapped|buried|under rubble|collapsed|crush)\b", 2.0, "Trapped or buried victims detected in report descriptions"),
    (r"\b(casualt|fatalit|dead|death|perish)\b", 2.2, "Casualties or fatalities indicated"),
    (r"\b(unconscious|critical condition|bleeding heavily|heart attack|severe injury|amputat)\b", 1.8, "Life-threatening medical condition"),
    (r"\b(rising water|submerged|swept away|flash flood|dam breach)\b", 1.6, "Active fast-rising water hazard"),
    (r"\b(explosion|gas leak|hazardous chemical|toxic|flammable|spreading rapidly)\b", 2.0, "Hazardous material or rapid fire expansion"),
    (r"\b(child|infant|elderly|pregnant|disabled|dialysis|oxygen dependent)\b", 1.2, "Vulnerable populations at immediate risk"),
    (r"\b(power outage|blackout|grid down|transformer blast)\b", 0.8, "Infrastructure / power failure"),
    (r"\b(road blocked|bridge collapse|inaccessible|cut off|isolated)\b", 1.0, "Access route blockage or isolated terrain"),
    (r"\b(fire spreading|smoke engulfing|roof collapse)\b", 1.5, "Structural fire propagation"),
]

# Report volume / clustering escalation weights
REPORT_COUNT_WEIGHTS: List[Tuple[int, float, str]] = [
    (8, 2.0, "High report density (8+ citizen reports corroborating incident)"),
    (4, 1.4, "Moderate report clustering (4-7 corroborating reports)"),
    (2, 0.8, "Corroborated incident (2-3 distinct citizen reports)"),
    (1, 0.0, "Single citizen report"),
]


def calculate_explainable_severity(
    emergency_type: str,
    descriptions: List[str],
    report_count: int = 1,
    officer_priorities: Optional[List[str]] = None,
    media_count: int = 0,
) -> Tuple[float, SeverityLevel, List[str]]:
    """
    Calculate an explainable, bounded severity score (0.0 to 10.0) and level for a situation.
    Returns: (severity_score, severity_level, key_factors)
    """
    key_factors: List[str] = []
    
    # 1. Base Emergency Type Severity
    base_score = BASE_EMERGENCY_SEVERITY.get(emergency_type, 4.0)
    key_factors.append(f"Base category weight for '{emergency_type}': {base_score:.1f}/10.0")
    
    running_score = base_score
    
    # 2. Textual situational indicator scans across all combined descriptions
    combined_text = " ".join(descriptions).lower()
    matched_boosts = 0.0
    for pattern, boost, explanation in SITUATIONAL_INDICATORS:
        if re.search(pattern, combined_text):
            matched_boosts += boost
            key_factors.append(f"+{boost:.1f} Severity: {explanation}")
            
    # Cap situational keywords boost to prevent runaway inflation
    running_score += min(matched_boosts, 3.5)
    
    # 3. Report clustering / volume escalation
    for threshold, boost, explanation in REPORT_COUNT_WEIGHTS:
        if report_count >= threshold:
            if boost > 0:
                running_score += boost
                key_factors.append(f"+{boost:.1f} Cluster escalation: {explanation}")
            break
            
    # 4. Media evidence boost (visual confirmation)
    if media_count > 0:
        media_boost = min(0.4 * media_count, 0.8)
        running_score += media_boost
        key_factors.append(f"+{media_boost:.1f} Verified on-ground evidence ({media_count} photo/video attachments)")
        
    # 5. Respect Officer Priority Ground Truth (Officers have direct operational authority)
    if officer_priorities:
        if ReportPriority.CRITICAL.value in officer_priorities:
            if running_score < 8.2:
                running_score = max(running_score, 8.2)
                key_factors.append("Severity aligned with confirmed CRITICAL officer priority assessment.")
        elif ReportPriority.HIGH.value in officer_priorities:
            if running_score < 6.2:
                running_score = max(running_score, 6.2)
                key_factors.append("Severity aligned with confirmed HIGH officer priority assessment.")
        elif ReportPriority.MEDIUM.value in officer_priorities:
            if running_score < 4.0:
                running_score = max(running_score, 4.0)
                key_factors.append("Severity aligned with confirmed MEDIUM officer priority assessment.")
                
    # 6. Bound to 0.0 - 10.0
    final_score = round(max(0.5, min(10.0, running_score)), 1)
    
    # 7. Map score to standardized SeverityLevel
    if final_score >= 8.0:
        level = SeverityLevel.CRITICAL
    elif final_score >= 6.0:
        level = SeverityLevel.HIGH
    elif final_score >= 3.5:
        level = SeverityLevel.MEDIUM
    else:
        level = SeverityLevel.LOW
        
    return final_score, level, key_factors
