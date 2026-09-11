import asyncio
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.core.config import settings
from app.models.visual_evidence import (
    VisualEvidenceAnalysis,
    VisualAnalysisStatus,
    GeminiErrorClassification,
    VisualHazardType,
    TextImageConsistency,
)
from app.services.gemini_service import (
    GeminiIntelligenceService,
    classify_gemini_error,
)
from app.services.agents.adapters.priority_agent import PriorityAgent
from app.models.enums import SeverityLevel


# Sample 32-byte realistic image payload (valid 1x1 PNG)
SAMPLE_IMAGE_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(autouse=True)
def clear_caches():
    GeminiIntelligenceService.clear_cache()
    from app.services.vision_router import VisualAnalysisRouter
    router = VisualAnalysisRouter.get_instance()
    router.get_gemini_provider().set_client(None)
    router.get_openai_provider().set_client(None)
    yield
    GeminiIntelligenceService.clear_cache()
    router.get_gemini_provider().set_client(None)
    router.get_openai_provider().set_client(None)


# -------------------------------------------------------------
# 1. Classification Tests
# -------------------------------------------------------------

def test_classify_gemini_503_unavailable():
    class UnavailableException(Exception):
        code = 503
        message = "This model is currently experiencing high demand. Please try again later."

    ex = UnavailableException("503 UNAVAILABLE: high demand")
    classification, retryable, code = classify_gemini_error(ex)
    assert classification == GeminiErrorClassification.GEMINI_TEMPORARILY_UNAVAILABLE
    assert retryable is True
    assert code == 503


def test_classify_gemini_429_rate_limited():
    ex = Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded")
    classification, retryable, code = classify_gemini_error(ex)
    assert classification == GeminiErrorClassification.GEMINI_RATE_LIMITED
    assert retryable is True
    assert code == 429


def test_classify_gemini_502_504_gateway_errors():
    for err_msg in ["502 Bad Gateway", "504 Gateway Timeout", "connection reset by peer"]:
        ex = Exception(err_msg)
        classification, retryable, code = classify_gemini_error(ex)
        assert classification == GeminiErrorClassification.GEMINI_TEMPORARILY_UNAVAILABLE
        assert retryable is True


def test_classify_gemini_timeout():
    ex = asyncio.TimeoutError()
    classification, retryable, code = classify_gemini_error(ex)
    assert classification == GeminiErrorClassification.GEMINI_TIMEOUT
    assert retryable is True


def test_classify_gemini_401_auth_error():
    ex = Exception("401 UNAUTHENTICATED: API key not valid")
    classification, retryable, code = classify_gemini_error(ex)
    assert classification == GeminiErrorClassification.GEMINI_AUTH_ERROR
    assert retryable is False


def test_classify_gemini_400_invalid_request():
    ex = Exception("400 INVALID_ARGUMENT: Payload is malformed")
    classification, retryable, code = classify_gemini_error(ex)
    assert classification == GeminiErrorClassification.GEMINI_INVALID_REQUEST
    assert retryable is False


def test_classify_gemini_malformed_json():
    ex = json.JSONDecodeError("Expecting value", "doc", 0)
    classification, retryable, code = classify_gemini_error(ex)
    assert classification == GeminiErrorClassification.GEMINI_MALFORMED_RESPONSE
    assert retryable is False


# -------------------------------------------------------------
# 2. Vision Success & Idempotency / Caching Tests
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemini_vision_success_and_caching():
    valid_gemini_response = {
        "hazard_type": "FLOOD",
        "hazard_confidence": 0.95,
        "text_image_consistency": "SUPPORTED",
        "claim_evaluations": [
            {
                "claim_text": "Water entered ground floor",
                "status": "SUPPORTED",
                "visual_observation": "Muddy floodwater reaches porch level",
                "confidence": 0.95,
            }
        ],
        "visual_observations": [
            {
                "category": "ENVIRONMENTAL_IMPACT",
                "observation": "High water levels on street",
                "severity_indicator": "HIGH",
                "confidence": 0.90,
            }
        ],
        "vulnerable_person_indicators": [],
        "infrastructure_conditions": [
            {
                "infrastructure_type": "ROAD",
                "condition": "SUBMERGED",
                "is_access_blocked": True,
                "confidence": 0.92,
            }
        ],
        "visible_impacts": ["Submerged road", "Water against structure"],
        "affected_people_observable": False,
        "estimated_people_count": None,
        "medical_indicators": [],
        "environmental_indicators": ["Muddy standing water"],
        "obstruction_indicators": ["Road blocked by flood"],
        "uncertainties": [],
        "overall_confidence": 0.92,
        "warnings": [],
    }

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(valid_gemini_response)
    mock_client.models.generate_content.return_value = mock_resp

    GeminiIntelligenceService.set_client(mock_client)

    result = await GeminiIntelligenceService.analyze_visual_evidence(
        source_id="EV-TEST-001",
        image_bytes=SAMPLE_IMAGE_BYTES,
        citizen_text="Water entered ground floor",
        declared_type="Flood",
        report_id="REP-TEST-001",
    )

    assert result.status == VisualAnalysisStatus.SUCCESS
    assert result.hazard_type == VisualHazardType.FLOOD
    assert result.text_image_consistency == TextImageConsistency.SUPPORTED
    assert result.evidence_available is True
    assert result.analysis_available is True
    assert result.retryable is False
    assert result.is_cached is False
    assert mock_client.models.generate_content.call_count == 1

    # Second call should hit idempotent cache
    cached_res = await GeminiIntelligenceService.analyze_visual_evidence(
        source_id="EV-TEST-001",
        image_bytes=SAMPLE_IMAGE_BYTES,
        citizen_text="Water entered ground floor",
        declared_type="Flood",
        report_id="REP-TEST-001",
    )
    assert cached_res.status == VisualAnalysisStatus.SUCCESS
    assert cached_res.is_cached is True
    # Still only 1 actual API call was made
    assert mock_client.models.generate_content.call_count == 1


# -------------------------------------------------------------
# 3. Gemini 503 Retry & Recovery
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemini_503_retry_and_recovery():
    valid_resp = MagicMock()
    valid_resp.text = json.dumps({
        "hazard_type": "FIRE",
        "hazard_confidence": 0.90,
        "text_image_consistency": "SUPPORTED",
        "claim_evaluations": [],
        "visual_observations": [],
        "vulnerable_person_indicators": [],
        "infrastructure_conditions": [],
        "visible_impacts": ["Smoke rising"],
        "overall_confidence": 0.88,
    })

    mock_client = MagicMock()
    # Attempt 1: 503 Unavailable, Attempt 2: Success
    mock_client.models.generate_content.side_effect = [
        Exception("503 UNAVAILABLE: This model is currently experiencing high demand."),
        valid_resp,
    ]

    GeminiIntelligenceService.set_client(mock_client)

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await GeminiIntelligenceService.analyze_visual_evidence(
            source_id="EV-503-RECOVER",
            image_bytes=SAMPLE_IMAGE_BYTES,
            citizen_text="Smoke visible from roof",
            declared_type="Fire",
            report_id="REP-503-01",
        )

        assert result.status == VisualAnalysisStatus.SUCCESS
        assert result.hazard_type == VisualHazardType.FIRE
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1


# -------------------------------------------------------------
# 4. Gemini 503 Retry Exhaustion -> TEMPORARILY_UNAVAILABLE
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemini_503_retry_exhaustion():
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception(
        "503 UNAVAILABLE: Model overloaded with high demand"
    )

    GeminiIntelligenceService.set_client(mock_client)

    with patch.object(settings, "OPENAI_API_KEY", ""), patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await GeminiIntelligenceService.analyze_visual_evidence(
            source_id="EV-503-EXHAUST",
            image_bytes=SAMPLE_IMAGE_BYTES,
            citizen_text="Severe flooding on main street",
            declared_type="Flood",
            report_id="REP-503-02",
        )

        assert result.status == VisualAnalysisStatus.TEMPORARILY_UNAVAILABLE
        assert result.evidence_available is True
        assert result.analysis_available is False
        assert result.retryable is True
        assert result.error_classification == GeminiErrorClassification.GEMINI_TEMPORARILY_UNAVAILABLE.value
        assert result.retry_attempts_exhausted == 3
        assert "temporarily unavailable" in result.error_message.lower()
        assert "evidence has been safely preserved" in result.error_message.lower()
        # Retried 3 times
        assert mock_client.models.generate_content.call_count == 3
        # Slept 2 times between 3 attempts
        assert mock_sleep.call_count == 2


# -------------------------------------------------------------
# 5. Temporary Failure is NOT cached as success
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_temporary_failure_not_cached_as_success():
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("503 UNAVAILABLE")
    GeminiIntelligenceService.set_client(mock_client)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        res1 = await GeminiIntelligenceService.analyze_visual_evidence(
            source_id="EV-NO-CACHE-FAIL",
            image_bytes=SAMPLE_IMAGE_BYTES,
            citizen_text="Flooding report",
            declared_type="Flood",
            report_id="REP-FAIL-01",
        )
        assert res1.status == VisualAnalysisStatus.TEMPORARILY_UNAVAILABLE

    # Now make Gemini succeed on next try
    valid_resp = MagicMock()
    valid_resp.text = json.dumps({
        "hazard_type": "FLOOD",
        "hazard_confidence": 0.88,
        "text_image_consistency": "SUPPORTED",
        "claim_evaluations": [],
        "visual_observations": [],
        "vulnerable_person_indicators": [],
        "infrastructure_conditions": [],
        "visible_impacts": [],
        "overall_confidence": 0.85,
    })
    mock_client.models.generate_content.side_effect = None
    mock_client.models.generate_content.return_value = valid_resp

    res2 = await GeminiIntelligenceService.analyze_visual_evidence(
        source_id="EV-NO-CACHE-FAIL",
        image_bytes=SAMPLE_IMAGE_BYTES,
        citizen_text="Flooding report",
        declared_type="Flood",
        report_id="REP-FAIL-01",
    )
    # Must NOT have returned the cached 503! Must return SUCCESS
    assert res2.status == VisualAnalysisStatus.SUCCESS
    assert res2.hazard_type == VisualHazardType.FLOOD


# -------------------------------------------------------------
# 6. Non-retryable Errors (401 Auth, 400 Bad Request, Malformed JSON)
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_retryable_auth_error_fails_immediately():
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("401 UNAUTHENTICATED: Invalid API key")
    GeminiIntelligenceService.set_client(mock_client)

    with patch.object(settings, "OPENAI_API_KEY", ""), patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await GeminiIntelligenceService.analyze_visual_evidence(
            source_id="EV-AUTH-FAIL",
            image_bytes=SAMPLE_IMAGE_BYTES,
            citizen_text="Fire incident",
            declared_type="Fire",
        )
        assert result.status == VisualAnalysisStatus.FAILED
        assert result.retryable is False
        assert result.error_classification == GeminiErrorClassification.GEMINI_AUTH_ERROR.value
        # No retry attempts made for non-retryable auth error
        assert mock_client.models.generate_content.call_count == 1
        assert mock_sleep.call_count == 0


@pytest.mark.asyncio
async def test_invalid_image_fails_safely():
    # Empty or tiny byte payload
    result = await GeminiIntelligenceService.analyze_visual_evidence(
        source_id="EV-EMPTY",
        image_bytes=b"123",  # < 16 bytes
        citizen_text="Fire incident",
    )
    assert result.status == VisualAnalysisStatus.UNAVAILABLE
    assert result.retryable is False


# -------------------------------------------------------------
# 7. PriorityAgent Safety with & without Visual Analysis
# -------------------------------------------------------------

from app.models.agent import AgentContext

@pytest.mark.asyncio
async def test_priority_agent_with_temporarily_unavailable_visual_evidence():
    agent = PriorityAgent()

    # Report parameters where visual evidence is TEMPORARILY_UNAVAILABLE
    context = AgentContext(
        situation_id="SIT-TEST-001",
        emergency_type="Flood",
        description="Water is 3 feet high on Main Street, elderly neighbor needs help.",
        parameters={
            "citizen_impact_level": "HIGH",
            "evidence_verification": {
                "verification_status": "PARTIALLY_VERIFIED",
                "confidence_band": "MEDIUM",
                "location_match_state": "MATCH",
                "evidence_freshness": "FRESH",
                "has_live_photo": True,
            },
            "visual_evidence": {
                "status": "TEMPORARILY_UNAVAILABLE",
                "evidence_available": True,
                "analysis_available": False,
                "retryable": True,
                "error_classification": "GEMINI_TEMPORARILY_UNAVAILABLE",
            },
        },
    )

    result = await agent.execute(context)

    assert result.status.value == "COMPLETED"
    assert result.structured_output["evidence_aware"] is False
    assert result.structured_output["text_image_consistency"] == "UNAVAILABLE"
    # Must compute valid deterministic severity score without crash or fabrication
    assert result.structured_output["severity_level"] in ["HIGH", "CRITICAL", "MEDIUM"]
    assert result.structured_output["severity_score"] > 0
    # No fake visual evidence was created
    assert not any("Live camera photo shows observable" in f for f in result.structured_output["evidence_factors"])


@pytest.mark.asyncio
async def test_priority_agent_with_successful_visual_evidence():
    agent = PriorityAgent()

    context = AgentContext(
        situation_id="SIT-TEST-002",
        emergency_type="Flood",
        description="Flood water blocking road completely.",
        parameters={
            "citizen_impact_level": "HIGH",
            "visual_evidence": {
                "status": "SUCCESS",
                "hazard_type": "FLOOD",
                "text_image_consistency": "SUPPORTED",
                "visible_impacts": ["Submerged roadway"],
                "claim_evaluations": [
                    {
                        "claim_text": "Flood water blocking road",
                        "status": "SUPPORTED",
                        "visual_observation": "Road under 2ft water",
                    }
                ],
                "infrastructure_conditions": [
                    {
                        "infrastructure_type": "ROAD",
                        "condition": "SUBMERGED",
                        "is_access_blocked": True,
                    }
                ],
            },
        },
    )

    result = await agent.execute(context)

    assert result.status.value == "COMPLETED"
    assert result.structured_output["evidence_aware"] is True
    assert result.structured_output["text_image_consistency"] == "SUPPORTED"
    assert any("Claim visually confirmed" in f for f in result.structured_output["evidence_factors"])
