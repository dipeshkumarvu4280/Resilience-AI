from enum import Enum
from typing import Optional, List, Dict, Any, Generic, TypeVar
from datetime import datetime
from pydantic import BaseModel, Field

T = TypeVar("T")


class AnalyticsTimeRange(str, Enum):
    LAST_24_HOURS = "24h"
    LAST_7_DAYS = "7d"
    LAST_30_DAYS = "30d"
    LAST_90_DAYS = "90d"
    ALL_TIME = "all"
    CUSTOM = "custom"


class DataSufficiencyStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NO_RECORDS = "NO_RECORDS"


class BottleneckType(str, Enum):
    ACKNOWLEDGEMENT_DELAY = "ACKNOWLEDGEMENT_DELAY"
    PLANNING_DELAY = "PLANNING_DELAY"
    OFFICER_APPROVAL_DELAY = "OFFICER_APPROVAL_DELAY"
    TASK_ASSIGNMENT_DELAY = "TASK_ASSIGNMENT_DELAY"
    FIELD_RESPONSE_DELAY = "FIELD_RESPONSE_DELAY"
    TASK_EXECUTION_DELAY = "TASK_EXECUTION_DELAY"
    RESOURCE_SHORTAGE = "RESOURCE_SHORTAGE"
    SHELTER_CAPACITY_SHORTAGE = "SHELTER_CAPACITY_SHORTAGE"
    HEALTHCARE_CAPACITY_SHORTAGE = "HEALTHCARE_CAPACITY_SHORTAGE"
    VOLUNTEER_SHORTAGE = "VOLUNTEER_SHORTAGE"
    TRANSPORT_SHORTAGE = "TRANSPORT_SHORTAGE"
    ROUTE_BLOCKAGE = "ROUTE_BLOCKAGE"
    REPEATED_REPLANNING = "REPEATED_REPLANNING"


class DecisionSignalType(str, Enum):
    RESOURCE_SHORTAGE_RISK = "RESOURCE_SHORTAGE_RISK"
    SHELTER_CAPACITY_RISK = "SHELTER_CAPACITY_RISK"
    HEALTHCARE_CAPACITY_RISK = "HEALTHCARE_CAPACITY_RISK"
    VOLUNTEER_AVAILABILITY_RISK = "VOLUNTEER_AVAILABILITY_RISK"
    TRANSPORT_CONGESTION_RISK = "TRANSPORT_CONGESTION_RISK"
    REPEATED_ROUTE_DISRUPTION = "REPEATED_ROUTE_DISRUPTION"
    APPROVAL_BOTTLENECK = "APPROVAL_BOTTLENECK"
    EXECUTION_DELAY_ALERT = "EXECUTION_DELAY_ALERT"
    REPLANNING_CASCADE_WARNING = "REPLANNING_CASCADE_WARNING"
    HIGH_UNRESOLVED_POPULATION_NEED = "HIGH_UNRESOLVED_POPULATION_NEED"


class MetricValue(BaseModel, Generic[T]):
    value: Optional[T] = None
    unit: str = ""
    status: DataSufficiencyStatus = DataSufficiencyStatus.AVAILABLE
    sample_count: int = 0
    time_range: str = "all"
    reason: Optional[str] = None


class DurationDistribution(BaseModel):
    min_minutes: Optional[float] = None
    median_minutes: Optional[float] = None
    avg_minutes: Optional[float] = None
    max_minutes: Optional[float] = None
    sample_count: int = 0
    status: DataSufficiencyStatus = DataSufficiencyStatus.AVAILABLE
    reason: Optional[str] = None


class ResponseMilestoneTimeline(BaseModel):
    intake_to_acknowledgement: DurationDistribution
    acknowledgement_to_situation: DurationDistribution
    situation_to_plan_generation: DurationDistribution
    plan_generation_to_officer_approval: DurationDistribution
    approval_to_task_assignment: DurationDistribution
    assignment_to_field_start: DurationDistribution
    field_start_to_completion: DurationDistribution
    incident_creation_to_resolution: DurationDistribution
    total_samples: int = 0


class BottleneckInsight(BaseModel):
    bottleneck_type: BottleneckType
    severity: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    title: str
    description: str
    evidence: str
    delay_impact_minutes: Optional[float] = None
    affected_domain: str
    affected_situation_id: Optional[str] = None
    actionable_recommendation: str
    detected_at: datetime


class ResourceDemandCategory(BaseModel):
    category_name: str
    total_stock: float
    total_allocated: float
    total_consumed: float
    remaining_available: float
    utilization_percentage: float
    shortage_count: int
    conflict_count: int


class ResourceUtilizationAnalytics(BaseModel):
    time_range: str
    total_resources_tracked: int
    total_units_stock: float
    total_units_allocated: float
    total_units_consumed: float
    overall_utilization_rate: float
    categories: List[ResourceDemandCategory] = Field(default_factory=list)
    shortage_incidents_count: int = 0
    conflict_resolution_rate: Optional[float] = None
    status: DataSufficiencyStatus = DataSufficiencyStatus.AVAILABLE
    reason: Optional[str] = None


class ShelterAnalytics(BaseModel):
    total_shelters: int = 0
    total_capacity_beds: float = 0.0
    current_occupancy_beds: float = 0.0
    remaining_capacity_beds: float = 0.0
    occupancy_rate_percentage: float = 0.0
    full_shelters_count: int = 0
    unavailable_shelters_count: int = 0
    displaced_population_covered: float = 0.0
    unmet_shelter_demand_population: float = 0.0
    status: DataSufficiencyStatus = DataSufficiencyStatus.AVAILABLE


class HealthcareAnalytics(BaseModel):
    total_facilities: int = 0
    total_beds_available: float = 0.0
    total_beds_occupied: float = 0.0
    bed_utilization_percentage: float = 0.0
    icu_beds_available: float = 0.0
    icu_beds_occupied: float = 0.0
    patient_evacuation_demand: int = 0
    critical_triage_demand: int = 0
    healthcare_shortages_count: int = 0
    status: DataSufficiencyStatus = DataSufficiencyStatus.AVAILABLE


class VolunteerPerformanceAnalytics(BaseModel):
    registered_volunteers: int = 0
    active_responders: int = 0
    total_missions_assigned: int = 0
    missions_accepted: int = 0
    missions_in_progress: int = 0
    missions_completed: int = 0
    missions_blocked_or_failed: int = 0
    completion_rate_percentage: float = 0.0
    avg_mission_duration_minutes: Optional[float] = None
    skill_demand_breakdown: Dict[str, int] = Field(default_factory=dict)
    volunteer_shortages_count: int = 0
    status: DataSufficiencyStatus = DataSufficiencyStatus.AVAILABLE


class FleetAnalytics(BaseModel):
    total_vehicles: int = 0
    active_fleet_missions: int = 0
    completed_fleet_missions: int = 0
    blocked_routes_reported: int = 0
    fleet_utilization_rate: float = 0.0
    avg_transit_minutes: Optional[float] = None
    vehicle_conflicts_count: int = 0
    status: DataSufficiencyStatus = DataSufficiencyStatus.AVAILABLE


class ReplanningIntelligence(BaseModel):
    total_monitoring_events: int = 0
    impactful_events_detected: int = 0
    total_replans_executed: int = 0
    avg_replans_per_situation: float = 0.0
    affected_domains_distribution: Dict[str, int] = Field(default_factory=dict)
    replan_triggers_breakdown: Dict[str, int] = Field(default_factory=dict)
    avg_replan_resolution_minutes: Optional[float] = None
    status: DataSufficiencyStatus = DataSufficiencyStatus.AVAILABLE


class IncidentComparisonMetric(BaseModel):
    group_name: str
    incident_count: int
    avg_response_minutes: Optional[float] = None
    avg_resolution_minutes: Optional[float] = None
    avg_replans: float = 0.0
    task_completion_rate: float = 0.0
    total_population_impacted: int = 0


class IncidentComparisonResponse(BaseModel):
    dimension: str  # emergency_type, severity_level, zone_or_district
    groups: List[IncidentComparisonMetric] = Field(default_factory=list)
    status: DataSufficiencyStatus = DataSufficiencyStatus.AVAILABLE
    reason: Optional[str] = None


class DecisionSupportSignal(BaseModel):
    signal_id: str
    signal_type: DecisionSignalType
    severity: str  # INFO, WARNING, CRITICAL
    title: str
    domain: str
    evidence: str
    affected_entity_id: Optional[str] = None
    recommended_action: str
    confidence: float = 1.0
    created_at: datetime


class DecisionSupportResponse(BaseModel):
    signals: List[DecisionSupportSignal] = Field(default_factory=list)
    total_signals: int = 0
    critical_signals_count: int = 0
    warning_signals_count: int = 0
    generated_at: datetime


class PostIncidentIntelligence(BaseModel):
    situation_id: str
    title: str
    emergency_type: str
    severity_level: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    total_duration_hours: Optional[float] = None
    
    # 12-factor debrief metrics
    total_citizen_reports: int = 0
    initial_estimated_population: int = 0
    plan_versions_count: int = 0
    total_replans: int = 0
    participating_agents: List[str] = Field(default_factory=list)
    total_tasks_generated: int = 0
    tasks_completed: int = 0
    tasks_blocked_or_failed: int = 0
    task_completion_rate: float = 0.0
    
    resources_allocated_count: int = 0
    resources_consumed_count: int = 0
    shelters_activated_count: int = 0
    shelter_occupancy_peak: float = 0.0
    healthcare_referrals_count: int = 0
    volunteers_engaged_count: int = 0
    vehicles_deployed_count: int = 0
    route_disruptions_count: int = 0
    monitoring_events_count: int = 0
    
    # Performance & delays
    intake_to_approval_minutes: Optional[float] = None
    execution_duration_minutes: Optional[float] = None
    identified_bottlenecks: List[str] = Field(default_factory=list)
    operational_improvements: List[str] = Field(default_factory=list)
    ai_summary_explanation: Optional[str] = None


class EmergencyAnalyticsOverview(BaseModel):
    time_range: str
    total_reports: int = 0
    total_situations: int = 0
    active_situations: int = 0
    resolved_situations: int = 0
    critical_incidents: int = 0
    high_severity_incidents: int = 0
    
    avg_acknowledgement_minutes: MetricValue[float]
    avg_planning_minutes: MetricValue[float]
    avg_approval_minutes: MetricValue[float]
    avg_field_response_minutes: MetricValue[float]
    avg_task_completion_minutes: MetricValue[float]
    avg_incident_resolution_hours: MetricValue[float]
    
    overall_task_completion_rate: Optional[float] = None
    overall_resource_utilization_rate: float = 0.0
    total_active_volunteers: int = 0
    total_active_fleet_missions: int = 0
    active_bottlenecks_count: int = 0
    active_decision_signals_count: int = 0
    generated_at: datetime
