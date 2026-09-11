from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.models.enums import (
    OperationalDomain,
    AgentName,
    SeverityLevel,
    ResourceType,
    CoordinationPlanStatus,
)
from app.models.agent import CoordinationPlan
from app.models.monitoring import ChangeImpactResult, PlanDiffResult


class ScenarioType(str, Enum):
    RESOURCE_QUANTITY_REDUCTION = "RESOURCE_QUANTITY_REDUCTION"
    RESOURCE_REDUCTION = "RESOURCE_QUANTITY_REDUCTION"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"
    SUPPLY_DEPLETED = "RESOURCE_UNAVAILABLE"
    DEMAND_SURGE = "DEMAND_SURGE"
    SHELTER_CAPACITY_REDUCTION = "SHELTER_CAPACITY_REDUCTION"
    SHELTER_UNAVAILABLE = "SHELTER_UNAVAILABLE"
    FACILITY_OFFLINE = "FACILITY_OFFLINE"
    HEALTHCARE_CAPACITY_REDUCTION = "HEALTHCARE_CAPACITY_REDUCTION"
    HEALTHCARE_FACILITY_UNAVAILABLE = "HEALTHCARE_FACILITY_UNAVAILABLE"
    VOLUNTEER_UNAVAILABLE = "VOLUNTEER_UNAVAILABLE"
    VOLUNTEER_DROPOUT = "VOLUNTEER_UNAVAILABLE"
    VOLUNTEER_SHORTAGE = "VOLUNTEER_SHORTAGE"
    VEHICLE_UNAVAILABLE = "VEHICLE_UNAVAILABLE"
    ROUTE_BLOCKED = "ROUTE_BLOCKED"
    SITUATION_SEVERITY_CHANGE = "SITUATION_SEVERITY_CHANGE"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            val_norm = value.strip().upper()
            mapping = {
                "RESOURCE_REDUCTION": cls.RESOURCE_QUANTITY_REDUCTION,
                "DEMAND_SURGE": cls.RESOURCE_QUANTITY_REDUCTION,
                "FACILITY_OFFLINE": cls.SHELTER_UNAVAILABLE,
                "VOLUNTEER_DROPOUT": cls.VOLUNTEER_UNAVAILABLE,
                "SUPPLY_DEPLETED": cls.RESOURCE_UNAVAILABLE,
            }
            if val_norm in mapping:
                return mapping[val_norm]
            for member in cls:
                if member.value == val_norm or member.name == val_norm:
                    return member
        return None


class SimulationStatus(str, Enum):
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DISCARDED = "DISCARDED"
    STALE = "STALE"
    EXPIRED = "EXPIRED"


class SimulationScenario(BaseModel):
    """
    Typed definition of a single what-if change within a simulation.
    Must reference a real, existing target entity in the database.
    """
    scenario_id: str
    scenario_type: ScenarioType
    target_entity_type: str  # "RESOURCE", "SHELTER", "HEALTHCARE", "VOLUNTEER", "TRANSPORT", "ROUTE", "SITUATION"
    target_entity_id: str
    target_entity_name: str
    change_type: str
    previous_value: Any
    simulated_value: Any
    affected_fields: List[str] = Field(default_factory=list)
    location: Optional[Dict[str, Any]] = None
    title: Optional[str] = None
    description: str
    target_domain: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SimulationRun(BaseModel):
    """
    Authoritative document for an isolated simulation run stored in `simulations`.
    Never mutates real MongoDB operational collections.
    """
    simulation_id: str
    simulation_name: str
    situation_id: str
    situation_name: str
    baseline_plan_id: str
    baseline_plan_version: int
    baseline_fingerprint: str
    scenarios: List[SimulationScenario] = Field(default_factory=list)
    status: SimulationStatus = SimulationStatus.DRAFT
    is_simulation: bool = True
    created_by_id: str
    created_by_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    impact_summary: Optional[ChangeImpactResult] = None
    result_plan: Optional[CoordinationPlan] = None
    diff_result: Optional[PlanDiffResult] = None
    simulation_explanation: Optional[str] = None
    state_fingerprint: Optional[str] = None
    error_message: Optional[str] = None


class CreateSimulationRequest(BaseModel):
    situation_id: str
    simulation_name: Optional[str] = None


class AddScenarioRequest(BaseModel):
    scenario_type: ScenarioType
    target_entity_type: str
    target_entity_id: str
    simulated_value: Any
    title: Optional[str] = None
    description: Optional[str] = None
    target_domain: Optional[str] = None
    target_entity_name: Optional[str] = None


class SimulationEntityTarget(BaseModel):
    entity_id: str
    entity_name: str
    name: Optional[str] = None
    entity_type: str  # "RESOURCE", "SHELTER", "HEALTHCARE", "VOLUNTEER", "TRANSPORT", "ROUTE", "SITUATION"
    current_value: Any
    available_capacity_or_quantity: Optional[Any] = None
    unit: Optional[str] = None
    unit_or_type: Optional[str] = None
    status: Optional[str] = None
    location_summary: Optional[str] = None
    location_name: Optional[str] = None
    coordinates: Optional[Dict[str, float]] = None


class SimulationTargetLookupResponse(BaseModel):
    situation_id: str
    situation_name: str
    baseline_plan_id: str
    baseline_plan_version: int
    baseline_plan_status: Optional[str] = None
    baseline_plan_activated_at: Optional[str] = None
    has_active_baseline: bool = False
    resources: List[SimulationEntityTarget] = Field(default_factory=list)
    shelters: List[SimulationEntityTarget] = Field(default_factory=list)
    healthcare_facilities: List[SimulationEntityTarget] = Field(default_factory=list)
    healthcare: List[SimulationEntityTarget] = Field(default_factory=list)
    volunteers: List[SimulationEntityTarget] = Field(default_factory=list)
    transports: List[SimulationEntityTarget] = Field(default_factory=list)
    routes: List[SimulationEntityTarget] = Field(default_factory=list)
    situation_severities: List[str] = Field(default_factory=lambda: ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
    total_count: int = 0


class RunSimulationResponse(BaseModel):
    success: bool
    simulation_id: str
    status: SimulationStatus
    baseline_plan_id: str
    simulated_plan_id: Optional[str] = None
    total_changes: int = 0
    impact_level: str = "NONE"
    explanation: Optional[str] = None
    diff_result: Optional[PlanDiffResult] = None
    is_simulation: bool = True
