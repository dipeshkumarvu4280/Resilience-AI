import pytest
import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from app.models.llm_extraction import LLMExtractionResult, ExtractedLanguage
from app.models.enums import EmergencyType, SeverityLevel, SafetyNotificationType
from app.services.text_analysis_router import parse_llm_extraction_json
from app.services.agents.adapters.safety_guidance_agent import (
    SafetyGuidanceAgent,
    MULTILINGUAL_SAFETY_TEMPLATES,
)
from app.models.safety_guidance import (
    CitizenSafetyGuidance,
    VerifiedDestination,
    RouteDetails,
    DestinationType,
    RouteStatus,
)
from app.services.notification.web_push_service import WebPushService


def test_parse_llm_extraction_multilingual_telugu():
    raw_dict = {
        "detected_language": {
            "code": "te",
            "name": "Telugu",
            "confidence": 0.98,
            "is_mixed": False
        },
        "hazard": {
            "value": "Flood",
            "confidence": 0.95,
            "excerpt": "నా ఇంట్లోకి నీళ్లు వచ్చాయి"
        },
        "observations": [
            {"type": "WATER_ENTERED_RESIDENCE", "confidence": 0.95}
        ],
        "overall_confidence": 0.95
    }
    raw_json = json.dumps(raw_dict)
    result = parse_llm_extraction_json(
        raw_text=raw_json,
        source_id="REP-TE-001",
        source_type="CITIZEN_REPORT",
        model_name="gemini-2.5-flash",
        provider="GEMINI",
    )
    assert result.detected_language is not None
    assert result.detected_language.code == "te"
    assert result.detected_language.name == "Telugu"
    assert result.detected_language.confidence >= 0.9
    assert result.hazard is not None
    assert result.hazard.value == "Flood"


def test_parse_llm_extraction_multilingual_hindi():
    raw_dict = {
        "detected_language": {
            "code": "hi",
            "name": "Hindi",
            "confidence": 0.99,
            "is_mixed": False
        },
        "hazard": {
            "value": "Fire",
            "confidence": 0.98,
            "excerpt": "इमारत में आग लगी है"
        },
        "observations": [
            {"type": "STRUCTURAL_FIRE", "confidence": 0.98}
        ],
        "overall_confidence": 0.98
    }
    raw_json = json.dumps(raw_dict)
    result = parse_llm_extraction_json(
        raw_text=raw_json,
        source_id="REP-HI-001",
        source_type="CITIZEN_REPORT",
        model_name="gpt-5.6-luna",
        provider="OPENAI",
    )
    assert result.detected_language is not None
    assert result.detected_language.code == "hi"
    assert result.detected_language.name == "Hindi"
    assert result.hazard is not None
    assert result.hazard.value == "Fire"


def test_safety_guidance_synthesis_telugu():
    dest = VerifiedDestination(
        destination_id="PLC-123",
        destination_name="విజయవాడ పునరావాస కేంద్రం",
        destination_type=DestinationType.SHELTER,
        latitude=16.5062,
        longitude=80.6480,
        address_or_landmark="Bhavanipuram",
        distance_km=2.4,
        estimated_drive_minutes=8.0,
        is_verified_operational=True,
    )
    route = RouteDetails(
        origin_latitude=16.5000,
        origin_longitude=80.6400,
        destination_latitude=16.5062,
        destination_longitude=80.6480,
        distance_km=2.4,
        estimated_duration_minutes=8.0,
        route_status=RouteStatus.CALCULATED,
        route_warnings=["నీటి నిల్వ ఉన్న లోతట్టు ప్రాంతాలను నివారించండి"],
    )

    actions, precautions = SafetyGuidanceAgent._synthesize_contextual_actions(
        emergency_type="Flood",
        description="నా ఇంట్లోకి నీళ్లు వచ్చాయి",
        risk_level=SeverityLevel.HIGH,
        destination=dest,
        route=route,
        language_code="te",
    )

    assert len(actions) >= 2
    assert len(precautions) >= 1
    assert any("ఎత్తైన" in a or "వరద" in a or "విజయవాడ" in a for a in actions)
    assert any("విద్యుత్" in p or "హెచ్చరిక" in p for p in precautions)


def test_safety_guidance_synthesis_hindi():
    dest = VerifiedDestination(
        destination_id="PLC-456",
        destination_name="सामुदायिक राहत केंद्र",
        destination_type=DestinationType.SHELTER,
        latitude=28.6139,
        longitude=77.2090,
        address_or_landmark="Central Zone",
        distance_km=3.1,
        estimated_drive_minutes=10.0,
        is_verified_operational=True,
    )

    actions, precautions = SafetyGuidanceAgent._synthesize_contextual_actions(
        emergency_type="Fire",
        description="इमारत में आग लगी है",
        risk_level=SeverityLevel.CRITICAL,
        destination=dest,
        language_code="hi",
    )

    assert len(actions) >= 2
    assert any("इमारत खाली करें" in a or "सामुदायिक राहत केंद्र" in a for a in actions)
    assert any("लिफ्ट" in p or "कपड़े से ढकें" in p for p in precautions)


def test_localize_guidance_live_override():
    base_guidance = CitizenSafetyGuidance(
        guidance_id="GUD-TEST-001",
        secure_access_token="tok_1234567890abcdef",
        report_id="REP-TEST-001",
        generated_at=datetime.now(timezone.utc),
        valid_until=datetime.now(timezone.utc),
        status="ACTIVE",
        emergency_type="Flood",
        risk_level=SeverityLevel.HIGH,
        immediate_actions=["Move to higher ground immediately."],
        precautions=["Turn off main electrical breaker."],
        recommended_destination=VerifiedDestination(
            destination_id="PLC-TEST",
            destination_name="City Central Shelter",
            destination_type=DestinationType.SHELTER,
            latitude=16.50,
            longitude=80.64,
            address_or_landmark="Main St",
            distance_km=1.5,
            is_verified_operational=True,
        ),
        language={"code": "en", "name": "English", "source": "DEFAULT"},
    )

    # Localize to Telugu
    te_guidance = SafetyGuidanceAgent.localize_guidance(base_guidance, "te")
    assert te_guidance.language["code"] == "te"
    assert "తెలుగు" in te_guidance.language["name"]
    assert any("ఎత్తైన" in a for a in te_guidance.immediate_actions)

    # Localize to Hindi
    hi_guidance = SafetyGuidanceAgent.localize_guidance(base_guidance, "hi")
    assert hi_guidance.language["code"] == "hi"
    assert "हिन्दी" in hi_guidance.language["name"]
    assert any("ऊंचे स्थान" in a for a in hi_guidance.immediate_actions)

    # Localize to Tamil
    ta_guidance = SafetyGuidanceAgent.localize_guidance(base_guidance, "ta")
    assert ta_guidance.language["code"] == "ta"
    assert "தமிழ்" in ta_guidance.language["name"]
    assert any("உயர்ந்த" in a for a in ta_guidance.immediate_actions)


def test_multilingual_push_notification_payload():
    guidance_te = CitizenSafetyGuidance(
        guidance_id="GUD-PUSH-001",
        secure_access_token="tok_te_push",
        report_id="REP-PUSH-001",
        generated_at=datetime.now(timezone.utc),
        valid_until=datetime.now(timezone.utc),
        status="ACTIVE",
        emergency_type="Flood",
        risk_level=SeverityLevel.HIGH,
        immediate_actions=[],
        precautions=[],
        recommended_destination=VerifiedDestination(
            destination_id="PLC-TE",
            destination_name="జిల్లా సహాయ కేంద్రం",
            destination_type=DestinationType.SHELTER,
            latitude=16.50,
            longitude=80.64,
            address_or_landmark="Zone 1",
            distance_km=2.0,
            estimated_drive_minutes=5.0,
            is_verified_operational=True,
        ),
        language={"code": "te", "name": "Telugu", "source": "DETECTION"},
    )

    payload = WebPushService.get_controlled_payload(
        guidance_te,
        notification_type=SafetyNotificationType.SAFETY_GUIDANCE_READY,
    )

    assert "అత్యవసర భద్రతా మార్గదర్శకం" in payload.title
    assert "ధృవీకరించబడిన సురక్షిత గమ్యస్థానం" in payload.body
    assert "జిల్లా సహాయ కేంద్రం" in payload.body
    assert payload.data.get("language") == "te"


from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_create_report_and_guidance_multilingual_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        report_data = {
            "full_name": "రమేష్ వర్మ",
            "phone": "9876543999",
            "emergency_type": "Flood",
            "citizen_impact_level": "HIGH",
            "description": "నా ఇంట్లోకి నీళ్లు వచ్చాయి, రోడ్డు మొత్తం మునిగిపోయింది",
            "preferred_language": "te",
            "location": {
                "latitude": 16.5062,
                "longitude": 80.6480,
                "address": "Bhavanipuram, Vijayawada"
            }
        }

        # Post emergency report
        response = await client.post("/api/v1/citizen/reports", json=report_data)
        assert response.status_code == 201
        res_data = response.json()
        report_id = res_data.get("report_id") or res_data.get("id")
        token = res_data.get("safety_guidance_token")
        assert report_id is not None
        assert res_data.get("language") is not None
        assert res_data["language"]["code"] == "te"

        # Query safety guidance with default (stored) language
        if token:
            g_resp = await client.get(f"/api/v1/citizen/safety-guidance/{token}")
            assert g_resp.status_code == 200
            g_data = g_resp.json()
            assert g_data["success"] is True
            guidance_obj = g_data["guidance"]
            assert guidance_obj["language"]["code"] == "te"
            assert any("ఎత్తైన" in a or "వరద" in a for a in guidance_obj["immediate_actions"])

            # Query safety guidance with live Hindi override
            hi_resp = await client.get(f"/api/v1/citizen/safety-guidance/{token}?lang=hi")
            assert hi_resp.status_code == 200
            hi_data = hi_resp.json()
            assert hi_data["guidance"]["language"]["code"] == "hi"
            assert any("ऊंचे स्थान" in a for a in hi_data["guidance"]["immediate_actions"])

