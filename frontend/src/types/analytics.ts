export type AnalyticsTimeRange = '24h' | '7d' | '30d' | '90d' | 'all' | 'custom';

export type DataSufficiencyStatus = 'AVAILABLE' | 'INSUFFICIENT_DATA' | 'NO_RECORDS';

export interface MetricValue<T = number> {
  value: T | null;
  unit: string;
  status: DataSufficiencyStatus;
  sample_count: number;
  time_range: string;
  reason?: string | null;
}

export interface DurationDistribution {
  min_minutes: number | null;
  median_minutes: number | null;
  avg_minutes: number | null;
  max_minutes: number | null;
  sample_count: number;
  status: DataSufficiencyStatus;
  reason?: string | null;
}

export interface ResponseMilestoneTimeline {
  intake_to_acknowledgement: DurationDistribution;
  acknowledgement_to_situation: DurationDistribution;
  situation_to_plan_generation: DurationDistribution;
  plan_generation_to_officer_approval: DurationDistribution;
  approval_to_task_assignment: DurationDistribution;
  assignment_to_field_start: DurationDistribution;
  field_start_to_completion: DurationDistribution;
  incident_creation_to_resolution: DurationDistribution;
  total_samples: number;
}

export interface BottleneckInsight {
  bottleneck_type: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  title: string;
  description: string;
  evidence: string;
  delay_impact_minutes?: number | null;
  affected_domain: string;
  affected_situation_id?: string | null;
  actionable_recommendation: string;
  detected_at: string;
}

export interface ResourceDemandCategory {
  category_name: string;
  total_stock: number;
  total_allocated: number;
  total_consumed: number;
  remaining_available: number;
  utilization_percentage: number;
  shortage_count: number;
  conflict_count: number;
}

export interface ResourceUtilizationAnalytics {
  time_range: string;
  total_resources_tracked: number;
  total_units_stock: number;
  total_units_allocated: number;
  total_units_consumed: number;
  overall_utilization_rate: number;
  categories: ResourceDemandCategory[];
  shortage_incidents_count: number;
  conflict_resolution_rate: number | null;
  status: DataSufficiencyStatus;
  reason?: string | null;
}

export interface ShelterAnalytics {
  total_shelters: number;
  total_capacity_beds: number;
  current_occupancy_beds: number;
  remaining_capacity_beds: number;
  occupancy_rate_percentage: number;
  full_shelters_count: number;
  unavailable_shelters_count: number;
  displaced_population_covered: number;
  unmet_shelter_demand_population: number;
  status: DataSufficiencyStatus;
}

export interface HealthcareAnalytics {
  total_facilities: number;
  total_beds_available: number;
  total_beds_occupied: number;
  bed_utilization_percentage: number;
  icu_beds_available: number;
  icu_beds_occupied: number;
  patient_evacuation_demand: number;
  critical_triage_demand: number;
  healthcare_shortages_count: number;
  status: DataSufficiencyStatus;
}

export interface VolunteerPerformanceAnalytics {
  registered_volunteers: number;
  active_responders: number;
  total_missions_assigned: number;
  missions_accepted: number;
  missions_in_progress: number;
  missions_completed: number;
  missions_blocked_or_failed: number;
  completion_rate_percentage: number;
  avg_mission_duration_minutes: number | null;
  skill_demand_breakdown: Record<string, number>;
  volunteer_shortages_count: number;
  status: DataSufficiencyStatus;
}

export interface FleetAnalytics {
  total_vehicles: number;
  active_fleet_missions: number;
  completed_fleet_missions: number;
  blocked_routes_reported: number;
  fleet_utilization_rate: number;
  avg_transit_minutes: number | null;
  vehicle_conflicts_count: number;
  status: DataSufficiencyStatus;
}

export interface ReplanningIntelligence {
  total_monitoring_events: number;
  impactful_events_detected: number;
  total_replans_executed: number;
  avg_replans_per_situation: number;
  affected_domains_distribution: Record<string, number>;
  replan_triggers_breakdown: Record<string, number>;
  avg_replan_resolution_minutes: number | null;
  status: DataSufficiencyStatus;
}

export interface IncidentComparisonMetric {
  group_name: string;
  incident_count: number;
  avg_response_minutes: number | null;
  avg_resolution_minutes: number | null;
  avg_replans: number;
  task_completion_rate: number;
  total_population_impacted: number;
}

export interface IncidentComparisonResponse {
  dimension: string;
  groups: IncidentComparisonMetric[];
  status: DataSufficiencyStatus;
  reason?: string | null;
}

export interface DecisionSupportSignal {
  signal_id: string;
  signal_type: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  title: string;
  domain: string;
  evidence: string;
  affected_entity_id?: string | null;
  recommended_action: string;
  confidence: number;
  created_at: string;
}

export interface DecisionSupportResponse {
  signals: DecisionSupportSignal[];
  total_signals: number;
  critical_signals_count: number;
  warning_signals_count: number;
  generated_at: string;
}

export interface PostIncidentIntelligence {
  situation_id: string;
  title: string;
  emergency_type: string;
  severity_level: string;
  status: string;
  created_at: string;
  resolved_at?: string | null;
  closed_at?: string | null;
  total_duration_hours?: number | null;
  
  total_citizen_reports: number;
  initial_estimated_population: number;
  plan_versions_count: number;
  total_replans: number;
  participating_agents: string[];
  total_tasks_generated: number;
  tasks_completed: number;
  tasks_blocked_or_failed: number;
  task_completion_rate: number;
  
  resources_allocated_count: number;
  resources_consumed_count: number;
  shelters_activated_count: number;
  shelter_occupancy_peak: number;
  healthcare_referrals_count: number;
  volunteers_engaged_count: number;
  vehicles_deployed_count: number;
  route_disruptions_count: number;
  monitoring_events_count: number;
  
  intake_to_approval_minutes?: number | null;
  execution_duration_minutes?: number | null;
  identified_bottlenecks: string[];
  operational_improvements: string[];
  ai_summary_explanation?: string | null;
}

export interface EmergencyAnalyticsOverview {
  time_range: string;
  total_reports: number;
  total_situations: number;
  active_situations: number;
  resolved_situations: number;
  critical_incidents: number;
  high_severity_incidents: number;
  
  avg_acknowledgement_minutes: MetricValue<number>;
  avg_planning_minutes: MetricValue<number>;
  avg_approval_minutes: MetricValue<number>;
  avg_field_response_minutes: MetricValue<number>;
  avg_task_completion_minutes: MetricValue<number>;
  avg_incident_resolution_hours: MetricValue<number>;
  
  overall_task_completion_rate: number | null;
  overall_resource_utilization_rate: number;
  total_active_volunteers: number;
  total_active_fleet_missions: number;
  active_bottlenecks_count: number;
  active_decision_signals_count: number;
  generated_at: string;
}
