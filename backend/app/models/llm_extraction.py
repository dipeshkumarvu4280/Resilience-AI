from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, Field


class ExtractionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_EXTRACTED = "NOT_EXTRACTED"
    FAILED = "FAILED"


class ExtractedHazard(BaseModel):
    value: str = Field(..., description="Inferred hazard/emergency type (e.g. Flood, Fire, Building Collapse)")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = "LLM_EXTRACTION"
    excerpt: Optional[str] = Field(None, description="Direct text quote/excerpt supporting this extraction")


class ExtractedObservation(BaseModel):
    type: str = Field(..., description="Normalized observation type (e.g. WATER_ENTERED_RESIDENCE, ROAD_BLOCKED, POWER_OUTAGE)")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = "LLM_EXTRACTION"
    excerpt: Optional[str] = None


class ExtractedAffectedPopulation(BaseModel):
    estimated_count: Optional[int] = Field(None, ge=0, description="Estimated number of affected individuals if stated")
    is_uncertain: bool = Field(default=False, description="True if citizen expressed uncertainty (e.g. 'maybe 50', 'around 20')")
    uncertainty_phrase: Optional[str] = Field(None, description="Original uncertainty qualifier (e.g. 'approx', 'around', 'maybe')")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = "LLM_EXTRACTION"


class ExtractedVulnerableGroup(BaseModel):
    group_type: str = Field(..., description="Type of vulnerable group (e.g. ELDERLY, CHILDREN, INFANTS, DISABLED, PREGNANT)")
    estimated_count: Optional[int] = Field(None, ge=0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    excerpt: Optional[str] = None
    source: str = "LLM_EXTRACTION"


class ExtractedNeed(BaseModel):
    need_type: str = Field(..., description="Reported relief requirement (e.g. DRINKING_WATER, FOOD, MEDICAL_KITS, BOATS, SHELTER)")
    suggested_quantity: Optional[float] = Field(None, ge=0.0)
    unit: Optional[str] = Field(None, description="Reported unit (e.g. Liters, Packets, Persons)")
    urgency: str = Field(default="MEDIUM", description="Inferred urgency (LOW, MEDIUM, HIGH, CRITICAL)")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    excerpt: Optional[str] = None
    source: str = "LLM_EXTRACTION"


class ExtractedMedicalIndicator(BaseModel):
    condition: str = Field(..., description="Reported trauma or medical condition (e.g. INJURED, BURN, UNCONSCIOUS, FRACTURE)")
    casualty_count: Optional[int] = Field(None, ge=0)
    is_critical: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    excerpt: Optional[str] = None
    source: str = "LLM_EXTRACTION"


class ExtractedInfrastructureCondition(BaseModel):
    infrastructure_type: str = Field(..., description="Asset type (e.g. ROAD, BRIDGE, POWER_GRID, WATER_LINE)")
    status: str = Field(..., description="Reported condition (e.g. BLOCKED, COLLAPSED, SUBMERGED, DAMAGED, OPERATIONAL)")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    excerpt: Optional[str] = None
    source: str = "LLM_EXTRACTION"


class ExtractedLanguage(BaseModel):
    code: str = Field(default="en", description="ISO 639-1 language code (e.g. te, hi, en, ta, kn, mr, bn, gu, ml, pa, ur, mixed)")
    name: str = Field(default="English", description="Human-readable language name (e.g. Telugu, Hindi, English, Tamil, etc.)")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    is_mixed: bool = Field(default=False, description="True if text combines multiple languages")
    source: str = "LLM_EXTRACTION"


def generate_extraction_id() -> str:
    return f"EXT-{uuid.uuid4().hex[:10].upper()}"


class LLMExtractionResult(BaseModel):
    """
    Strongly typed container for LLM unstructured text extraction results.
    Strictly advisory. Never makes autonomous operational decisions.
    Preserves complete provenance, uncertainty indicators, and missing-value semantics.
    """
    extraction_id: str = Field(default_factory=generate_extraction_id)
    source_type: str = "CITIZEN_REPORT"
    source_id: str
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model: str = "gemini-2.5-flash"
    prompt_version: str = "1.0.0"
    status: ExtractionStatus = ExtractionStatus.SUCCESS

    # Extracted structured dimensions
    detected_language: Optional[ExtractedLanguage] = None
    hazard: Optional[ExtractedHazard] = None
    observations: List[ExtractedObservation] = Field(default_factory=list)
    affected_population: Optional[ExtractedAffectedPopulation] = None
    vulnerable_groups: List[ExtractedVulnerableGroup] = Field(default_factory=list)
    reported_needs: List[ExtractedNeed] = Field(default_factory=list)
    medical_indicators: List[ExtractedMedicalIndicator] = Field(default_factory=list)
    infrastructure_conditions: List[ExtractedInfrastructureCondition] = Field(default_factory=list)
    mentioned_landmarks: List[str] = Field(default_factory=list)
    temporal_references: List[str] = Field(default_factory=list)
    textual_location_reference: Optional[str] = None

    # Quality & Provenance
    uncertainty_detected: bool = False
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    is_cached: bool = False
    provider: str = "GEMINI"
    fallback_used: bool = False
    primary_provider: Optional[str] = "GEMINI"
    primary_provider_error: Optional[str] = None
    error_classification: Optional[str] = None
    retryable: bool = False

    @classmethod
    def unavailable(cls, source_id: str, source_type: str = "CITIZEN_REPORT", reason: str = "LLM service unavailable") -> "LLMExtractionResult":
        """Fail-safe factory when LLM is unconfigured, timed out, or unavailable."""
        return cls(
            extraction_id=generate_extraction_id(),
            source_type=source_type,
            source_id=source_id,
            status=ExtractionStatus.UNAVAILABLE,
            overall_confidence=0.0,
            warnings=[f"AI interpretation unavailable: {reason}"],
            error_message=reason,
        )

    @classmethod
    def temporarily_unavailable(
        cls,
        source_id: str,
        reason: str = "AI text analysis temporarily unavailable",
        source_type: str = "CITIZEN_REPORT",
        error_classification: Optional[str] = None,
        model: str = "gemini-2.5-flash",
        provider: str = "GEMINI",
        fallback_used: bool = False,
        primary_provider_error: Optional[str] = None,
        fallback_provider: Optional[str] = None,
    ) -> "LLMExtractionResult":
        """Fail-safe factory when all LLM providers (Primary and Fallback) are temporarily unavailable."""
        return cls(
            extraction_id=generate_extraction_id(),
            source_type=source_type,
            source_id=source_id,
            status=ExtractionStatus.UNAVAILABLE,
            overall_confidence=0.0,
            warnings=[f"AI interpretation temporarily unavailable: {reason}"],
            error_message=reason,
            error_classification=error_classification,
            model=model,
            provider=provider,
            fallback_used=fallback_used,
            primary_provider="GEMINI",
            primary_provider_error=primary_provider_error,
            retryable=True,
        )

    @classmethod
    def failed(cls, source_id: str, source_type: str = "CITIZEN_REPORT", error: str = "Extraction validation failed") -> "LLMExtractionResult":
        """Fail-safe factory when LLM returns unparseable or invalid schema."""
        return cls(
            extraction_id=generate_extraction_id(),
            source_type=source_type,
            source_id=source_id,
            status=ExtractionStatus.FAILED,
            overall_confidence=0.0,
            warnings=[f"AI extraction parsing failed: {error}"],
            error_message=error,
        )
