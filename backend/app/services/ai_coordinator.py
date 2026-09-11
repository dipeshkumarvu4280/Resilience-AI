import logging
from typing import List, Dict, Any, Optional
from app.models.enums import EmergencyType, ResourceType, NeedUrgency
from app.models.resource import AINeedsSuggestionItem, AINeedsSuggestionResponse

logger = logging.getLogger("resilience.ai_coordinator")


def generate_heuristic_ai_needs_suggestions(
    emergency_type: str,
    description: str,
    location_summary: str = "",
) -> List[AINeedsSuggestionItem]:
    """
    Expert heuristic emergency assessment engine for generating initial advisory recommendations
    based on incident type, situational keywords, and geographical severity.
    """
    suggestions: List[AINeedsSuggestionItem] = []
    desc_lower = description.lower()
    et_lower = emergency_type.lower()

    if "flood" in et_lower or "water" in desc_lower or "submerged" in desc_lower:
        suggestions.append(AINeedsSuggestionItem(
            resource_type=ResourceType.RESCUE_EQUIPMENT,
            suggested_quantity=4.0,
            unit="Inflatable Rafts / Kits",
            urgency=NeedUrgency.CRITICAL,
            reasoning="Water rescue and evacuation capability required for flooded zone.",
            confidence=0.92,
        ))
        suggestions.append(AINeedsSuggestionItem(
            resource_type=ResourceType.WATER,
            suggested_quantity=100.0,
            unit="Litres (Potable)",
            urgency=NeedUrgency.HIGH,
            reasoning="Potable drinking water supply essential to prevent waterborne contamination.",
            confidence=0.88,
        ))
        suggestions.append(AINeedsSuggestionItem(
            resource_type=ResourceType.BLANKETS,
            suggested_quantity=50.0,
            unit="Pieces",
            urgency=NeedUrgency.MEDIUM,
            reasoning="Thermal comfort for displaced citizens exposed to wet conditions.",
            confidence=0.82,
        ))

    elif "fire" in et_lower or "smoke" in desc_lower or "burn" in desc_lower:
        suggestions.append(AINeedsSuggestionItem(
            resource_type=ResourceType.FIRST_AID,
            suggested_quantity=15.0,
            unit="Burn & Trauma Kits",
            urgency=NeedUrgency.CRITICAL,
            reasoning="Immediate burn care and smoke inhalation emergency first aid.",
            confidence=0.95,
        ))
        suggestions.append(AINeedsSuggestionItem(
            resource_type=ResourceType.PROTECTIVE_EQUIPMENT,
            suggested_quantity=20.0,
            unit="Respirators / SCBA Sets",
            urgency=NeedUrgency.HIGH,
            reasoning="Respiratory protection for first responders and active search personnel.",
            confidence=0.90,
        ))

    elif "collapse" in et_lower or "landslide" in et_lower or "trapped" in desc_lower:
        suggestions.append(AINeedsSuggestionItem(
            resource_type=ResourceType.RESCUE_EQUIPMENT,
            suggested_quantity=5.0,
            unit="Hydraulic Cutters / Spreaders",
            urgency=NeedUrgency.CRITICAL,
            reasoning="Heavy extraction equipment necessary for debris clearance and extrication.",
            confidence=0.94,
        ))
        suggestions.append(AINeedsSuggestionItem(
            resource_type=ResourceType.MEDICAL_EQUIPMENT,
            suggested_quantity=10.0,
            unit="Trauma Stretchers & C-Collars",
            urgency=NeedUrgency.HIGH,
            reasoning="Immobilization and transport gear for crush injuries.",
            confidence=0.89,
        ))
        suggestions.append(AINeedsSuggestionItem(
            resource_type=ResourceType.GENERATOR,
            suggested_quantity=2.0,
            unit="5kW Units",
            urgency=NeedUrgency.MEDIUM,
            reasoning="Emergency perimeter illumination and power for search teams.",
            confidence=0.80,
        ))

    elif "medical" in et_lower or "injury" in desc_lower or "casualty" in desc_lower:
        suggestions.append(AINeedsSuggestionItem(
            resource_type=ResourceType.MEDICINE,
            suggested_quantity=25.0,
            unit="Emergency Trauma & IV Packs",
            urgency=NeedUrgency.CRITICAL,
            reasoning="Urgent stabilization and triage supplies for casualties.",
            confidence=0.93,
        ))
        suggestions.append(AINeedsSuggestionItem(
            resource_type=ResourceType.FIRST_AID,
            suggested_quantity=20.0,
            unit="Triage First Aid Kits",
            urgency=NeedUrgency.HIGH,
            reasoning="Field first aid for minor and moderate wounds.",
            confidence=0.87,
        ))

    else:
        # General emergency advisory
        suggestions.append(AINeedsSuggestionItem(
            resource_type=ResourceType.FIRST_AID,
            suggested_quantity=10.0,
            unit="General Response Kits",
            urgency=NeedUrgency.HIGH,
            reasoning="Standard emergency triage and on-scene first aid readiness.",
            confidence=0.80,
        ))
        suggestions.append(AINeedsSuggestionItem(
            resource_type=ResourceType.COMMUNICATION_EQUIPMENT,
            suggested_quantity=4.0,
            unit="Handheld Radios",
            urgency=NeedUrgency.MEDIUM,
            reasoning="Field relay and coordination communication units.",
            confidence=0.75,
        ))

    return suggestions


async def generate_ai_needs_assessment(
    report_id: str,
    emergency_type: str,
    description: str,
    location_summary: str,
) -> AINeedsSuggestionResponse:
    """
    Generates structured AI suggestions for an emergency report.
    Advisory only; always requires human officer review and confirmation.
    """
    try:
        suggestions = generate_heuristic_ai_needs_suggestions(
            emergency_type=emergency_type,
            description=description,
            location_summary=location_summary,
        )
        return AINeedsSuggestionResponse(
            report_id=report_id,
            suggestions=suggestions,
            ai_available=True,
            disclaimer="AI recommendations are advisory only. Emergency Officer verification is mandatory."
        )
    except Exception as e:
        logger.warning(f"AI Needs Advisory error: {e}")
        return AINeedsSuggestionResponse(
            report_id=report_id,
            suggestions=[],
            ai_available=False,
            disclaimer="AI assistance unavailable. Manual needs assessment is available."
        )
