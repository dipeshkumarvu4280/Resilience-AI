from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.models.enums import (
    AgentName,
    AgentRunStatus,
    CoordinationPlanStatus,
    PlanReviewAction,
    SeverityLevel,
    NeedUrgency,
    ResourceType,
    ConflictType,
    ShelterConflictType,
    ResolutionStrategy,
    ConflictStatus,
)


class AgentContext(BaseModel):
    """
    Standardized execution context supplied to each registered agent.
    Contains situation data, member reports, inventory state, and officer decisions.
    """
    situation_id: str = "SIT-DEFAULT"
    situation_title: str = "Emergency Situation"
    emergency_type: str = "OTHER"
    description: str = ""
    location_summary: str = "Incident Area"
    center_latitude: Optional[float] = None
    center_longitude: Optional[float] = None
    report_count: int = 1
    member_report_ids: List[str] = Field(default_factory=list)
    officer_severity_override: Optional[SeverityLevel] = None
    existing_needs: List[Dict[str, Any]] = Field(default_factory=list)
    available_resources: List[Dict[str, Any]] = Field(default_factory=list)
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None
    state_fingerprint: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    """
    Strictly typed, validated result produced by every agent.
    """
    agent_name: AgentName
    run_id: str
    status: AgentRunStatus
    recommendation: str
    structured_output: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    evidence: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class AgentRunRecord(BaseModel):
    """
    Persistent document tracking each agent run in MongoDB collection `ai_agent_runs`.
    """
    run_id: str
    situation_id: str
    agent_name: AgentName
    agent_version: str = "1.0.0"
    status: AgentRunStatus
    state_fingerprint: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    input_summary: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[AgentResult] = None
    confidence: float = 1.0
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None


class PlanRecommendedResource(BaseModel):
    """
    Individual matched resource recommendation within a Coordination Plan.
    """
    resource_type: ResourceType
    quantity_required: float
    unit: str
    urgency: NeedUrgency
    matched_resource_id: Optional[str] = None
    matched_resource_name: Optional[str] = None
    available_in_inventory: Optional[float] = None
    allocated_quantity: Optional[float] = None
    depot_location: Optional[str] = None
    distance_km: Optional[float] = None
    reasoning: Optional[str] = None


class DetectedConflict(BaseModel):
    """
    Explicit coordination conflict detected by the Conflict Resolution Agent.
    """
    conflict_id: str
    conflict_type: ConflictType
    severity: SeverityLevel
    description: str
    affected_need: Optional[str] = None
    affected_resource: Optional[str] = None
    detected_quantity: Optional[float] = None
    available_quantity: Optional[float] = None
    shortfall: Optional[float] = None
    resolution_strategy: Optional[ResolutionStrategy] = None
    resolution_status: ConflictStatus = ConflictStatus.UNRESOLVED
    officer_attention_required: bool = True
    explanation: str
    alternative_options: List[str] = Field(default_factory=list)


class ConflictResolutionSummary(BaseModel):
    """
    Composite conflict resolution intelligence embedded within the Coordination Plan.
    """
    conflicts_detected: List[DetectedConflict] = Field(default_factory=list)
    conflicts_count: int = 0
    resolved_conflicts: int = 0
    unresolved_conflicts: int = 0
    resolution_actions: List[str] = Field(default_factory=list)
    affected_needs: List[str] = Field(default_factory=list)
    affected_resources: List[str] = Field(default_factory=list)
    shortages: List[Dict[str, Any]] = Field(default_factory=list)
    officer_attention_required: bool = False
    explanation: str = "No coordination conflicts detected."
    confidence: float = 1.0
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    agent_version: str = "1.0.0"


class RecommendedShelter(BaseModel):
    """
    Individual matched emergency shelter facility recommendation within a Coordination Plan.
    """
    shelter_id: str
    shelter_name: str
    distance_km: float
    total_capacity: float
    current_occupancy: float
    remaining_capacity: float
    recommended_occupancy: float
    coverage_percentage: float
    suitability_score: float
    ranking_factors: Dict[str, float] = Field(default_factory=dict)
    recommendation_reason: str
    location_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: str = "AVAILABLE"
    accessibility: Optional[str] = None


class ShelterCoordinationSummary(BaseModel):
    """
    Composite emergency shelter intelligence embedded within the Coordination Plan.
    """
    shelter_required: bool = False
    requirement_reason: str = "SHELTER_NOT_REQUIRED"
    affected_population: Optional[int] = None
    population_confidence: float = 1.0
    shelters_evaluated: int = 0
    shelters_recommended: List[RecommendedShelter] = Field(default_factory=list)
    total_capacity_available: float = 0.0
    total_population_covered: float = 0.0
    total_shortfall: float = 0.0
    conflicts: List[str] = Field(default_factory=list)
    officer_attention_required: bool = False
    explanation: str = "Shelter coordination evaluation completed."
    confidence: float = 1.0
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    agent_version: str = "1.0.0"


class RecommendedHealthcareFacility(BaseModel):
    """
    Individual recommended healthcare/hospital facility within a Coordination Plan.
    """
    facility_id: str
    facility_name: str
    facility_type: str = "Hospital"
    distance_km: float
    total_beds: float = 0.0
    available_beds: float = 0.0
    allocated_patients: float = 0.0
    coverage_percentage: float = 100.0
    icu_available: int = 0
    oxygen_available: bool = True
    trauma_capable: bool = True
    emergency_capable: bool = True
    suitability_score: float = 100.0
    ranking_factors: Dict[str, float] = Field(default_factory=dict)
    recommendation_reason: str
    location_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: str = "AVAILABLE"


class HealthcareCoordinationSummary(BaseModel):
    """
    Composite medical & healthcare intelligence embedded within the Coordination Plan.
    """
    medical_required: bool = False
    requirement_reason: str = "MEDICAL_NOT_REQUIRED"
    estimated_casualties: Optional[int] = None
    casualty_confidence: float = 1.0
    facilities_evaluated: int = 0
    facilities_recommended: List[RecommendedHealthcareFacility] = Field(default_factory=list)
    total_beds_available: float = 0.0
    total_patients_covered: float = 0.0
    total_shortfall: float = 0.0
    conflicts: List[str] = Field(default_factory=list)
    officer_attention_required: bool = False
    explanation: str = "Healthcare coordination evaluation completed."
    confidence: float = 1.0
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    agent_version: str = "1.0.0"


class RecommendedVolunteerAssignment(BaseModel):
    """
    Individual recommended field volunteer assignment within a Coordination Plan.
    """
    volunteer_id: str
    volunteer_name: str
    role_or_skill: str
    assigned_operation: str
    location_zone: Optional[str] = None
    distance_km: Optional[float] = None
    suitability_score: float = 100.0
    availability_status: str = "Available Immediately"
    recommendation_reason: str
    phone: Optional[str] = None


class VolunteerCoordinationSummary(BaseModel):
    """
    Composite volunteer & field responder intelligence embedded within the Coordination Plan.
    """
    volunteers_required: bool = False
    requirement_reason: str = "VOLUNTEER_NOT_REQUIRED"
    estimated_volunteers_needed: int = 0
    volunteers_evaluated: int = 0
    volunteers_recommended: List[RecommendedVolunteerAssignment] = Field(default_factory=list)
    total_volunteers_assigned: int = 0
    total_available: int = 0
    total_volunteers_available: int = 0
    total_shortfall: int = 0
    conflicts: List[str] = Field(default_factory=list)
    officer_attention_required: bool = False
    explanation: str = "Volunteer coordination evaluation completed."
    confidence: float = 1.0
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    agent_version: str = "1.0.0"


class RecommendedTransport(BaseModel):
    """
    Individual vehicle / transport unit matched for logistical or evacuation operations.
    """
    transport_id: str
    vehicle_name: str
    vehicle_type: str
    capacity: float
    allocated_load_or_passengers: float
    current_status: str = "AVAILABLE"
    location_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    assigned_mission: str
    recommendation_reason: str


class RecommendedRoute(BaseModel):
    """
    Deterministic route waypoint vector between incident, response facilities, and depots.
    """
    route_id: str
    origin_name: str
    destination_name: str
    origin_coordinates: Dict[str, float]
    destination_coordinates: Dict[str, float]
    distance_km: float
    estimated_duration_minutes: float
    road_condition_status: str = "PASSABLE"
    transport_id: Optional[str] = None
    assigned_mission: str
    recommendation_reason: str


class RouteTransportCoordinationSummary(BaseModel):
    """
    Composite route & transport logistical intelligence embedded within the Coordination Plan.
    """
    transport_required: bool = False
    requirement_reason: str = "TRANSPORT_NOT_REQUIRED"
    routes_evaluated: int = 0
    routes_recommended: List[RecommendedRoute] = Field(default_factory=list)
    transports_recommended: List[RecommendedTransport] = Field(default_factory=list)
    total_routes_recommended: int = 0
    total_transports_available: int = 0
    total_available: int = 0
    total_vehicles_assigned: int = 0
    transport_shortfall: int = 0
    conflicts: List[str] = Field(default_factory=list)
    officer_attention_required: bool = False
    explanation: str = "Route and transport coordination evaluation completed."
    confidence: float = 1.0
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    agent_version: str = "1.0.0"


class OfficerPlanReview(BaseModel):
    """
    Audit record of the human-in-the-loop Emergency Officer decision on a Coordination Plan.
    """
    decision: PlanReviewAction
    reviewed_by_id: str
    reviewed_by_name: str
    reviewed_by_role: str
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)
    officer_notes: Optional[str] = None
    modified_fields: Optional[Dict[str, Any]] = None


class CoordinationPlan(BaseModel):
    """
    Authoritative composite coordination plan generated by the Central Orchestrator.
    Requires human Emergency Officer review before any execution.
    """
    plan_id: str
    situation_id: str
    version: int = 1
    state_fingerprint: Optional[str] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    participating_agents: List[AgentName] = Field(default_factory=list)
    agent_results: Dict[str, AgentResult] = Field(default_factory=dict)
    assessed_priority: SeverityLevel
    assessed_needs: List[Dict[str, Any]] = Field(default_factory=list)
    recommended_allocations: List[PlanRecommendedResource] = Field(default_factory=list)
    conflicts: List[DetectedConflict] = Field(default_factory=list)
    conflict_summary: Optional[ConflictResolutionSummary] = None
    recommended_shelters: List[RecommendedShelter] = Field(default_factory=list)
    shelter_summary: Optional[ShelterCoordinationSummary] = None
    recommended_facilities: List[RecommendedHealthcareFacility] = Field(default_factory=list)
    healthcare_summary: Optional[HealthcareCoordinationSummary] = None
    recommended_volunteers: List[RecommendedVolunteerAssignment] = Field(default_factory=list)
    volunteer_summary: Optional[VolunteerCoordinationSummary] = None
    recommended_transports: List[RecommendedTransport] = Field(default_factory=list)
    recommended_routes: List[RecommendedRoute] = Field(default_factory=list)
    route_summary: Optional[RouteTransportCoordinationSummary] = None
    officer_attention_required: bool = False
    has_unresolved_conflicts: bool = False
    reasoning: str
    constraints: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    status: CoordinationPlanStatus = CoordinationPlanStatus.PENDING_OFFICER_REVIEW
    officer_review: Optional[OfficerPlanReview] = None
    # Phase 6.3 & 6.4 Revision Lineage & Diff Fields
    previous_plan_id: Optional[str] = None
    previous_version: Optional[int] = None
    trigger_event_id: Optional[str] = None
    impact_id: Optional[str] = None
    is_revised_version: bool = False
    is_simulation: bool = False
    diff_summary: Optional[Dict[str, Any]] = None
    change_explanation: Optional[str] = None


# API Payload Schemas
class OrchestrateSituationRequest(BaseModel):
    force_refresh: bool = False
    notes: Optional[str] = None


class PlanReviewRequest(BaseModel):
    action: PlanReviewAction
    notes: Optional[str] = None
    modified_needs: Optional[List[Dict[str, Any]]] = None
    modified_allocations: Optional[List[PlanRecommendedResource]] = None
    modified_shelters: Optional[List[RecommendedShelter]] = None
    modified_facilities: Optional[List[RecommendedHealthcareFacility]] = None
    modified_volunteers: Optional[List[RecommendedVolunteerAssignment]] = None
    modified_transports: Optional[List[RecommendedTransport]] = None
    modified_routes: Optional[List[RecommendedRoute]] = None
