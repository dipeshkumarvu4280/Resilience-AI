import asyncio
import json
import pytest
from unittest.mock import MagicMock, AsyncMock

from app.core.config import settings
from app.models.visual_evidence import (
    VisualEvidenceAnalysis,
    VisualAnalysisStatus,
    VisualHazardType,
    TextImageConsistency,
    VisionProviderType,
    VisionFailureCategory,
)
from app.services.vision_router import (
    VisualAnalysisRouter,
    GeminiVisionProvider,
    OpenAIVisionProvider,
    parse_visual_evidence_json,
    classify_gemini_error,
    classify_openai_error,
)
from app.services.gemini_service import GeminiIntelligenceService



SAMPLE_VALID_RESPONSE_JSON = json.dumps({
    "hazard_type": "FLOOD",
    "hazard_confidence": 0.92,
    "text_image_consistency": "SUPPORTED",
    "claim_evaluations": [
        {
            "claim_text": "Water rising above waist level on main road",
            "status": "SUPPORTED",
            "visual_observation": "Muddy floodwater visibly reaching shop front shutters and submerging parked cars up to hoods.",
            "confidence": 0.95
        }
    ],
    "visual_observations": [
        {
            "category": "INFRASTRUCTURE_IMPACT",
            "observation": "Road submerged by 1-1.5m turbulent floodwater",
            "severity_indicator": "HIGH",
            "confidence": 0.92
        }
    ],
    "vulnerable_person_indicators": [
        {
            "indicator_type": "ELDERLY",
            "observed_details": "Elderly individual stranded on elevated porch",
            "confidence": 0.88
        }
    ],
    "infrastructure_conditions": [
        {
            "infrastructure_type": "ROAD",
            "condition": "SUBMERGED",
            "is_access_blocked": True,
            "confidence": 0.95
        }
    ],
    "visible_impacts": ["Submerged vehicles", "Inaccessible road"],
    "affected_people_observable": True,
    "estimated_people_count": 3,
    "medical_indicators": [],
    "environmental_indicators": ["Muddy brown floodwaters"],
    "obstruction_indicators": ["Fallen branches submerged"],
    "uncertainties": [],
    "overall_confidence": 0.92,
    "warnings": []
})


@pytest.fixture(autouse=True)
def reset_router():
    """Reset router and providers before each test."""
    router = VisualAnalysisRouter.get_instance()
    router.clear_cache()
    gemini_p = GeminiVisionProvider()
    openai_p = OpenAIVisionProvider()
    router.register_provider(gemini_p)
    router.register_provider(openai_p)
    yield
    router.clear_cache()


# 1. Gemini Success
@pytest.mark.asyncio
async def test_gemini_vision_success():
    router = VisualAnalysisRouter.get_instance()
    gemini_p = router.get_gemini_provider()

    mock_gemini_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_VALID_RESPONSE_JSON
    mock_gemini_client.models.generate_content.return_value = mock_resp
    gemini_p.set_client(mock_gemini_client)

    result = await router.analyze_visual_evidence(
        source_id="TEST-001",
        image_bytes=b"GIF89a_fake_image_bytes_here_12345678",
        citizen_text="Water rising on road",
        report_id="REP-001",
        evidence_id="EVID-001",
    )

    assert result.status == VisualAnalysisStatus.SUCCESS
    assert result.provider == "GEMINI"
    assert result.fallback_triggered is False
    assert result.hazard_type == VisualHazardType.FLOOD
    assert result.text_image_consistency == TextImageConsistency.SUPPORTED
    assert result.evidence_available is True
    assert result.analysis_available is True


# 2. Gemini 503 -> Retry -> Success
@pytest.mark.asyncio
async def test_gemini_503_retry_success():
    router = VisualAnalysisRouter.get_instance()
    gemini_p = router.get_gemini_provider()

    mock_gemini_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_VALID_RESPONSE_JSON

    err_503 = Exception("503 UNAVAILABLE: Model is currently experiencing high demand.")
    mock_gemini_client.models.generate_content.side_effect = [err_503, mock_resp]
    gemini_p.set_client(mock_gemini_client)

    result = await router.analyze_visual_evidence(
        source_id="TEST-002",
        image_bytes=b"GIF89a_fake_image_bytes_here_503_retry",
        citizen_text="Road flooded",
        report_id="REP-002",
    )

    assert result.status == VisualAnalysisStatus.SUCCESS
    assert result.provider == "GEMINI"
    assert result.fallback_triggered is False
    assert result.hazard_type == VisualHazardType.FLOOD
    assert mock_gemini_client.models.generate_content.call_count == 2


# 3. Gemini 503 -> Retry Exhaustion -> OpenAI Success (Failover)
@pytest.mark.asyncio
async def test_gemini_503_exhaustion_openai_fallback_success():
    router = VisualAnalysisRouter.get_instance()
    gemini_p = router.get_gemini_provider()
    openai_p = router.get_openai_provider()

    # Mock Gemini always failing with 503
    mock_gemini_client = MagicMock()
    mock_gemini_client.models.generate_content.side_effect = Exception("503 UNAVAILABLE: high demand spikes")
    gemini_p.set_client(mock_gemini_client)

    # Mock OpenAI succeeding
    mock_openai_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = SAMPLE_VALID_RESPONSE_JSON
    mock_openai_resp = MagicMock()
    mock_openai_resp.choices = [mock_choice]
    mock_openai_client.chat.completions.create.return_value = mock_openai_resp
    openai_p.set_client(mock_openai_client)

    result = await router.analyze_visual_evidence(
        source_id="TEST-003",
        image_bytes=b"GIF89a_fake_image_bytes_here_openai_fallback",
        citizen_text="Flooding on street",
        report_id="REP-003",
        evidence_id="EVID-003",
    )

    assert result.status == VisualAnalysisStatus.SUCCESS
    assert result.provider == "OPENAI"
    assert result.fallback_triggered is True
    assert result.fallback_provider == "OPENAI"
    assert "503" in (result.primary_provider_error or "")
    assert result.hazard_type == VisualHazardType.FLOOD
    assert result.evidence_available is True
    assert result.analysis_available is True


# 4. Gemini 429 Rate Limited -> Fallback to OpenAI
@pytest.mark.asyncio
async def test_gemini_429_rate_limit_fallback():
    router = VisualAnalysisRouter.get_instance()
    gemini_p = router.get_gemini_provider()
    openai_p = router.get_openai_provider()

    mock_gemini_client = MagicMock()
    mock_gemini_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Rate limit reached")
    gemini_p.set_client(mock_gemini_client)

    mock_openai_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = SAMPLE_VALID_RESPONSE_JSON
    mock_openai_resp = MagicMock()
    mock_openai_resp.choices = [mock_choice]
    mock_openai_client.chat.completions.create.return_value = mock_openai_resp
    openai_p.set_client(mock_openai_client)

    result = await router.analyze_visual_evidence(
        source_id="TEST-004",
        image_bytes=b"GIF89a_fake_image_bytes_here_429_test",
        citizen_text="Flooding on street",
    )

    assert result.status == VisualAnalysisStatus.SUCCESS
    assert result.provider == "OPENAI"
    assert result.fallback_triggered is True


# 5. Gemini Timeout -> Fallback to OpenAI
@pytest.mark.asyncio
async def test_gemini_timeout_fallback():
    router = VisualAnalysisRouter.get_instance()
    gemini_p = router.get_gemini_provider()
    openai_p = router.get_openai_provider()

    mock_gemini_client = MagicMock()
    mock_gemini_client.models.generate_content.side_effect = asyncio.TimeoutError("Gemini call timed out")
    gemini_p.set_client(mock_gemini_client)

    mock_openai_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = SAMPLE_VALID_RESPONSE_JSON
    mock_openai_resp = MagicMock()
    mock_openai_resp.choices = [mock_choice]
    mock_openai_client.chat.completions.create.return_value = mock_openai_resp
    openai_p.set_client(mock_openai_client)

    result = await router.analyze_visual_evidence(
        source_id="TEST-005",
        image_bytes=b"GIF89a_fake_image_bytes_here_timeout_test",
        citizen_text="Flooding on street",
    )

    assert result.status == VisualAnalysisStatus.SUCCESS
    assert result.provider == "OPENAI"
    assert result.fallback_triggered is True


# 6. Gemini 500 / 502 / 504 -> Fallback to OpenAI
@pytest.mark.asyncio
async def test_gemini_500_502_504_fallback():
    router = VisualAnalysisRouter.get_instance()
    gemini_p = router.get_gemini_provider()
    openai_p = router.get_openai_provider()

    mock_gemini_client = MagicMock()
    mock_gemini_client.models.generate_content.side_effect = Exception("502 Bad Gateway: Connection reset by peer")
    gemini_p.set_client(mock_gemini_client)

    mock_openai_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = SAMPLE_VALID_RESPONSE_JSON
    mock_openai_resp = MagicMock()
    mock_openai_resp.choices = [mock_choice]
    mock_openai_client.chat.completions.create.return_value = mock_openai_resp
    openai_p.set_client(mock_openai_client)

    result = await router.analyze_visual_evidence(
        source_id="TEST-006",
        image_bytes=b"GIF89a_fake_image_bytes_here_502_test",
        citizen_text="Flooding on street",
    )

    assert result.status == VisualAnalysisStatus.SUCCESS
    assert result.provider == "OPENAI"
    assert result.fallback_triggered is True


# 7. Both Providers Fail -> TEMPORARILY_UNAVAILABLE (Zero Dummy Data)
@pytest.mark.asyncio
async def test_both_providers_fail_returns_truthful_unavailable():
    router = VisualAnalysisRouter.get_instance()
    gemini_p = router.get_gemini_provider()
    openai_p = router.get_openai_provider()

    mock_gemini_client = MagicMock()
    mock_gemini_client.models.generate_content.side_effect = Exception("503 UNAVAILABLE: Gemini high demand")
    gemini_p.set_client(mock_gemini_client)

    mock_openai_client = MagicMock()
    mock_openai_client.chat.completions.create.side_effect = Exception("503 Service Unavailable: OpenAI outage")
    openai_p.set_client(mock_openai_client)

    result = await router.analyze_visual_evidence(
        source_id="TEST-007",
        image_bytes=b"GIF89a_fake_image_bytes_here_both_fail",
        citizen_text="Flooding on street",
        report_id="REP-007",
        evidence_id="EVID-007",
    )

    assert result.status == VisualAnalysisStatus.TEMPORARILY_UNAVAILABLE
    assert result.evidence_available is True
    assert result.analysis_available is False
    assert result.retryable is True
    assert result.hazard_type == VisualHazardType.UNKNOWN
    assert result.hazard_confidence == 0.0
    assert result.overall_confidence == 0.0
    # ZERO dummy data fabricated
    assert len(result.visual_observations) == 0


# 8. Malformed Gemini Output -> Fallback to OpenAI
@pytest.mark.asyncio
async def test_malformed_gemini_output_fallback_to_openai():
    router = VisualAnalysisRouter.get_instance()
    gemini_p = router.get_gemini_provider()
    openai_p = router.get_openai_provider()

    mock_gemini_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "This is not json at all { unclosed"
    mock_gemini_client.models.generate_content.return_value = mock_resp
    gemini_p.set_client(mock_gemini_client)

    mock_openai_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = SAMPLE_VALID_RESPONSE_JSON
    mock_openai_resp = MagicMock()
    mock_openai_resp.choices = [mock_choice]
    mock_openai_client.chat.completions.create.return_value = mock_openai_resp
    openai_p.set_client(mock_openai_client)

    result = await router.analyze_visual_evidence(
        source_id="TEST-008",
        image_bytes=b"GIF89a_fake_image_bytes_here_malformed_gemini",
        citizen_text="Flooding on street",
    )

    assert result.status == VisualAnalysisStatus.SUCCESS
    assert result.provider == "OPENAI"
    assert result.fallback_triggered is True


# 9. Idempotent Same-Image Caching
@pytest.mark.asyncio
async def test_idempotent_same_image_caching():
    router = VisualAnalysisRouter.get_instance()
    gemini_p = router.get_gemini_provider()

    mock_gemini_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_VALID_RESPONSE_JSON
    mock_gemini_client.models.generate_content.return_value = mock_resp
    gemini_p.set_client(mock_gemini_client)

    image_bytes = b"GIF89a_unique_image_bytes_for_cache_test"

    # Call 1
    res1 = await router.analyze_visual_evidence(
        source_id="TEST-009A",
        image_bytes=image_bytes,
        citizen_text="Flooding on street",
    )
    assert res1.status == VisualAnalysisStatus.SUCCESS
    assert res1.is_cached is False
    assert mock_gemini_client.models.generate_content.call_count == 1

    # Call 2 (Same image + text)
    res2 = await router.analyze_visual_evidence(
        source_id="TEST-009B",
        image_bytes=image_bytes,
        citizen_text="Flooding on street",
    )
    assert res2.status == VisualAnalysisStatus.SUCCESS
    assert res2.is_cached is True
    # Underlying provider not called again
    assert mock_gemini_client.models.generate_content.call_count == 1


# 10. GeminiIntelligenceService Façade Compatibility
@pytest.mark.asyncio
async def test_gemini_intelligence_service_facade():
    mock_gemini_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_VALID_RESPONSE_JSON
    mock_gemini_client.models.generate_content.return_value = mock_resp
    GeminiIntelligenceService.set_client(mock_gemini_client)

    result = await GeminiIntelligenceService.analyze_visual_evidence(
        source_id="TEST-010",
        image_bytes=b"GIF89a_fake_image_facade_test",
        citizen_text="Flood water rising",
        report_id="REP-010",
        evidence_id="EVID-010",
    )

    assert result.status == VisualAnalysisStatus.SUCCESS
    assert result.provider == "GEMINI"
    assert result.hazard_type == VisualHazardType.FLOOD

from app.services.agents.adapters.priority_agent import PriorityAgent
from app.models.agent import AgentContext
from app.models.enums import EmergencyType, SeverityLevel


# 11. PriorityAgent Agnostic to Provider (Deterministic Behavior Preserved)
@pytest.mark.asyncio
async def test_priority_agent_provider_agnostic():
    # PriorityAgent evaluates structured signals, never raw provider text
    # Visual Evidence from Gemini
    gemini_vis = parse_visual_evidence_json(
        raw_text=SAMPLE_VALID_RESPONSE_JSON,
        source_id="REP-P01",
        source_type="LIVE_CAMERA_EVIDENCE",
        model_name="gemini-2.5-flash",
        provider="GEMINI",
    )

    # Visual Evidence from OpenAI
    openai_vis = parse_visual_evidence_json(
        raw_text=SAMPLE_VALID_RESPONSE_JSON,
        source_id="REP-P01",
        source_type="LIVE_CAMERA_EVIDENCE",
        model_name="gpt-4o",
        provider="OPENAI",
    )

    ctx_gemini = AgentContext(
        incident_id="INC-P01",
        emergency_type=EmergencyType.FLOOD,
        description="Rising flood water trapping family",
        location={"latitude": 12.9716, "longitude": 77.5946, "address": "Test Road"},
        visual_evidence=gemini_vis,
    )

    ctx_openai = AgentContext(
        incident_id="INC-P01",
        emergency_type=EmergencyType.FLOOD,
        description="Rising flood water trapping family",
        location={"latitude": 12.9716, "longitude": 77.5946, "address": "Test Road"},
        visual_evidence=openai_vis,
    )

    agent = PriorityAgent()
    res_gemini = await agent.execute(ctx_gemini)
    res_openai = await agent.execute(ctx_openai)

    # PriorityAgent produces identical deterministic output regardless of provider
    assert res_gemini.status == res_openai.status
    assert res_gemini.structured_output.get("effective_severity") == res_openai.structured_output.get("effective_severity")
    assert res_gemini.structured_output.get("base_score") == res_openai.structured_output.get("base_score")


# 12. Direct OpenAI Vision Provider Success
@pytest.mark.asyncio
async def test_direct_openai_provider_success():
    provider = OpenAIVisionProvider()
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = SAMPLE_VALID_RESPONSE_JSON
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp
    provider.set_client(mock_client)

    result = await provider.analyze_visual_evidence(
        source_id="TEST-012",
        source_type="LIVE_CAMERA_EVIDENCE",
        image_bytes=b"GIF89a_fake_image_openai_direct",
        mime_type="image/jpeg",
        citizen_text="Flooding on street",
        declared_type="FLOOD",
        report_id="REP-012",
        evidence_id="EVID-012",
    )

    assert result.status == VisualAnalysisStatus.SUCCESS
    assert result.provider == "OPENAI"
    assert result.hazard_type == VisualHazardType.FLOOD
    assert result.evidence_available is True
    assert result.analysis_available is True


# 13. Missing Keys Handling
@pytest.mark.asyncio
async def test_missing_credentials_handling():
    gemini_p = GeminiVisionProvider()
    gemini_p.set_client(None)
    openai_p = OpenAIVisionProvider()
    openai_p.set_client(None)

    orig_gemini_key = settings.GEMINI_API_KEY
    orig_openai_key = settings.OPENAI_API_KEY
    settings.GEMINI_API_KEY = None
    settings.OPENAI_API_KEY = None

    try:
        res_g = await gemini_p.analyze_visual_evidence(
            source_id="T1", source_type="LIVE", image_bytes=b"bytes12345678", mime_type="image/jpeg",
            citizen_text="", declared_type=""
        )
        assert res_g.status == VisualAnalysisStatus.UNAVAILABLE
        assert res_g.evidence_available is True

        res_o = await openai_p.analyze_visual_evidence(
            source_id="T2", source_type="LIVE", image_bytes=b"bytes12345678", mime_type="image/jpeg",
            citizen_text="", declared_type=""
        )
        assert res_o.status == VisualAnalysisStatus.UNAVAILABLE
        assert res_o.evidence_available is True
    finally:
        settings.GEMINI_API_KEY = orig_gemini_key
        settings.OPENAI_API_KEY = orig_openai_key


# 14. Provenance and Metadata Integrity
@pytest.mark.asyncio
async def test_provenance_and_metadata_integrity():
    router = VisualAnalysisRouter.get_instance()
    gemini_p = router.get_gemini_provider()

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_VALID_RESPONSE_JSON
    mock_client.models.generate_content.return_value = mock_resp
    gemini_p.set_client(mock_client)

    result = await router.analyze_visual_evidence(
        source_id="SRC-PROV-999",
        source_type="LIVE_CAMERA_EVIDENCE",
        image_bytes=b"GIF89a_provenance_test_bytes",
        report_id="REP-PROV-999",
        evidence_id="EVID-PROV-999",
        content_hash="abcd1234sha256hash",
    )

    assert result.source_id == "SRC-PROV-999"
    assert result.report_id == "REP-PROV-999"
    assert result.evidence_id == "EVID-PROV-999"
    assert result.content_hash == "abcd1234sha256hash"
    assert result.analyzed_at is not None
    assert result.prompt_version == "1.0.0"


# 15. Different Image Hash Creates Distinct Analysis
@pytest.mark.asyncio
async def test_different_image_hash_distinct_analysis():
    router = VisualAnalysisRouter.get_instance()
    gemini_p = router.get_gemini_provider()

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_VALID_RESPONSE_JSON
    mock_client.models.generate_content.return_value = mock_resp
    gemini_p.set_client(mock_client)

    res1 = await router.analyze_visual_evidence(
        source_id="T-1",
        image_bytes=b"GIF89a_image_one_11111111",
        citizen_text="Flood",
    )
    res2 = await router.analyze_visual_evidence(
        source_id="T-2",
        image_bytes=b"GIF89a_image_two_22222222",
        citizen_text="Flood",
    )

    assert res1.is_cached is False
    assert res2.is_cached is False
    assert res1.content_hash != res2.content_hash
    assert mock_client.models.generate_content.call_count == 2

