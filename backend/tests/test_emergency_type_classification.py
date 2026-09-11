import pytest
from app.models.enums import EmergencyType, ReportPriority, ReportStatus
from app.models.citizen import EmergencyReportResponse, LocationPayload
from app.models.llm_extraction import LLMExtractionResult, ExtractedHazard, ExtractionStatus
from app.services.incident_fusion import calculate_explainable_severity


# ==============================================================================
# CANONICAL EMERGENCY TYPE TESTS
# ==============================================================================

def test_01_canonical_emergency_types_exist():
    assert EmergencyType.FLOOD.value == "Flood"
    assert EmergencyType.FIRE.value == "Fire"
    assert EmergencyType.CYCLONE_STORM.value == "Cyclone / Storm"
    assert EmergencyType.MEDICAL_EMERGENCY.value == "Medical Emergency"
    assert EmergencyType.LANDSLIDE.value == "Landslide"
    assert EmergencyType.BUILDING_COLLAPSE.value == "Building Collapse"
    assert EmergencyType.ROAD_ACCIDENT.value == "Road Accident"
    assert EmergencyType.MISSING_TRAPPED.value == "Missing / Trapped Person"
    assert EmergencyType.OTHER.value == "Other"


def test_02_title_formatting_contract():
    def format_emergency_title(emergency_type: str | None) -> str:
        if not emergency_type or emergency_type in ["Other", "OTHER", "UNKNOWN", "Unspecified"]:
            return "Emergency Incident"
        clean_type = emergency_type.strip()
        if clean_type.lower().endswith("emergency"):
            return clean_type
        return f"{clean_type} Emergency"

    assert format_emergency_title("Flood") == "Flood Emergency"
    assert format_emergency_title("Fire") == "Fire Emergency"
    assert format_emergency_title("Cyclone / Storm") == "Cyclone / Storm Emergency"
    assert format_emergency_title("Landslide") == "Landslide Emergency"
    assert format_emergency_title("Medical Emergency") == "Medical Emergency"
    assert format_emergency_title("Other") == "Emergency Incident"
    assert format_emergency_title(None) == "Emergency Incident"
    assert format_emergency_title("") == "Emergency Incident"


def test_03_flood_keyword_detection_contract():
    def detect_flood_keywords(text: str) -> bool:
        lower = text.lower()
        flood_keywords = [
            "paani", "pani", "nadi", "flood", "waterlog", "water rising",
            "submerged", "drowning", "jal-bharaav", "water entered", "river water"
        ]
        return any(k in lower for k in flood_keywords)

    sample_hindi = "Nadi ka paani ghar ke andar aa gaya hai. Lagbhag 20 log affected hain aur 2 elderly log phase hue hain."
    sample_english = "Heavy waterlogging and flood water entered ground floor."
    sample_fire = "Commercial fire broke out near factory."

    assert detect_flood_keywords(sample_hindi) is True
    assert detect_flood_keywords(sample_english) is True
    assert detect_flood_keywords(sample_fire) is False


def test_04_gemini_extraction_remains_advisory_without_altering_canonical_model():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    report = EmergencyReportResponse(
        report_id="RES-TEST-FLD-01",
        citizen_id="CIT-001",
        citizen_name="Citizen Tester",
        citizen_phone="9999999999",
        emergency_type=EmergencyType.FLOOD,
        description="Nadi ka paani ghar ke andar aa gaya hai.",
        location=LocationPayload(latitude=16.5, longitude=80.6, address="River Ward"),
        llm_extraction=LLMExtractionResult(
            source_id="RES-TEST-FLD-01",
            status=ExtractionStatus.SUCCESS,
            hazard=ExtractedHazard(value="FLOOD", confidence=0.95),
            overall_confidence=0.95,
        ),
        status=ReportStatus.RECEIVED,
        created_at=now,
        updated_at=now,
    )

    # Authoritative field remains EmergencyType.FLOOD
    assert report.emergency_type == EmergencyType.FLOOD
    assert report.emergency_type.value == "Flood"
    # LLM extraction remains advisory inside llm_extraction container
    assert report.llm_extraction.hazard.value == "FLOOD"
    assert report.llm_extraction.hazard.confidence == 0.95


def test_05_calculate_explainable_severity_preserves_flood_type():
    score, level, factors = calculate_explainable_severity(
        emergency_type=EmergencyType.FLOOD.value,
        descriptions=["Nadi ka paani ghar ke andar aa gaya hai."],
        report_count=1,
    )
    assert score >= 5.0
    assert any("flood" in f.lower() or "water" in f.lower() for f in factors)
