import asyncio
import os
import sys

# Ensure app is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.services.text_analysis_router import TextAnalysisRouter, OpenAITextProvider
from app.models.llm_extraction import ExtractionStatus


async def run_live_test():
    print("=" * 60)
    print("LIVE OPENAI TEXT EXTRACTION CONNECTIVITY TEST")
    print("=" * 60)

    if not settings.OPENAI_API_KEY:
        print("[STATUS] OPENAI_API_KEY is NOT configured in .env.")
        print("[RESULT] LIVE OPENAI TEXT CONNECTIVITY: NOT TESTED (No API Key)")
        return

    # Redact key in logs for security
    key_preview = f"{settings.OPENAI_API_KEY[:6]}...{settings.OPENAI_API_KEY[-4:]}"
    print(f"[CONFIG] OpenAI API Key detected: {key_preview}")
    print(f"[CONFIG] Target Model: {settings.OPENAI_TEXT_MODEL}")

    provider = OpenAITextProvider()
    test_text = (
        "Tenali road flooded near government hospital. 15 people stuck including 2 infants and 1 pregnant woman. "
        "Need clean drinking water and 1 rescue boat urgently. Road is completely submerged under 4 feet water."
    )

    print("\n[STEP 1] Executing live extraction against OpenAI Text Provider...")
    result = await provider.extract_structured_evidence(
        source_id="LIVE-CONNECTIVITY-TEST-001",
        source_type="CITIZEN_REPORT",
        text_content=test_text,
        context_metadata={"emergency_type": "Flood", "location_address": "Tenali Road"},
    )

    print(f"[STEP 2] Extraction completed. Status: {result.status}")
    print(f"  - Provider: {result.provider}")
    print(f"  - Model: {result.model}")
    print(f"  - Overall Confidence: {result.overall_confidence}")
    if result.hazard:
        print(f"  - Extracted Hazard: {result.hazard.value} (Confidence: {result.hazard.confidence})")
    if result.affected_population:
        print(f"  - Affected Population: {result.affected_population.estimated_count} (Uncertain: {result.affected_population.is_uncertain})")
    print(f"  - Vulnerable Groups Extracted: {[f'{vg.estimated_count or 0} {vg.group_type}' for vg in result.vulnerable_groups]}")
    needs_list = [f"{n.need_type} ({n.suggested_quantity or 0} {n.unit or ''}) [{n.urgency}]" for n in result.reported_needs]
    print(f"  - Reported Needs Extracted: {needs_list}")
    infra_list = [f"{ic.infrastructure_type}: {ic.status}" for ic in result.infrastructure_conditions]
    print(f"  - Infrastructure Conditions: {infra_list}")

    if result.status == ExtractionStatus.SUCCESS:
        print("\n[RESULT] LIVE OPENAI TEXT CONNECTIVITY: PASS")
    else:
        print(f"\n[RESULT] LIVE OPENAI TEXT CONNECTIVITY: FAILED ({result.error_message})")


if __name__ == "__main__":
    asyncio.run(run_live_test())
