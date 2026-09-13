from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.predictive import (
    PredictiveFeature,
    PredictiveEvidenceItem,
    ForecastHorizonResult,
    IncidentPredictionResponse,
)


from app.models.weather import WeatherEvidence


class RawIncidentData(BaseModel):
    """
    Normalized container holding all genuine database records extracted for an incident.
    """
    incident_id: str
    is_situation: bool
    situation_doc: Optional[Dict[str, Any]] = None
    report_docs: List[Dict[str, Any]] = Field(default_factory=list)
    sensor_docs: List[Dict[str, Any]] = Field(default_factory=list)
    sensor_readings: List[Dict[str, Any]] = Field(default_factory=list)
    sensor_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    field_verifications: List[Dict[str, Any]] = Field(default_factory=list)
    monitoring_events: List[Dict[str, Any]] = Field(default_factory=list)
    change_impacts: List[Dict[str, Any]] = Field(default_factory=list)
    response_tasks: List[Dict[str, Any]] = Field(default_factory=list)
    weather_evidence: Optional[WeatherEvidence] = None
    window_start: datetime
    window_end: datetime
    window_minutes: int


class ExtractedFeatureSet(BaseModel):
    """
    Extracted deterministic feature set with provenance and sufficiency metrics.
    """
    features: List[PredictiveFeature] = Field(default_factory=list)
    feature_dict: Dict[str, float] = Field(default_factory=dict)
    missing_features: List[str] = Field(default_factory=list)
    evidence_items: List[PredictiveEvidenceItem] = Field(default_factory=list)
    data_points_used: Dict[str, int] = Field(default_factory=dict)
    total_data_points: int = 0
    independent_sources_count: int = 0
    independent_physical_sources_count: int = 0
    external_context_sources_count: int = 0
    weather_evidence: Optional[WeatherEvidence] = None
    data_status: str = "INSUFFICIENT_DATA"
    limitations: List[str] = Field(default_factory=list)


class PredictiveFeatureProvider(ABC):
    """
    Abstract interface for feature extraction providers.
    Allows Phase 1 deterministic feature extraction and future Phase 2 multimodal/external providers.
    """

    @abstractmethod
    async def extract_features(
        self,
        raw_data: RawIncidentData,
    ) -> ExtractedFeatureSet:
        pass


class PredictiveModel(ABC):
    """
    Abstract interface for prediction models.
    Supports Phase 1 DeterministicPredictor and future Phase 2 ML / Time-Series Predictors.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        pass

    @abstractmethod
    def predict_horizon(
        self,
        horizon_minutes: int,
        feature_set: ExtractedFeatureSet,
        raw_data: RawIncidentData,
    ) -> ForecastHorizonResult:
        pass
