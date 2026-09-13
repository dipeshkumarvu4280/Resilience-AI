export type UserRole =
  | 'CITIZEN'
  | 'EMERGENCY_OFFICER'
  | 'RESOURCE_MANAGER'
  | 'VOLUNTEER'
  | 'ADMIN';

export interface VolunteerProfile {
  skills: string[];
  availability: string;
  zone_or_district?: string;
  notes?: string;
  address?: string;
}

export interface User {
  id: string;
  phone: string;
  full_name: string;
  email?: string;
  role: UserRole;
  is_active: boolean;
  badge_number?: string;
  department_or_agency?: string;
  department?: string;
  google_sub?: string | null;
  auth_provider?: string;
  created_at: string;
  volunteer_profile?: VolunteerProfile;
}

export type UserResponse = User;

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface OTPRequestResponse {
  message: string;
  phone: string;
  expires_in_seconds: number;
  simulated_mode?: boolean;
  demo_otp?: string | null;
  cooldown_seconds?: number;
}

export interface OTPVerifyResponse {
  message: string;
  phone: string;
  reset_token: string;
  expires_in_seconds: number;
}

export interface PasswordResetResponse {
  message: string;
}

export type ServiceStatus = 'Operational' | 'Degraded' | 'Outage' | 'Not Enabled';

export interface ServiceInfo {
  name: string;
  status: ServiceStatus;
  phase: string;
  description: string;
  last_check: string;
  details?: string;
}

export interface SystemHealthResponse {
  system_name: string;
  environment: string;
  version: string;
  overall_status: string;
  timestamp: string;
  active_phase: string;
  services: Record<string, ServiceInfo>;
  database_connected: boolean;
}

export interface PlatformConfig {
  system_name: string;
  organization_name: string;
  operational_mode: string;
  spatial_cluster_radius_km: number;
  temporal_window_hours: number;
  ai_coordination_enabled: boolean;
  require_human_approval_for_dispatch: boolean;
  monitoring_poll_interval_sec: number;
  whatsapp_notifications_enabled: boolean;
  session_timeout_minutes: number;
  audit_retention_days: number;
  updated_at?: string;
  updated_by?: string;
}

export interface UserProfileUpdatePayload {
  full_name?: string;
  phone?: string;
  email?: string;
  department_or_agency?: string;
  badge_number?: string;
  volunteer_profile?: VolunteerProfile;
}

export type IncidentSeverity = 'CRITICAL' | 'HIGH' | 'WARNING' | 'NORMAL' | 'INFO';

export interface OTPRequestResponse {
  message: string;
  phone: string;
  expires_in_seconds: number;
}

export interface OTPVerifyResponse {
  message: string;
  phone: string;
  reset_token: string;
  expires_in_seconds: number;
}

// Phase 1: Citizen Emergency Reporting Types
export type EmergencyType =
  | 'Flood'
  | 'Fire'
  | 'Medical Emergency'
  | 'Road Accident'
  | 'Cyclone / Storm'
  | 'Landslide'
  | 'Building Collapse'
  | 'Missing / Trapped Person'
  | 'Other';

export type ReportStatus =
  | 'RECEIVED'
  | 'ACKNOWLEDGED'
  | 'UNDER_ASSESSMENT'
  | 'ACTION_REQUIRED'
  | 'RESOLVED'
  | 'VERIFIED'
  | 'IN_PROGRESS';

export type ReportPriority =
  | 'UNASSESSED'
  | 'LOW'
  | 'MEDIUM'
  | 'HIGH'
  | 'CRITICAL';

export type TimelineEventType =
  | 'REPORT_RECEIVED'
  | 'REPORT_VIEWED'
  | 'REPORT_ACKNOWLEDGED'
  | 'PRIORITY_CHANGED'
  | 'STATUS_CHANGED'
  | 'NOTE_ADDED';

export interface LocationPayload {
  latitude: number;
  longitude: number;
  address?: string;
  street_address?: string;
  landmark?: string;
  zone_or_district?: string;
  district?: string;
  display_name?: string;
  city?: string;
  state?: string;
  country?: string;
  postal_code?: string;
  manual_zone?: string;
  accuracy_meters?: number;
}

export interface ReverseGeocodeResponse {
  latitude: number;
  longitude: number;
  address?: string;
  street_address?: string;
  landmark?: string;
  zone_or_district?: string;
  district?: string;
  display_name?: string;
  city?: string;
  state?: string;
  country?: string;
  postal_code?: string;
  resolved: boolean;
}

export interface MediaAttachment {
  filename: string;
  file_url: string;
  media_type: string;
  size_bytes: number;
}

export type CitizenImpactLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | 'NOT_SURE';

export type EvidenceValidationStatus =
  | 'VALIDATED'
  | 'REVIEW_REQUIRED'
  | 'LOW_CONFIDENCE'
  | 'UNAVAILABLE'
  | 'PARTIALLY_VALIDATED'
  | 'VERIFIED'
  | 'MISMATCH'
  | 'FLAGGED';

export type ReportTrustState = 'NORMAL' | 'REVIEW_REQUIRED' | 'LOW_CONFIDENCE';

export type VerificationStatus =
  | 'UNVERIFIED'
  | 'PARTIALLY_VERIFIED'
  | 'CORROBORATED'
  | 'FIELD_VERIFIED'
  | 'CONFLICTED';

export type EvidenceConfidenceBand = 'LOW' | 'MEDIUM' | 'HIGH';

export type LocationMatchState = 'MATCH' | 'NEAR_MATCH' | 'MISMATCH' | 'UNAVAILABLE';

export type EvidenceFreshness = 'FRESH' | 'AGING' | 'STALE' | 'UNAVAILABLE';

export type ReportCompleteness = 'COMPLETE' | 'PARTIAL' | 'INCOMPLETE';

export interface EvidenceVerificationResult {
  report_id: string;
  verification_status: VerificationStatus;
  confidence_band: EvidenceConfidenceBand;
  citizen_impact_level: CitizenImpactLevel;
  evidence_signals: string[];
  warnings: string[];
  verified_factors: string[];
  missing_factors: string[];
  location_match_state: LocationMatchState;
  distance_from_report_meters?: number;
  evidence_freshness: EvidenceFreshness;
  evidence_age_seconds?: number;
  report_completeness: ReportCompleteness;
  recommendations: string[];
  has_live_photo: boolean;
  content_hash?: string;
  is_duplicate: boolean;
  duplicate_of_report_id?: string;
  last_evaluated_at: string;
}

// =======================================================
// Phase B: Multi-Source Corroboration & Conflict Detection
// =======================================================

export type CorroborationStatus =
  | 'NO_CORROBORATION'
  | 'PARTIALLY_CORROBORATED'
  | 'CORROBORATED'
  | 'CONFLICTED';

export type CorroborationSourceType =
  | 'CITIZEN_REPORT'
  | 'CITIZEN_EVIDENCE'
  | 'SENSOR_EVENT'
  | 'FIELD_UPDATE'
  | 'SITUATION_INTELLIGENCE';

export type CorroborationSpatialRelationship =
  | 'MATCH'
  | 'NEAR_MATCH'
  | 'DISTANT'
  | 'UNAVAILABLE';

export type CorroborationTemporalRelationship =
  | 'COINCIDENT'
  | 'NEAR_CONTEMPORARY'
  | 'HISTORICAL'
  | 'UNAVAILABLE';

export type CorroborationAlignment =
  | 'SUPPORTING'
  | 'NEUTRAL'
  | 'CONFLICTING';

export type EvidenceConflictCategory =
  | 'SPATIAL_CONFLICT'
  | 'TEMPORAL_CONFLICT'
  | 'EVENT_TYPE_CONFLICT'
  | 'OBSERVATION_CONFLICT'
  | 'SENSOR_REPORT_CONFLICT'
  | 'CITIZEN_REPORT_CONFLICT'
  | 'SOURCE_STATE_CONFLICT';

export interface CorroboratingSource {
  source_type: CorroborationSourceType;
  source_id: string;
  source_name?: string | null;
  summary: string;
  alignment: CorroborationAlignment;
  spatial_relationship: CorroborationSpatialRelationship;
  distance_meters?: number | null;
  temporal_relationship: CorroborationTemporalRelationship;
  time_difference_seconds?: number | null;
  timestamp?: string | null;
  sensor_type?: string | null;
  reading_value?: number | null;
  reading_unit?: string | null;
  threshold?: number | null;
  is_breach?: boolean | null;
  coverage_radius_meters?: number | null;
  within_coverage?: boolean | null;
  details?: Record<string, any>;
}

export interface ConflictDetail {
  conflict_id: string;
  category: EvidenceConflictCategory;
  conflicting_source_id: string;
  conflicting_source_type: CorroborationSourceType;
  conflicting_source_name?: string | null;
  summary: string;
  reason: string;
  severity: string;
  recommended_action: string;
}

export interface CorroborationResult {
  target_id: string;
  target_type: 'CITIZEN_REPORT' | 'SITUATION';
  corroboration_status: CorroborationStatus;
  total_sources_evaluated: number;
  supporting_source_count: number;
  conflicting_source_count: number;
  neutral_source_count: number;
  supporting_sources: CorroboratingSource[];
  conflicting_sources: CorroboratingSource[];
  neutral_sources: CorroboratingSource[];
  conflict_details: ConflictDetail[];
  corroboration_factors: string[];
  conflict_factors: string[];
  warnings: string[];
  explanation: string;
  recommendations: string[];
  evaluated_at: string;
}


export interface LiveEvidencePayload {
  image_base64?: string;
  capture_session_id?: string;
  client_capture_timestamp?: string;
  latitude?: number;
  longitude?: number;
  accuracy_meters?: number;
  device_info?: string;
  status?: EvidenceValidationStatus;
  error_reason?: string;
}

export interface LiveEvidenceRecord {
  evidence_id: string;
  report_id?: string;
  evidence_type: string;
  source: string;
  file_url?: string;
  filename?: string;
  content_hash?: string;
  client_capture_timestamp?: string;
  server_received_timestamp: string;
  latitude?: number;
  longitude?: number;
  accuracy_meters?: number;
  distance_from_report_meters?: number;
  capture_session_id?: string;
  validation_status: EvidenceValidationStatus;
  trust_signals: string[];
  is_duplicate?: boolean;
  duplicate_of_evidence_id?: string;
  error_reason?: string;
}

// =======================================================
// Hybrid AI LLM Intelligence Layer (Google Gemini)
// =======================================================

export type ExtractionStatus = 'SUCCESS' | 'PARTIAL' | 'UNAVAILABLE' | 'NOT_EXTRACTED' | 'FAILED';

export interface ExtractedHazard {
  value: string;
  confidence: number;
  source?: string;
  excerpt?: string;
}

export interface ExtractedObservation {
  type: string;
  confidence: number;
  source?: string;
  excerpt?: string;
}

export interface ExtractedAffectedPopulation {
  estimated_count?: number;
  is_uncertain: boolean;
  uncertainty_phrase?: string;
  confidence: number;
  source?: string;
}

export interface ExtractedVulnerableGroup {
  group_type: string;
  estimated_count?: number;
  confidence: number;
  excerpt?: string;
  source?: string;
}

export interface ExtractedNeed {
  need_type: string;
  suggested_quantity?: number;
  unit?: string;
  urgency: string;
  confidence: number;
  excerpt?: string;
  source?: string;
}

export interface ExtractedMedicalIndicator {
  condition: string;
  casualty_count?: number;
  is_critical: boolean;
  confidence: number;
  excerpt?: string;
  source?: string;
}

export interface ExtractedInfrastructureCondition {
  infrastructure_type: string;
  status: string;
  confidence: number;
  excerpt?: string;
  source?: string;
}

export interface LLMExtractionResult {
  extraction_id: string;
  source_type: string;
  source_id: string;
  extracted_at: string;
  model: string;
  prompt_version: string;
  status: ExtractionStatus;
  hazard?: ExtractedHazard;
  observations: ExtractedObservation[];
  affected_population?: ExtractedAffectedPopulation;
  vulnerable_groups: ExtractedVulnerableGroup[];
  reported_needs: ExtractedNeed[];
  medical_indicators: ExtractedMedicalIndicator[];
  infrastructure_conditions: ExtractedInfrastructureCondition[];
  mentioned_landmarks: string[];
  temporal_references: string[];
  textual_location_reference?: string;
  uncertainty_detected: boolean;
  overall_confidence: number;
  warnings: string[];
  error_message?: string;
  is_cached?: boolean;
  provider?: string;
  fallback_used?: boolean;
  primary_provider?: string;
  primary_provider_error?: string;
  error_classification?: string;
  retryable?: boolean;
}

export interface EmergencyReportCreate {
  full_name: string;
  phone: string;
  emergency_type: EmergencyType;
  citizen_impact_level: CitizenImpactLevel;
  description: string;
  location: LocationPayload;
  verification_token?: string;
  bot_honeypot?: string;
  media?: MediaAttachment[];
  evidence?: LiveEvidencePayload;
}

export type VisualHazardType =
  | 'FLOOD'
  | 'FIRE'
  | 'LANDSLIDE'
  | 'STORM'
  | 'CYCLONE'
  | 'EARTHQUAKE'
  | 'ACCIDENT'
  | 'INFRASTRUCTURE_FAILURE'
  | 'STRUCTURAL_COLLAPSE'
  | 'OTHER'
  | 'UNKNOWN'
  | 'NONE_OBSERVABLE';

export type TextImageConsistency =
  | 'SUPPORTED'
  | 'PARTIALLY_SUPPORTED'
  | 'NOT_SUPPORTED'
  | 'INCONCLUSIVE'
  | 'NOT_EVALUATED';

export type ClaimSupportStatus =
  | 'SUPPORTED'
  | 'NOT_OBSERVABLE'
  | 'CONTRADICTED'
  | 'UNCERTAIN';

export type VisualAnalysisStatus =
  | 'SUCCESS'
  | 'TEMPORARILY_UNAVAILABLE'
  | 'UNAVAILABLE'
  | 'FAILED'
  | 'NOT_ANALYZED';

export interface TextClaimEvaluation {
  claim_text: string;
  status: ClaimSupportStatus;
  visual_observation: string;
  confidence: number;
}

export interface VisualObservationItem {
  category: string;
  description: string;
  confidence: number;
}

export interface VulnerablePersonIndicator {
  indicator_type: string;
  observable_count?: number | null;
  visual_description: string;
  confidence: number;
}

export interface InfrastructureCondition {
  infrastructure_type: string;
  condition: string;
  is_access_blocked: boolean;
  visual_description: string;
  confidence: number;
}

export interface PriorityRecommendationSummary {
  recommended_priority: ReportPriority | string;
  score: number;
  evidence_aware: boolean;
  text_image_consistency: TextImageConsistency | string;
  evidence_factors: string[];
  unverified_claims: string[];
  uncertainties: string[];
}

export interface VisualEvidenceAnalysis {
  analysis_id: string;
  source_type: string;
  source_id?: string | null;
  report_id?: string | null;
  evidence_id?: string | null;
  content_hash?: string | null;
  analyzed_at: string;
  model: string;
  prompt_version: string;
  status: VisualAnalysisStatus;
  hazard_type: VisualHazardType;
  hazard_description?: string;
  text_image_consistency: TextImageConsistency;
  consistency_explanation?: string;
  claim_evaluations: TextClaimEvaluation[];
  visible_impacts: string[];
  affected_people_observable?: boolean | number | null;
  estimated_people_count?: number | null;
  vulnerable_person_indicators: VulnerablePersonIndicator[];
  infrastructure_conditions: InfrastructureCondition[];
  environmental_indicators: string[];
  medical_indicators: string[];
  obstruction_indicators?: string[];
  uncertainties: string[];
  overall_confidence: number;
  warnings: string[];
  error_message?: string | null;
  error_reason?: string | null;
  error_classification?: string | null;
  provider?: string;
  fallback_triggered?: boolean;
  primary_provider_error?: string | null;
  fallback_provider?: string | null;
  evidence_available?: boolean;
  analysis_available?: boolean;
  retryable?: boolean;
  retry_attempts_exhausted?: number | null;
  is_cached?: boolean;
}

export interface EmergencyReportResponse {
  report_id: string;
  citizen_id: string;
  citizen_name: string;
  citizen_phone: string;
  emergency_type: EmergencyType;
  citizen_impact_level?: CitizenImpactLevel;
  description: string;
  location: LocationPayload;
  media: MediaAttachment[];
  evidence?: LiveEvidenceRecord;
  evidence_verification?: EvidenceVerificationResult;
  corroboration?: CorroborationResult;
  llm_extraction?: LLMExtractionResult;
  visual_evidence?: VisualEvidenceAnalysis;
  priority_recommendation?: PriorityRecommendationSummary;
  status: ReportStatus;
  priority?: ReportPriority;
  phone_verified?: boolean;
  possible_duplicate?: boolean;
  risk_level?: string;
  risk_reasons?: string[];
  trust_state?: ReportTrustState;
  trust_signals?: string[];
  acknowledged_at?: string;
  acknowledged_by?: string;
  situation_id?: string;
  safety_guidance_id?: string;
  safety_guidance_token?: string;
  created_at: string;
  updated_at: string;
}

export type GuidanceApprovalState = 'PENDING_REVIEW' | 'APPROVED' | 'MODIFIED' | 'REJECTED' | 'AUTO_PUBLISHED';
export type DestinationType = 'SHELTER' | 'HEALTHCARE' | 'POLICE' | 'FIRE_STATION' | 'BUS_STATION' | 'EMERGENCY_ASSISTANCE_POINT' | 'SAFE_ASSEMBLY_AREA' | 'OTHER';
export type RouteStatus = 'CALCULATED' | 'ROUTE_UNAVAILABLE' | 'ROUTE_UNSAFE' | 'RESTRICTED' | 'ROUTE_PROVIDER_ERROR' | 'INSUFFICIENT_DATA';

export type WebPushState =
  | 'NOT_SUPPORTED'
  | 'PERMISSION_NOT_REQUESTED'
  | 'PERMISSION_DENIED'
  | 'PERMISSION_GRANTED_NO_SUBSCRIPTION'
  | 'SUBSCRIPTION_PENDING'
  | 'SUBSCRIBED_NOT_PERSISTED'
  | 'ACTIVE';

export interface VerifiedDestination {
  destination_id: string;
  destination_name: string;
  destination_type: DestinationType;
  latitude: number;
  longitude: number;
  address_or_landmark: string;
  distance_km: number;
  available_capacity?: number | null;
  total_capacity?: number | null;
  operational_status: string;
  suitability_reason: string;
  contact_phone?: string | null;
  place_id?: string | null;
  provider?: string | null;
  last_checked?: string | null;
  estimated_drive_minutes?: number | null;
  rating?: number | null;
  open_now?: boolean | null;
}

export interface HazardAvoidanceZone {
  hazard_id: string;
  hazard_type: string;
  latitude: number;
  longitude: number;
  radius_km: number;
  warning_message: string;
}

export interface RouteDetails {
  origin_latitude: number;
  origin_longitude: number;
  destination_latitude: number;
  destination_longitude: number;
  distance_km: number;
  estimated_duration_minutes: number;
  route_status: RouteStatus;
  polyline_points: [number, number][];
  encoded_polyline?: string | null;
  route_warnings: string[];
  avoid_areas: HazardAvoidanceZone[];
  provider: string;
  calculated_at: string;
}

export interface GuidanceVersionHistoryItem {
  guidance_id: string;
  version: number;
  status: string;
  approval_state: string;
  generated_at: string;
  valid_until: string;
  change_reason?: string | null;
  trigger_event_id?: string | null;
  destination_name?: string | null;
  route_status: string;
  is_stale: boolean;
}

export interface CitizenSafetyGuidance {
  guidance_id: string;
  secure_access_token: string;
  report_id: string;
  situation_id?: string | null;
  generated_at: string;
  valid_until: string;
  status: string;
  emergency_type: string;
  risk_level: string;
  immediate_actions: string[];
  precautions: string[];
  recommended_destination?: VerifiedDestination | null;
  nearby_alternatives?: VerifiedDestination[];
  destination_reason?: string | null;
  route?: RouteDetails | null;
  route_warnings: string[];
  avoid_locations: HazardAvoidanceZone[];
  confidence: number;
  evidence_references: string[];
  requires_officer_approval: boolean;
  approval_state: GuidanceApprovalState;
  officer_review_notes?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  version: number;
  supersedes_guidance_id?: string | null;
  superseded_by_guidance_id?: string | null;
  trigger_event_id?: string | null;
  change_reason?: string | null;
  is_stale?: boolean;
  history?: any[];
}

export interface CitizenSafetyGuidanceResponse {
  success: boolean;
  guidance?: CitizenSafetyGuidance | null;
  secure_access_token?: string | null;
  latest_active_token?: string | null;
  message: string;
}

export interface PushSubscriptionCreate {
  endpoint: string;
  keys: {
    p256dh: string;
    auth: string;
  };
  user_agent?: string;
  report_id?: string;
  session_id?: string;
}

export interface SafetyGuidanceReviewRequest {
  action: GuidanceApprovalState;
  modified_actions?: string[];
  modified_precautions?: string[];
  officer_notes?: string;
}


export interface OfficerNote {
  note_id: string;
  author_id: string;
  author_name: string;
  author_role: UserRole;
  note: string;
  created_at: string;
}

export interface TimelineEvent {
  event_id: string;
  event_type: TimelineEventType;
  actor_id?: string;
  actor_name?: string;
  actor_role?: string;
  details: string;
  previous_value?: string;
  new_value?: string;
  timestamp: string;
}

export interface OfficerReportStatsResponse {
  total_incoming: number;
  acknowledged: number;
  under_assessment: number;
  action_required: number;
  resolved: number;
  total_reports: number;
}

export interface OfficerReportDetailResponse extends EmergencyReportResponse {
  priority: ReportPriority;
  notes: OfficerNote[];
  timeline: TimelineEvent[];
}

export interface PaginatedOfficerReportsResponse {
  items: OfficerReportDetailResponse[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface CitizenOTPVerifyResponse {
  message: string;
  phone: string;
  citizen_id: string;
  verification_token: string;
  expires_in_seconds: number;
}

// Phase 3: Emergency Resource Coordination Types
export type ResourceType =
  | 'Water'
  | 'Food'
  | 'Medicine'
  | 'First Aid'
  | 'Medical Equipment'
  | 'Rescue Equipment'
  | 'Protective Equipment'
  | 'Blankets'
  | 'Clothing'
  | 'Generator'
  | 'Fuel'
  | 'Communication Equipment'
  | 'Transport'
  | 'Shelter'
  | 'Other';

export type ResourceStatus = 'AVAILABLE' | 'PARTIALLY_AVAILABLE' | 'UNAVAILABLE';
export type ResourceCondition = 'GOOD' | 'LIMITED' | 'DAMAGED';
export type NeedUrgency = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type AllocationStatus = 'PROPOSED' | 'APPROVED' | 'REJECTED' | 'DISPATCHED' | 'COMPLETED' | 'CANCELLED';

export interface ResourceLocation {
  latitude: number;
  longitude: number;
  address?: string;
  street_address?: string;
  landmark?: string;
  zone_or_district?: string;
  district?: string;
  city?: string;
  state?: string;
  postal_code?: string;
}

export interface ResourceResponse {
  resource_id: string;
  name: string;
  resource_type: ResourceType;
  category?: string;
  quantity_total: number;
  quantity_available: number;
  unit: string;
  location: ResourceLocation;
  status: ResourceStatus;
  condition: ResourceCondition;
  owner?: string;
  contact?: string;
  notes?: string;
  created_by?: string;
  created_by_name?: string;
  updated_by?: string;
  updated_by_name?: string;
  created_at: string;
  updated_at: string;
}

export interface ResourceCreatePayload {
  name: string;
  resource_type: ResourceType;
  category?: string;
  quantity_total: number;
  quantity_available: number;
  unit: string;
  location: ResourceLocation;
  status?: ResourceStatus;
  condition?: ResourceCondition;
  owner?: string;
  contact?: string;
  notes?: string;
}

export interface ResourceUpdatePayload {
  name?: string;
  resource_type?: ResourceType;
  category?: string;
  quantity_total?: number;
  quantity_available?: number;
  unit?: string;
  location?: ResourceLocation;
  status?: ResourceStatus;
  condition?: ResourceCondition;
  owner?: string;
  contact?: string;
  notes?: string;
}

export interface PaginatedResourcesResponse {
  items: ResourceResponse[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface ResourceStatsResponse {
  total_resources: number;
  available_resources: number;
  partially_available: number;
  unavailable: number;
  type_counts: Record<string, number>;
}

export interface EmergencyNeedItem {
  need_id: string;
  resource_type: ResourceType;
  requested_quantity: number;
  unit: string;
  urgency: NeedUrgency;
  reason?: string;
}

export interface NeedsAssessmentResponse {
  report_id: string;
  needs: EmergencyNeedItem[];
  assessed_by: string;
  assessed_by_id: string;
  assessed_at: string;
  updated_at: string;
}

export interface AINeedsSuggestionItem {
  resource_type: ResourceType;
  suggested_quantity: number;
  unit: string;
  urgency: NeedUrgency;
  reasoning: string;
  confidence: number;
}

export interface AINeedsSuggestionResponse {
  report_id: string;
  suggestions: AINeedsSuggestionItem[];
  ai_available: boolean;
  disclaimer: string;
}

export interface ResourceMatchCandidate {
  resource_id: string;
  name: string;
  resource_type: ResourceType;
  quantity_available: number;
  unit: string;
  distance_km: number;
  match_score: number;
  location: ResourceLocation;
  status: ResourceStatus;
  condition: ResourceCondition;
  reasoning: string[];
  recommended_allocation: number;
}

export interface NeedMatchResult {
  need_id: string;
  resource_type: ResourceType;
  requested_quantity: number;
  unit: string;
  urgency: NeedUrgency;
  candidates: ResourceMatchCandidate[];
  total_matched_available: number;
  is_fully_matchable: boolean;
}

export interface ResourceMatchingResponse {
  report_id: string;
  needs_matches: NeedMatchResult[];
  generated_at: string;
  ai_explanation?: string;
}

export interface AllocationCreateRequest {
  need_id: string;
  resource_id: string;
  requested_quantity: number;
  notes?: string;
}

export interface AllocationResponse {
  allocation_id: string;
  report_id: string;
  need_id: string;
  resource_id: string;
  resource_name: string;
  resource_type: ResourceType;
  requested_quantity: number;
  approved_quantity: number;
  unit: string;
  status: AllocationStatus;
  proposed_by: string;
  proposed_by_id: string;
  approved_by?: string;
  approved_by_id?: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}

// Phase 4: Situation Intelligence Types
export type SeverityLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type SituationStatus =
  | 'ACTIVE'
  | 'RESPONSE_IN_PROGRESS'
  | 'OPERATIONS_COMPLETED'
  | 'OFFICER_REVIEW'
  | 'MONITORING'
  | 'CONTAINED'
  | 'RESOLVED'
  | 'CLOSED';
export type AssessmentStatus = 'PENDING' | 'COMPLETED' | 'FAILED' | 'REVIEWED';
export type OfficerReviewAction = 'ACCEPT' | 'MODIFY' | 'REJECT';

export interface SituationLocationCenter {
  latitude: number;
  longitude: number;
  address?: string;
  street_address?: string;
  landmark?: string;
  zone_or_district?: string;
  city?: string;
  state?: string;
  country?: string;
  postal_code?: string;
}

export interface ImpactZone {
  center_latitude: number;
  center_longitude: number;
  radius_km: number;
  affected_zone_name?: string;
  bounding_box?: {
    min_lat: number;
    max_lat: number;
    min_lon: number;
    max_lon: number;
  };
  is_estimated: boolean;
  estimation_rationale?: string;
}

export interface SituationAssessment {
  assessment_id: string;
  situation_id: string;
  severity_score: number;
  severity_level: SeverityLevel;
  estimated_affected_population: number;
  impact_radius_km: number;
  hazard_risk: string;
  key_factors: string[];
  situation_summary: string;
  confidence: number;
  recommendations: string[];
  is_ai_generated: boolean;
  ai_provider?: string;
  generated_by: string;
  created_at: string;
  updated_at: string;
}

export interface OfficerSituationReview {
  reviewed_by_id: string;
  reviewed_by_name: string;
  action: OfficerReviewAction;
  operational_severity_level: SeverityLevel;
  operational_severity_score: number;
  notes?: string;
  reviewed_at: string;
}

export interface OfficerSituationReviewRequest {
  action: OfficerReviewAction;
  modified_severity_level?: SeverityLevel;
  modified_severity_score?: number;
  notes?: string;
  reset_override?: boolean;
}

export interface ClusteredReportSummary {
  report_id: string;
  emergency_type: EmergencyType;
  description: string;
  citizen_name: string;
  citizen_phone: string;
  latitude: number;
  longitude: number;
  address?: string;
  zone_or_district?: string;
  distance_to_center_km: number;
  status: string;
  priority: string;
  created_at: string;
  media: MediaAttachment[];
}

export interface SituationCluster {
  situation_id: string;
  cluster_id: string;
  title: string;
  emergency_type: EmergencyType;
  primary_report_id: string;
  report_ids: string[];
  report_count: number;
  center_location: SituationLocationCenter;
  impact_zone: ImpactZone;
  status: SituationStatus;
  assessment_status: AssessmentStatus;
  
  // Effective operational severity (officer override if set, else computed)
  severity_score: number;
  severity_level: SeverityLevel;
  
  // Deterministic / AI computed severity
  computed_severity_score?: number;
  computed_severity_level?: SeverityLevel;
  
  // Officer override specifics
  officer_override_severity?: SeverityLevel | null;
  officer_override_score?: number | null;
  officer_override_by?: string | null;
  officer_override_by_id?: string | null;
  officer_override_at?: string | null;
  officer_override_notes?: string | null;

  estimated_affected_population: number;
  hazard_risk: string;
  confidence: number;
  situation_summary: string;
  assessment?: SituationAssessment | null;
  officer_review?: OfficerSituationReview | null;
  clustering_reasoning: string[];
  created_at: string;
  updated_at: string;
}

export interface SensorEvidenceSummary {
  source_type: string;
  source_id: string;
  sensor_id: string;
  sensor_name: string;
  sensor_type: string;
  event_id?: string | null;
  reading_id?: string | null;
  value: number;
  current_value: number;
  previous_value?: number | null;
  unit: string;
  threshold: number;
  threshold_state: string;
  is_breach: boolean;
  timestamp: string;
  latitude: number;
  longitude: number;
  location_name?: string | null;
  sensor_address?: string | null;
  coverage_radius_meters?: number | null;
  coverage_radius_km?: number | null;
  distance_to_center_km: number;
  correlation_reason: string;
  confidence_contribution: number;
  is_simulated: boolean;
}

export interface SituationEvidenceResponse {
  total_sources: number;
  citizen_reports_count: number;
  sensor_events_count: number;
  citizen_reports: ClusteredReportSummary[];
  sensor_evidence: SensorEvidenceSummary[];
}

export interface SituationDetailResponse {
  situation: SituationCluster;
  clustered_reports: ClusteredReportSummary[];
  sensor_evidence?: SensorEvidenceSummary[];
  evidence?: SituationEvidenceResponse | null;
  corroboration?: CorroborationResult | null;
}

export interface PaginatedSituationsResponse {
  items: SituationCluster[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface SituationStatsResponse {
  total_situations: number;
  active_situations: number;
  critical_situations: number;
  high_situations: number;
  total_clustered_reports: number;
  average_confidence: number;
}

// =========================================================================
// Phase 5: Multi-Agent Coordination & Central Orchestrator Types
// =========================================================================

export type AgentName =
  | 'priority_agent'
  | 'needs_agent'
  | 'resource_agent'
  | 'conflict_agent'
  | 'shelter_agent'
  | 'healthcare_agent'
  | 'volunteer_agent'
  | 'route_agent'
  | 'replanning_agent';

export type AgentRunStatus =
  | 'NOT_REQUIRED'
  | 'QUEUED'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'FALLBACK';

export type CoordinationPlanStatus =
  | 'DRAFT'
  | 'PENDING_OFFICER_REVIEW'
  | 'APPROVED'
  | 'ACTIVE'
  | 'MODIFIED'
  | 'REJECTED'
  | 'EXECUTING'
  | 'EXECUTED'
  | 'SUPERSEDED'
  | 'SIMULATION_RESULT';

export type PlanReviewAction = 'APPROVE' | 'MODIFY' | 'REJECT';

export type ConflictType =
  | 'RESOURCE_SHORTAGE'
  | 'COMPETING_RESOURCE_DEMAND'
  | 'INSUFFICIENT_QUANTITY'
  | 'RESOURCE_UNAVAILABLE'
  | 'RESOURCE_UNFIT'
  | 'RESOURCE_STATUS_CONFLICT'
  | 'GEOGRAPHIC_MISMATCH'
  | 'PRIORITY_CONFLICT'
  | 'NEED_RESOURCE_MISMATCH'
  | 'ALLOCATION_OVERLAP'
  | 'NO_FEASIBLE_ALLOCATION'
  | 'DUPLICATE_RECOMMENDATION'
  | 'UNKNOWN_CONFLICT';

export type ResolutionStrategy =
  | 'PRIORITY_FIRST'
  | 'PARTIAL_ALLOCATION'
  | 'MULTI_SOURCE_SPLIT'
  | 'ALTERNATIVE_RESOURCE'
  | 'DEFER_LOW_PRIORITY'
  | 'UNRESOLVED_ESCALATION'
  | 'NO_FEASIBLE_RESOLUTION';

export type ConflictStatus =
  | 'RESOLVED'
  | 'PARTIALLY_RESOLVED'
  | 'UNRESOLVED'
  | 'ESCALATED';

export interface DetectedConflict {
  conflict_id: string;
  conflict_type: ConflictType;
  severity: SeverityLevel;
  description: string;
  affected_need?: string | null;
  affected_resource?: string | null;
  detected_quantity?: number | null;
  available_quantity?: number | null;
  shortfall?: number | null;
  resolution_strategy?: ResolutionStrategy | null;
  resolution_status: ConflictStatus;
  officer_attention_required: boolean;
  explanation: string;
  alternative_options?: string[];
}

export interface ConflictResolutionSummary {
  conflicts_detected: DetectedConflict[];
  conflicts_count: number;
  resolved_conflicts: number;
  unresolved_conflicts: number;
  resolution_actions: string[];
  affected_needs: string[];
  affected_resources: string[];
  shortages?: Array<{
    resource_type: string;
    requested: number;
    available: number;
    shortfall: number;
    unit: string;
  }>;
  officer_attention_required: boolean;
  explanation: string;
  confidence: number;
  generated_at: string;
  agent_version: string;
}

export interface AgentResult {
  agent_name: AgentName;
  run_id: string;
  status: AgentRunStatus;
  recommendation: string;
  structured_output: Record<string, any>;
  confidence: number;
  evidence: string[];
  warnings: string[];
  constraints: string[];
  generated_at: string;
}

export interface PlanRecommendedResource {
  resource_type: ResourceType;
  quantity_required: number;
  unit: string;
  urgency: NeedUrgency;
  matched_resource_id?: string | null;
  matched_resource_name?: string | null;
  available_in_inventory?: number | null;
  allocated_quantity?: number | null;
  depot_location?: string | null;
  distance_km?: number | null;
  reasoning?: string | null;
}

export type ShelterConflictType =
  | 'SHELTER_CAPACITY_SHORTAGE'
  | 'SHELTER_FULL'
  | 'SHELTER_UNAVAILABLE'
  | 'SHELTER_CLOSED'
  | 'SHELTER_DATA_CONFLICT'
  | 'SHELTER_ACCESSIBILITY_CONFLICT'
  | 'SHELTER_DISTANCE_CONFLICT'
  | 'SHELTER_SUITABILITY_CONFLICT'
  | 'NO_FEASIBLE_SHELTER'
  | 'POPULATION_DATA_UNAVAILABLE'
  | 'SHELTER_NOT_REQUIRED';

export interface RecommendedShelter {
  shelter_id: string;
  shelter_name: string;
  distance_km: number;
  total_capacity: number;
  current_occupancy: number;
  remaining_capacity: number;
  recommended_occupancy: number;
  coverage_percentage: number;
  suitability_score: number;
  ranking_factors: Record<string, number>;
  recommendation_reason: string;
  location_address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  status: string;
  accessibility?: string | null;
}

export interface ShelterCoordinationSummary {
  shelter_required: boolean;
  requirement_reason: string;
  affected_population?: number | null;
  population_confidence: number;
  shelters_evaluated: number;
  shelters_recommended: RecommendedShelter[];
  total_capacity_available: number;
  total_population_covered: number;
  total_shortfall: number;
  conflicts: string[];
  officer_attention_required: boolean;
  explanation: string;
  confidence: number;
  generated_at: string;
  agent_version: string;
}

export interface RecommendedHealthcareFacility {
  facility_id: string;
  facility_name: string;
  facility_type: string;
  distance_km: number;
  total_beds: number;
  available_beds: number;
  allocated_patients: number;
  coverage_percentage: number;
  icu_available: number;
  oxygen_available: boolean;
  trauma_capable: boolean;
  emergency_capable: boolean;
  suitability_score: number;
  ranking_factors: Record<string, number>;
  recommendation_reason: string;
  location_address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  status: string;
}

export interface HealthcareCoordinationSummary {
  medical_required: boolean;
  requirement_reason: string;
  estimated_casualties?: number | null;
  casualty_confidence: number;
  facilities_evaluated: number;
  facilities_recommended: RecommendedHealthcareFacility[];
  total_beds_available: number;
  total_patients_covered: number;
  total_shortfall: number;
  conflicts: string[];
  officer_attention_required: boolean;
  explanation: string;
  confidence: number;
  generated_at: string;
  agent_version: string;
}

export interface RecommendedVolunteerAssignment {
  volunteer_id: string;
  volunteer_name: string;
  role_or_skill: string;
  assigned_operation: string;
  location_zone?: string | null;
  distance_km?: number | null;
  suitability_score: number;
  availability_status: string;
  recommendation_reason: string;
  phone?: string | null;
}

export interface VolunteerCoordinationSummary {
  volunteers_required: boolean;
  requirement_reason: string;
  estimated_volunteers_needed: number;
  volunteers_evaluated: number;
  volunteers_recommended: RecommendedVolunteerAssignment[];
  total_volunteers_assigned: number;
  total_shortfall: number;
  conflicts: string[];
  officer_attention_required: boolean;
  explanation: string;
  confidence: number;
  generated_at: string;
  agent_version: string;
}

export interface RecommendedTransport {
  transport_id: string;
  vehicle_name: string;
  vehicle_type: string;
  capacity: number;
  allocated_load_or_passengers: number;
  current_status: string;
  location_address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  assigned_mission: string;
  recommendation_reason: string;
}

export interface RecommendedRoute {
  route_id: string;
  origin_name: string;
  destination_name: string;
  origin_coordinates: { latitude: number; longitude: number };
  destination_coordinates: { latitude: number; longitude: number };
  distance_km: number;
  estimated_duration_minutes: number;
  road_condition_status: string;
  transport_id?: string | null;
  assigned_mission: string;
  recommendation_reason: string;
}

export interface RouteTransportCoordinationSummary {
  transport_required: boolean;
  requirement_reason: string;
  routes_evaluated: number;
  routes_recommended: RecommendedRoute[];
  transports_recommended: RecommendedTransport[];
  total_vehicles_assigned: number;
  transport_shortfall: number;
  conflicts: string[];
  officer_attention_required: boolean;
  explanation: string;
  confidence: number;
  generated_at: string;
  agent_version: string;
}

export interface OfficerPlanReview {
  decision: PlanReviewAction;
  reviewed_by_id: string;
  reviewed_by_name: string;
  reviewed_by_role: string;
  reviewed_at: string;
  officer_notes?: string | null;
  modified_fields?: Record<string, any> | null;
}

export interface CoordinationPlan {
  plan_id: string;
  situation_id: string;
  version: number;
  state_fingerprint?: string | null;
  generated_at: string;
  participating_agents: AgentName[];
  agent_results: Record<string, AgentResult>;
  assessed_priority: SeverityLevel;
  assessed_needs: any[];
  recommended_allocations: PlanRecommendedResource[];
  conflicts?: DetectedConflict[];
  conflict_summary?: ConflictResolutionSummary | null;
  recommended_shelters?: RecommendedShelter[];
  shelter_summary?: ShelterCoordinationSummary | null;
  recommended_facilities?: RecommendedHealthcareFacility[];
  healthcare_summary?: HealthcareCoordinationSummary | null;
  recommended_volunteers?: RecommendedVolunteerAssignment[];
  volunteer_summary?: VolunteerCoordinationSummary | null;
  recommended_transports?: RecommendedTransport[];
  recommended_routes?: RecommendedRoute[];
  route_summary?: RouteTransportCoordinationSummary | null;
  officer_attention_required?: boolean;
  has_unresolved_conflicts?: boolean;
  reasoning: string;
  constraints: string[];
  confidence: number;
  status: CoordinationPlanStatus;
  officer_review?: OfficerPlanReview | null;
  previous_plan_id?: string | null;
  previous_version?: number | null;
  trigger_event_id?: string | null;
  impact_id?: string | null;
  is_revised_version?: boolean;
  is_simulation?: boolean;
  diff_summary?: PlanDiffResult | null;
  change_explanation?: string | null;
}

export interface AgentRunRecord {
  run_id: string;
  situation_id: string;
  agent_name: AgentName;
  agent_version: string;
  status: AgentRunStatus;
  state_fingerprint?: string | null;
  started_at: string;
  completed_at?: string | null;
  input_summary: Record<string, any>;
  result?: AgentResult | null;
  confidence: number;
  warnings: string[];
  error?: string | null;
  actor_id?: string | null;
  actor_name?: string | null;
}

export interface PlanReviewPayload {
  action: PlanReviewAction;
  notes?: string;
  modified_needs?: any[];
  modified_allocations?: PlanRecommendedResource[];
  modified_shelters?: RecommendedShelter[];
  modified_facilities?: RecommendedHealthcareFacility[];
  modified_volunteers?: RecommendedVolunteerAssignment[];
  modified_transports?: RecommendedTransport[];
  modified_routes?: RecommendedRoute[];
}

// Phase 6: Live Monitoring & Unified Event Detection Types
export type MonitoringEventType =
  | 'REPORT_CREATED'
  | 'REPORT_STATUS_CHANGED'
  | 'REPORT_PRIORITY_CHANGED'
  | 'REPORT_TYPE_CHANGED'
  | 'REPORT_LOCATION_CHANGED'
  | 'REPORT_ACKNOWLEDGED'
  | 'REPORT_RESOLVED'
  | 'SITUATION_CREATED'
  | 'SITUATION_MEMBERSHIP_CHANGED'
  | 'SITUATION_SEVERITY_CHANGED'
  | 'SITUATION_CONFIDENCE_CHANGED'
  | 'SITUATION_LOCATION_CHANGED'
  | 'SITUATION_STATUS_CHANGED'
  | 'RESOURCE_CREATED'
  | 'RESOURCE_QUANTITY_INCREASED'
  | 'RESOURCE_QUANTITY_DECREASED'
  | 'RESOURCE_QUANTITY_CHANGED'
  | 'RESOURCE_STATUS_CHANGED'
  | 'RESOURCE_CONDITION_CHANGED'
  | 'RESOURCE_LOCATION_CHANGED'
  | 'RESOURCE_ALLOCATED'
  | 'RESOURCE_RELEASED'
  | 'SHELTER_CAPACITY_CHANGED'
  | 'SHELTER_OCCUPANCY_CHANGED'
  | 'SHELTER_STATUS_CHANGED'
  | 'SHELTER_UNAVAILABLE'
  | 'SHELTER_AVAILABLE'
  | 'HEALTHCARE_CAPACITY_CHANGED'
  | 'HEALTHCARE_STATUS_CHANGED'
  | 'HEALTHCARE_TRAUMA_CHANGED'
  | 'HEALTHCARE_FACILITY_UNAVAILABLE'
  | 'HEALTHCARE_FACILITY_AVAILABLE'
  | 'VOLUNTEER_AVAILABILITY_CHANGED'
  | 'VOLUNTEER_STATUS_CHANGED'
  | 'VOLUNTEER_SKILL_CHANGED'
  | 'VOLUNTEER_ASSIGNMENT_CHANGED'
  | 'TRANSPORT_AVAILABILITY_CHANGED'
  | 'TRANSPORT_STATUS_CHANGED'
  | 'TRANSPORT_ASSIGNMENT_CHANGED'
  | 'ROUTE_STATUS_CHANGED'
  | 'ROUTE_OBSTRUCTION_CHANGED'
  | 'OFFICER_SEVERITY_OVERRIDDEN'
  | 'OFFICER_PLAN_APPROVED'
  | 'OFFICER_PLAN_MODIFIED'
  | 'OFFICER_PLAN_REJECTED';

export type EventSourceType =
  | 'CITIZEN_REPORT'
  | 'SITUATION_INTELLIGENCE'
  | 'RESOURCE_INVENTORY'
  | 'SHELTER_FACILITY'
  | 'HEALTHCARE_FACILITY'
  | 'VOLUNTEER_NETWORK'
  | 'TRANSPORT_FLEET'
  | 'ROUTE_NETWORK'
  | 'OFFICER_DECISION'
  | 'SIMULATED_SENSOR'
  | 'SYSTEM';

export type EventStatus =
  | 'DETECTED'
  | 'ANALYZING'
  | 'ANALYZED'
  | 'REQUIRES_REVIEW'
  | 'ACKNOWLEDGED'
  | 'RESOLVED'
  | 'DISMISSED';

export type ImpactLevel = 'NONE' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type PlanValidityStatus =
  | 'UNAFFECTED'
  | 'POTENTIALLY_AFFECTED'
  | 'INVALIDATED'
  | 'REQUIRES_OFFICER_REVIEW';

export type OperationalDomain =
  | 'RESOURCE'
  | 'SHELTER'
  | 'HEALTHCARE'
  | 'VOLUNTEER'
  | 'TRANSPORT'
  | 'ROUTE'
  | 'SITUATION'
  | 'CONFLICT';

export interface MonitoringEvent {
  event_id: string;
  event_type: MonitoringEventType;
  source_type: EventSourceType;
  source_id: string;
  situation_id?: string | null;
  coordination_plan_id?: string | null;
  detected_at: string;
  effective_at: string;
  severity: SeverityLevel;
  previous_state: Record<string, any>;
  new_state: Record<string, any>;
  changed_fields: string[];
  location?: Record<string, any> | null;
  metadata: Record<string, any>;
  correlation_id?: string | null;
  event_fingerprint: string;
  is_simulation?: boolean;
  actor_id?: string | null;
  actor_name?: string | null;
  actor_role?: string | null;
  confidence: number;
  status: EventStatus;
  impact_level: ImpactLevel;
  resolved_at?: string | null;
  resolved_by_id?: string | null;
  resolved_by_name?: string | null;
  resolution_reason?: string | null;
  resolved_in_plan_id?: string | null;
  resolved_in_plan_version?: number | null;
  remediation_status?: string | null;
}

export interface ChangeImpactResult {
  impact_id: string;
  event_id: string;
  situation_id?: string | null;
  coordination_plan_id?: string | null;
  impact_level: ImpactLevel;
  plan_status: PlanValidityStatus;
  changed_entity: string;
  changed_fields: string[];
  previous_state: Record<string, any>;
  new_state: Record<string, any>;
  affected_domains: OperationalDomain[];
  affected_agents: AgentName[];
  dependency_chain: AgentName[];
  affected_plan_components: string[];
  violated_constraints: string[];
  shortfalls: Record<string, number>;
  officer_attention_required: boolean;
  explanation: string;
  analyzed_at: string;
  acknowledged_at?: string | null;
  acknowledged_by_id?: string | null;
  acknowledged_by_name?: string | null;
  resolved_at?: string | null;
  resolved_by_id?: string | null;
  resolved_by_name?: string | null;
  resolution_reason?: string | null;
  resolved_in_plan_id?: string | null;
  resolved_in_plan_version?: number | null;
  remediation_status?: string | null;
}

export interface PaginatedMonitoringEventsResponse {
  items: MonitoringEvent[];
  total_count: number;
  page: number;
  limit: number;
  total_pages: number;
}


export interface MonitoringStatsResponse {
  total_events: number;
  active_alerts: number;
  critical_impacts: number;
  high_impacts: number;
  invalidated_plans: number;
  plans_requiring_review: number;
  impacted_operations_count?: number;
  unacknowledged_events: number;
  acknowledged_events: number;
  resolved_events?: number;
  domain_breakdown: Record<string, number>;
}

export interface AcknowledgeEventResponse {
  success: boolean;
  event_id: string;
  status: EventStatus;
  acknowledged_at: string;
  acknowledged_by_name: string;
  message: string;
}

// Phase 6.3 & 6.4 Re-Planning & Plan Activation Types
export interface PlanComponentDiffItem {
  category: string;
  entity_id: string;
  entity_name: string;
  diff_type: 'ADDED' | 'REMOVED' | 'CHANGED' | 'UNCHANGED';
  previous_value?: any;
  new_value?: any;
  reason?: string | null;
  requires_officer_attention?: boolean;
}

export interface PlanDiffResult {
  previous_plan_id: string;
  previous_version: number;
  new_plan_id: string;
  new_version: number;
  summary: string;
  items: PlanComponentDiffItem[];
  affected_domains: OperationalDomain[];
  affected_agents: AgentName[];
  has_conflicts: boolean;
  is_material_change: boolean;
  generated_at: string;
}

export interface PlanApprovalRequest {
  officer_notes?: string;
  expected_state_fingerprint?: string;
}

export interface PlanModifyRequest {
  notes?: string;
  modified_needs?: any[];
  modified_allocations?: any[];
  modified_shelters?: any[];
  modified_facilities?: any[];
  modified_volunteers?: any[];
  modified_transports?: any[];
  modified_routes?: any[];
}

export interface PlanRejectRequest {
  rejection_reason: string;
  officer_notes?: string;
}

export interface PlanActivationResponse {
  success: boolean;
  plan_id: string;
  version: number;
  status: string;
  previous_plan_id?: string | null;
  previous_version?: number | null;
  activated_at: string;
  officer_id: string;
  officer_name: string;
  message: string;
}

// ==========================================
// Phase 6.5 Simulation / What-If Engine Types
// ==========================================

export type ScenarioType =
  | 'RESOURCE_REDUCTION'
  | 'RESOURCE_UNAVAILABLE'
  | 'DEMAND_SURGE'
  | 'ROUTE_BLOCKED'
  | 'FACILITY_OFFLINE'
  | 'VOLUNTEER_DROPOUT'
  | 'COMPOUND';

export type SimulationStatus =
  | 'DRAFT'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'DISCARDED'
  | 'STALE';

export interface SimulationScenario {
  scenario_id: string;
  scenario_type: ScenarioType;
  title: string;
  description: string;
  target_entity_type: string;
  target_entity_id: string;
  target_entity_name?: string | null;
  target_domain: OperationalDomain;
  target_agent?: AgentName | null;
  baseline_value: Record<string, any>;
  simulated_value: Record<string, any>;
  created_at: string;
}

export interface SimulationRun {
  simulation_id: string;
  simulation_name: string;
  situation_id: string;
  situation_name?: string | null;
  baseline_plan_id: string;
  baseline_plan_version: number;
  baseline_fingerprint?: string | null;
  scenarios: SimulationScenario[];
  status: SimulationStatus;
  is_simulation: boolean;
  simulated_plan_id?: string | null;
  simulated_plan?: CoordinationPlan | null;
  result_plan?: CoordinationPlan | null;
  diff_summary?: PlanDiffResult | null;
  diff_result?: PlanDiffResult | null;
  impact_level?: string | null;
  impact_summary?: ChangeImpactResult | null;
  explanation?: string | null;
  simulation_explanation?: string | null;
  execution_fingerprint?: string | null;
  affected_domains: OperationalDomain[];
  affected_agents: AgentName[];
  execution_duration_ms?: number | null;
  created_by_id: string;
  created_by_name: string;
  created_at: string;
  completed_at?: string | null;
  discarded_at?: string | null;
  expires_at?: string | null;
  error_message?: string | null;
}

export interface SimulationEntityTarget {
  entity_id: string;
  entity_type: string;
  name: string;
  entity_name?: string;
  domain?: OperationalDomain;
  agent_name?: AgentName;
  current_status?: string;
  current_value?: any;
  status?: string;
  available_capacity_or_quantity?: number | null;
  unit?: string | null;
  unit_or_type?: string | null;
  location_name?: string | null;
  location_summary?: string | null;
  extra?: Record<string, any>;
}

export interface SimulationTargetLookupResponse {
  situation_id: string;
  situation_name?: string;
  baseline_plan_id?: string;
  baseline_plan_version?: number;
  baseline_plan_status?: string | null;
  baseline_plan_activated_at?: string | null;
  has_active_baseline?: boolean;
  resources: SimulationEntityTarget[];
  shelters: SimulationEntityTarget[];
  healthcare: SimulationEntityTarget[];
  healthcare_facilities?: SimulationEntityTarget[];
  volunteers: SimulationEntityTarget[];
  transports: SimulationEntityTarget[];
  routes: SimulationEntityTarget[];
  situation_severities?: string[];
  total_count: number;
}

export interface CreateSimulationRequest {
  situation_id: string;
  simulation_name?: string | null;
}

export interface AddScenarioRequest {
  scenario_type: ScenarioType;
  title: string;
  description: string;
  target_entity_type: string;
  target_entity_id: string;
  target_entity_name?: string | null;
  target_domain: OperationalDomain;
  simulated_value: Record<string, any>;
}

export interface RunSimulationResponse {
  success: boolean;
  simulation_id: string;
  status: SimulationStatus;
  baseline_plan_id: string;
  simulated_plan_id: string;
  total_changes: number;
  impact_level: string;
  explanation: string;
  diff_result: PlanDiffResult;
  is_simulation: boolean;
}

// ==========================================
// Phase 7: Notification & Alert Engine Types
// ==========================================

export type NotificationChannel = 'IN_APP' | 'WHATSAPP' | 'SMS';

export type NotificationDeliveryStatus =
  | 'PENDING'
  | 'QUEUED'
  | 'SENDING'
  | 'SENT'
  | 'DELIVERED'
  | 'UNDELIVERED'
  | 'READ'
  | 'FAILED'
  | 'NOT_CONFIGURED'
  | 'SKIPPED'
  | 'CANCELLED';

export type NotificationCategory =
  | 'CITIZEN_REPORT'
  | 'SITUATION'
  | 'COORDINATION_PLAN'
  | 'RESOURCE_LOGISTICS'
  | 'SHELTER_OPS'
  | 'HEALTHCARE_OPS'
  | 'VOLUNTEER_OPS'
  | 'TRANSPORT_ROUTE'
  | 'LIVE_MONITORING'
  | 'DYNAMIC_REPLANNING'
  | 'WHAT_IF_SIMULATION';

export type NotificationSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface NotificationDeepLink {
  entity_type?: string | null;
  entity_id?: string | null;
  situation_id?: string | null;
  coordination_plan_id?: string | null;
  view_hint?: string | null;
}

export interface NotificationUserView {
  notification_id: string;
  id?: string;
  is_read?: boolean;
  event_id?: string | null;
  category: NotificationCategory;
  event_type: string;
  severity: NotificationSeverity;
  title: string;
  message: string;
  deep_link?: NotificationDeepLink | null;
  is_simulation: boolean;
  metadata?: Record<string, any>;
  created_at: string;
  in_app_status: NotificationDeliveryStatus;
  read_at?: string | null;
  whatsapp_status: NotificationDeliveryStatus;
  sms_status?: NotificationDeliveryStatus;
}

export interface NotificationPreference {
  preference_id: string;
  user_id: string;
  in_app_enabled: boolean;
  whatsapp_enabled: boolean;
  sms_enabled: boolean;
  phone_number?: string | null;
  notify_critical: boolean;
  notify_high: boolean;
  notify_operational: boolean;
  notify_plan_updates: boolean;
  notify_monitoring: boolean;
  updated_at: string;
}

export interface NotificationPreferenceUpdate {
  in_app_enabled?: boolean;
  whatsapp_enabled?: boolean;
  sms_enabled?: boolean;
  phone_number?: string | null;
  notify_critical?: boolean;
  notify_high?: boolean;
  notify_operational?: boolean;
  notify_plan_updates?: boolean;
  notify_monitoring?: boolean;
}

export interface ChannelStatusResponse {
  in_app: {
    channel: string;
    status: string;
    configured: boolean;
  };
  whatsapp: {
    channel: string;
    status: string;
    configured: boolean;
    provider?: string;
  };
  sms?: {
    channel: string;
    status: string;
    configured: boolean;
    provider?: string;
    enabled?: boolean;
  };
}

// ==========================================
// Phase 8: Field Operations & Execution Types
// ==========================================

export type ResponseTaskStatus =
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'ASSIGNED'
  | 'ACCEPTED'
  | 'IN_PROGRESS'
  | 'COMPLETED'
  | 'REJECTED'
  | 'CANCELLED'
  | 'BLOCKED'
  | 'FAILED'
  | 'ESCALATED';

export type TaskType =
  | 'RESOURCE_DELIVERY'
  | 'SHELTER_ACTIVATION'
  | 'PATIENT_EVACUATION'
  | 'SEARCH_AND_RESCUE'
  | 'ROUTE_CLEARANCE'
  | 'GENERAL_FIELD_OPERATION';

export type FieldUpdateType =
  | 'ARRIVED'
  | 'TASK_STARTED'
  | 'TASK_COMPLETED'
  | 'TASK_BLOCKED'
  | 'TASK_FAILED'
  | 'RESOURCE_CONSUMED'
  | 'RESOURCE_DAMAGED'
  | 'ROUTE_BLOCKED'
  | 'MEDICAL_CONDITION_CHANGED'
  | 'ADDITIONAL_HELP_REQUIRED'
  | 'SHELTER_CAPACITY_CHANGED'
  | 'VEHICLE_UNAVAILABLE'
  | 'TEAM_UNAVAILABLE'
  | 'OTHER_OPERATIONAL_CHANGE';

export interface TaskLocation {
  name?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

export interface AssignedResourceItem {
  resource_id: string;
  resource_name: string;
  resource_type: string;
  allocated_quantity: number;
  unit: string;
  depot_location?: string | null;
  consumed_quantity?: number;
}

export interface FieldUpdateRecord {
  update_id: string;
  task_id: string;
  situation_id: string;
  actor_id: string;
  actor_name: string;
  actor_role: string;
  event_type: FieldUpdateType;
  message: string;
  location?: TaskLocation | null;
  details?: Record<string, any>;
  timestamp: string;
}

export interface ResponseTask {
  task_id: string;
  situation_id: string;
  plan_id: string;
  plan_version: number;
  task_type: TaskType;
  title: string;
  description: string;
  priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  status: ResponseTaskStatus;
  assigned_team_id?: string | null;
  assigned_team_name?: string | null;
  assigned_volunteer_ids: string[];
  assigned_volunteer_names: string[];
  assigned_vehicle_id?: string | null;
  assigned_vehicle_name?: string | null;
  assigned_vehicle_type?: string | null;
  assigned_resource_ids: string[];
  assigned_resources: AssignedResourceItem[];
  allocated_resources?: AssignedResourceItem[];
  assigned_vehicle_ids?: string[];
  source_plan_component: string;
  location?: TaskLocation | null;
  destination?: TaskLocation | null;
  route_id?: string | null;
  dependencies: string[];
  estimated_duration_minutes?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  completion_notes?: string | null;
  failure_reason?: string | null;
  blocked_reason?: string | null;
  field_updates: FieldUpdateRecord[];
  created_by?: string | null;
  approved_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface OperationsOverview {
  active_plans_count: number;
  total_tasks_count: number;
  active_tasks_count?: number;
  pending_tasks_count: number;
  approved_tasks_count: number;
  assigned_tasks_count: number;
  in_progress_tasks_count: number;
  completed_tasks_count: number;
  blocked_tasks_count: number;
  escalated_tasks_count: number;
  resources_in_use_count: number;
  active_teams_count: number;
  active_volunteers_count: number;
  active_vehicles_count: number;
}

export interface PaginatedTasksResponse {
  items: ResponseTask[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface IncidentResolutionSummary {
  situation_id: string;
  title: string;
  emergency_type: string;
  severity_level: string;
  final_status: string;
  total_citizen_reports: number;
  active_plan_versions: number;
  total_tasks_created: number;
  tasks_completed: number;
  tasks_blocked_or_failed: number;
  resources_utilized: any[];
  volunteers_involved_count: number;
  vehicles_involved_count: number;
  monitoring_events_count: number;
  replanning_iterations_count: number;
  notifications_sent_count: number;
  resolved_by?: string | null;
  resolved_at?: string | null;
  closed_by?: string | null;
  closed_at?: string | null;
  resolution_notes?: string | null;
  duration_hours: number;
  created_at: string;
  updated_at: string;
}

// ==========================================
// Healthcare Facilities & Hospital Capacity
// ==========================================

export type HealthcareFacilityType =
  | 'Hospital'
  | 'Trauma Center'
  | 'Clinic'
  | 'Specialty Center'
  | 'Field Hospital'
  | 'Maternity & Pediatric Center'
  | 'Other';

export type HealthcareOperationalStatus =
  | 'ACTIVE'
  | 'LIMITED'
  | 'CLOSED'
  | 'MAINTENANCE';

export interface HealthcareLocation {
  latitude: number;
  longitude: number;
  address: string;
  city: string;
  district: string;
  state: string;
  country: string;
  postal_code: string;
  zone?: string;
}

export interface HealthcareCapabilities {
  emergency_care: boolean;
  trauma_care: boolean;
  icu: boolean;
  surgery: boolean;
  oxygen_support: boolean;
  ventilator_support: boolean;
  ambulance_support: boolean;
  pediatric_care: boolean;
  burn_unit: boolean;
  other_capabilities: string[];
}

export interface HealthcareFacility {
  _id: string;
  id?: string;
  facility_id: string;
  facility_name: string;
  facility_type: HealthcareFacilityType;
  location: HealthcareLocation;
  total_beds: number;
  occupied_beds: number;
  available_beds: number;
  bed_occupancy_rate: number;
  total_icu_beds: number;
  occupied_icu_beds: number;
  available_icu_beds: number;
  icu_occupancy_rate: number;
  total_emergency_beds: number;
  occupied_emergency_beds: number;
  available_emergency_beds: number;
  emergency_occupancy_rate: number;
  ventilators_total: number;
  ventilators_available: number;
  oxygen_supported_beds: number;
  oxygen_available_capacity: number;
  capabilities: HealthcareCapabilities;
  status: HealthcareOperationalStatus;
  condition: string;
  accessibility: string;
  contact_phone?: string | null;
  contact_email?: string | null;
  operating_hours: string;
  created_by_id?: string | null;
  created_by_name?: string | null;
  last_updated_by_id?: string | null;
  last_updated_by_name?: string | null;
  last_updated: string;
  created_at: string;
  updated_at: string;
}

export interface PaginatedHealthcareFacilitiesResponse {
  items: HealthcareFacility[];
  total_count: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface HealthcareStatsResponse {
  total_facilities: number;
  active_facilities: number;
  total_available_beds: number;
  total_occupied_beds: number;
  total_beds: number;
  available_icu_beds: number;
  total_icu_beds: number;
  available_emergency_beds: number;
  total_emergency_beds: number;
  available_ventilators: number;
  total_ventilators: number;
  available_oxygen_capacity: number;
  total_oxygen_supported_beds: number;
  overall_bed_utilization: number;
  overall_icu_utilization: number;
}

export interface HealthcareFacilityCreatePayload {
  facility_name: string;
  facility_type: HealthcareFacilityType;
  location: HealthcareLocation;
  total_beds: number;
  occupied_beds: number;
  total_icu_beds: number;
  occupied_icu_beds: number;
  total_emergency_beds: number;
  occupied_emergency_beds: number;
  ventilators_total?: number;
  ventilators_available?: number;
  oxygen_supported_beds?: number;
  oxygen_available_capacity?: number;
  capabilities: HealthcareCapabilities;
  status: HealthcareOperationalStatus;
  condition?: string;
  accessibility?: string;
  contact_phone?: string;
  contact_email?: string;
  operating_hours?: string;
}

export interface HealthcareCapacityUpdatePayload {
  occupied_beds?: number;
  occupied_icu_beds?: number;
  occupied_emergency_beds?: number;
  ventilators_available?: number;
  oxygen_available_capacity?: number;
  reason?: string;
}

export interface PublicEmergencyHotspot {
  hotspot_id: string;
  latitude: number;
  longitude: number;
  severity_level: SeverityLevel;
  impact_radius_km: number;
  active_incident_count: number;
  emergency_type?: EmergencyType;
  general_area_name?: string;
  last_updated_at: string;
}

export interface PublicActiveHotspotsResponse {
  hotspots: PublicEmergencyHotspot[];
  total_active_hotspots: number;
  total_active_incidents: number;
  last_updated_at: string;
}

export interface OfficerMapDataResponse {
  view_mode: 'active' | 'history' | 'all';
  situations: SituationCluster[];
  reports: OfficerReportDetailResponse[];
  shelters: ResourceResponse[];
  total_active_situations: number;
  total_resolved_situations: number;
  total_active_reports: number;
  total_resolved_reports: number;
  last_updated_at: string;
}

// --- Sensor Network & IoT Simulation Types ---

export type SensorType = 'WATER_LEVEL' | 'RAINFALL' | 'TEMPERATURE' | 'SMOKE_AIR_QUALITY' | 'AQI';
export type SensorStatus = 'DRAFT' | 'ACTIVE' | 'PAUSED' | 'INACTIVE';
export type SensorReadingSource = 'MANUAL_SIMULATION' | 'LIVE_SIMULATION';
export type SensorAlertStatus = 'ACTIVE_BREACH' | 'RESOLVED_RECOVERED';
export type SimulationTrend = 'RISING' | 'FALLING' | 'FLUCTUATING';

export interface SensorLocation {
  latitude: number;
  longitude: number;
  address?: string | null;
  street_address?: string | null;
  landmark?: string | null;
  zone?: string | null;
  district?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  postal_code?: string | null;
}

export interface SensorCoverage {
  radius_meters: number;
  display_value?: number | null;
  display_unit?: string | null;
}

export interface Sensor {
  sensor_id: string;
  name: string;
  sensor_type: SensorType;
  status: SensorStatus;
  location_name: string;
  latitude: number;
  longitude: number;
  location?: SensorLocation | null;
  coverage?: SensorCoverage | null;
  unit: string;
  threshold: number;
  current_reading?: number | null;
  previous_reading?: number | null;
  last_updated?: string | null;
  in_alert: boolean;
  current_alert?: Record<string, any> | null;
  linked_situation_id?: string | null;
  active_stream_session_id?: string | null;
  is_streaming?: boolean;
  created_by?: string | null;
  created_by_name?: string | null;
  created_at: string;
  updated_at: string;
  description?: string | null;
}

export interface SensorCreatePayload {
  name: string;
  sensor_type: SensorType;
  location_name?: string;
  latitude?: number;
  longitude?: number;
  location?: Partial<SensorLocation>;
  coverage_radius_value?: number;
  coverage_radius_unit?: string;
  coverage?: Partial<SensorCoverage>;
  unit?: string;
  threshold: number;
  linked_situation_id?: string | null;
  description?: string | null;
}

export interface SensorUpdatePayload {
  name?: string;
  sensor_type?: SensorType;
  location_name?: string;
  latitude?: number;
  longitude?: number;
  location?: Partial<SensorLocation>;
  coverage_radius_value?: number;
  coverage_radius_unit?: string;
  coverage?: Partial<SensorCoverage>;
  unit?: string;
  threshold?: number;
  linked_situation_id?: string | null;
  description?: string | null;
}

export interface SensorReading {
  reading_id: string;
  sensor_id: string;
  value: number;
  unit: string;
  previous_value?: number | null;
  timestamp: string;
  source_type: SensorReadingSource;
  simulation: boolean;
  threshold: number;
  is_breach: boolean;
  created_by?: string | null;
  created_by_name?: string | null;
  notes?: string | null;
}

export interface SensorReadingPayload {
  value: number;
  source_type?: SensorReadingSource;
  simulation?: boolean;
  notes?: string | null;
}

export interface SensorAlert {
  alert_id: string;
  event_id: string;
  sensor_id: string;
  sensor_name: string;
  sensor_type: SensorType;
  reading_id: string;
  severity: SeverityLevel;
  threshold: number;
  current_value: number;
  previous_value?: number | null;
  unit: string;
  location_name: string;
  latitude: number;
  longitude: number;
  situation_id?: string | null;
  status: SensorAlertStatus;
  message: string;
  created_at: string;
  resolved_at?: string | null;
}

export interface LiveStreamStartPayload {
  starting_value: number;
  min_value: number;
  max_value: number;
  interval_seconds?: number;
  trend?: SimulationTrend;
  step_size?: number;
}

export interface LiveStreamSession {
  session_id: string;
  sensor_id: string;
  status: string;
  started_at: string;
  stopped_at?: string | null;
  configuration: Record<string, any>;
  readings_emitted: number;
}

export interface SensorStatsResponse {
  total_sensors: number;
  active_sensors: number;
  paused_sensors: number;
  inactive_sensors: number;
  draft_sensors: number;
  sensors_in_alert: number;
  total_readings_today: number;
  type_counts: Record<string, number>;
}

export interface PaginatedSensorsResponse {
  items: Sensor[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface PaginatedReadingsResponse {
  items: SensorReading[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface PaginatedAlertsResponse {
  items: SensorAlert[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

// ============================================================================
// PHASE C: FIELD OFFICER LIVE VERIFICATION & INCIDENT EVOLUTION TIMELINE
// ============================================================================

export type FieldVerificationStatus =
  | 'FIELD_VERIFIED'
  | 'PARTIALLY_VERIFIED'
  | 'NOT_FOUND'
  | 'CONDITION_CHANGED'
  | 'UNABLE_TO_VERIFY';

export type FieldObservationCategory =
  | 'INCIDENT_CONFIRMED'
  | 'INCIDENT_NOT_FOUND'
  | 'SEVERITY_CHANGED'
  | 'WATER_LEVEL_CHANGED'
  | 'FIRE_SPREADING'
  | 'ROAD_BLOCKED'
  | 'ROAD_CLEAR'
  | 'SHELTER_ACCESSIBLE'
  | 'SHELTER_INACCESSIBLE'
  | 'MEDICAL_NEED_OBSERVED'
  | 'RESOURCE_SHORTAGE_OBSERVED'
  | 'CONDITION_UNKNOWN';

export type IncidentEvolutionCategory =
  | 'REPORT'
  | 'EVIDENCE'
  | 'SENSOR'
  | 'CORROBORATION'
  | 'CONFLICT'
  | 'FIELD_VERIFICATION'
  | 'OFFICER_ACTION'
  | 'RESPONSE_PLAN'
  | 'FIELD_TASK'
  | 'REPLANNING'
  | 'RESOLUTION';

export interface FieldVerificationEvidenceMedia {
  media_id?: string;
  url?: string;
  content_hash?: string;
  captured_at?: string;
  latitude?: number | null;
  longitude?: number | null;
  accuracy_meters?: number | null;
  source?: string;
}

export interface FieldVerificationCreateRequest {
  target_type: 'CITIZEN_REPORT' | 'SITUATION' | 'GENERAL_FIELD';
  target_id: string;
  verification_status: FieldVerificationStatus;
  observation_category: FieldObservationCategory;
  latitude: number;
  longitude: number;
  accuracy_meters?: number | null;
  notes: string;
  evidence_media?: FieldVerificationEvidenceMedia | null;
  image_base64?: string | null;
  client_captured_at?: string | null;
}

export interface FieldVerificationRecord {
  verification_id: string;
  target_type: 'CITIZEN_REPORT' | 'SITUATION' | 'GENERAL_FIELD';
  target_id: string;
  responder_id: string;
  responder_name: string;
  responder_role: UserRole;
  badge_number?: string | null;
  department?: string | null;
  verification_status: FieldVerificationStatus;
  observation_category: FieldObservationCategory;
  responder_latitude: number;
  responder_longitude: number;
  gps_accuracy_meters?: number | null;
  target_latitude?: number | null;
  target_longitude?: number | null;
  distance_from_target_meters?: number | null;
  spatial_match_state: 'MATCH' | 'NEAR_MATCH' | 'MISMATCH' | 'UNAVAILABLE';
  notes: string;
  evidence_media?: FieldVerificationEvidenceMedia | null;
  submitted_at: string;
  audit_logged?: boolean;
}

export interface PaginatedFieldVerificationsResponse {
  items: FieldVerificationRecord[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface IncidentEvolutionEvent {
  event_id: string;
  timestamp: string;
  category: IncidentEvolutionCategory;
  event_type: string;
  title: string;
  summary: string;
  actor_name?: string | null;
  actor_role?: string | null;
  badge_number?: string | null;
  department?: string | null;
  distance_meters?: number | null;
  spatial_relation?: string | null;
  severity?: IncidentSeverity | null;
  details?: Record<string, any>;
  source_id?: string | null;
  source_collection?: string | null;
  is_conflict?: boolean;
  conflict_category?: string | null;
}

export interface IncidentEvolutionTimelineResponse {
  target_id: string;
  target_type: string;
  target_title?: string;
  total_events: number;
  category_counts: Record<string, number>;
  events: IncidentEvolutionEvent[];
  generated_at: string;
}

// ==========================================
// Phase D: Sensor Health & Stale Data Types
// ==========================================

export type SensorReportingState = 'NEVER_REPORTED' | 'HEALTHY' | 'STALE' | 'INACTIVE' | 'UNAVAILABLE';
export type SensorHealthState = 'HEALTHY' | 'STALE' | 'INACTIVE' | 'NEVER_REPORTED' | 'UNAVAILABLE' | 'IN_ALERT';

export interface SensorHealthDetail {
  sensor_id: string;
  name: string;
  sensor_type: SensorType;
  status: SensorStatus;
  location_name: string;
  latitude: number;
  longitude: number;
  location?: SensorLocation | null;
  coverage?: SensorCoverage | null;
  unit: string;
  threshold: number;
  reporting_state: SensorReportingState;
  health_state: SensorHealthState;
  last_reading_at?: string | null;
  reading_age_seconds?: number | null;
  reading_age_human: string;
  stale_threshold_seconds: number;
  latest_reading_id?: string | null;
  latest_reading_value?: number | null;
  previous_reading_value?: number | null;
  is_breach: boolean;
  in_alert: boolean;
  current_alert_id?: string | null;
  linked_situation_id?: string | null;
  is_usable_for_intelligence: boolean;
  reliability_score: number;
  reason: string;
  evaluated_at: string;
}

export interface SensorHealthSummary {
  total_sensors: number;
  healthy_count: number;
  stale_count: number;
  never_reported_count: number;
  inactive_count: number;
  unavailable_count: number;
  in_alert_count: number;
  stale_threshold_seconds: number;
  evaluated_at: string;
}

export interface SensorHealthResponse {
  summary: SensorHealthSummary;
  items: SensorHealthDetail[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

// ==========================================
// Phase D: Resource Bottleneck Intelligence Types
// ==========================================

export type BottleneckType =
  | 'RESOURCE_SHORTAGE'
  | 'ALLOCATION_CONTENTION'
  | 'HIGH_UTILIZATION'
  | 'NO_ELIGIBLE_RESOURCE'
  | 'LOCATION_CONSTRAINT'
  | 'CAPABILITY_CONSTRAINT'
  | 'TASK_DEPENDENCY'
  | 'TRANSPORT_CONSTRAINT'
  | 'STALE_RESOURCE_STATE';

export type BottleneckSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface AffectedSituationRef {
  situation_id: string;
  title: string;
  emergency_type?: string | null;
  required_quantity: number;
  urgency: NeedUrgency;
  severity_level?: string | null;
}

export interface AffectedTaskRef {
  task_id: string;
  situation_id: string;
  title: string;
  status: string;
  allocated_quantity: number;
  consumed_quantity: number;
}

export interface ContentionDetail {
  total_demand: number;
  eligible_supply: number;
  contention_deficit: number;
  competing_situations: Array<{
    situation_id: string;
    title: string;
    demanded: number;
  }>;
}

export interface AlternativeResourceOption {
  resource_id: string;
  name: string;
  resource_type: ResourceType;
  quantity_available: number;
  unit: string;
  location_name?: string | null;
  distance_km?: number | null;
  feasibility_notes?: string | null;
}

export interface ResourceBottleneckItem {
  bottleneck_id: string;
  resource_type: ResourceType;
  resource_name?: string | null;
  severity: BottleneckSeverity;
  bottleneck_type: BottleneckType;
  required: number;
  available: number;
  allocated: number;
  consumed: number;
  shortfall: number;
  unit: string;
  affected_situations: AffectedSituationRef[];
  affected_tasks: AffectedTaskRef[];
  contention?: ContentionDetail | null;
  alternative_options: AlternativeResourceOption[];
  why_bottleneck: string;
  recommended_action: string;
  supporting_records: Record<string, any>;
  generated_at: string;
}

export interface ResourceBottleneckSummary {
  total_bottlenecks: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  total_shortfall_by_type: Record<string, number>;
  affected_situations_count: number;
  contention_count: number;
  generated_at: string;
}

export interface ResourceBottlenecksResponse {
  summary: ResourceBottleneckSummary;
  items: ResourceBottleneckItem[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

// -------------------------------------------------------------
// Phase 1 Predictive Intelligence & Escalation Forecasting Types
// -------------------------------------------------------------

export type PredictiveDataSufficiency =
  | 'SUFFICIENT_DATA'
  | 'LIMITED_DATA'
  | 'INSUFFICIENT_DATA'
  | 'NO_DATA';

export type EscalationRiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type TrendDirection = 'RISING' | 'STABLE' | 'FALLING' | 'UNKNOWN';

export interface PredictiveFeature {
  name: string;
  value: number;
  source: string;
  time_window: string;
  data_points: number;
  raw_records?: number | null;
  aggregation_method?: string | null;
  metadata?: Record<string, any>;
  description?: string | null;
}

export interface PredictiveEvidenceItem {
  source_type: string;
  source_id: string;
  timestamp: string;
  contribution: string;
  weight: number;
}

export interface WeatherForecastPeriod {
  horizon_minutes: number;
  forecast_timestamp: string;
  precipitation_mm?: number | null;
  precipitation_probability?: number | null;
  temperature_c?: number | null;
  wind_speed_mps?: number | null;
  wind_gust_mps?: number | null;
  condition?: string | null;
}

export interface WeatherEvidence {
  provider: string;
  fetched_at: string;
  observation_timestamp?: string | null;
  latitude: number;
  longitude: number;
  temperature_c?: number | null;
  precipitation_mm?: number | null;
  precipitation_probability?: number | null;
  humidity_percent?: number | null;
  wind_speed_mps?: number | null;
  wind_gust_mps?: number | null;
  condition?: string | null;
  forecast_periods: WeatherForecastPeriod[];
  data_status: 'FRESH' | 'STALE' | 'UNAVAILABLE' | 'ERROR';
  freshness_seconds?: number | null;
  error_detail?: string | null;
}

export interface ForecastHorizonResult {
  horizon_minutes: number;
  risk_level: EscalationRiskLevel;
  risk_score: number;
  raw_score?: number | null;
  projected_score?: number | null;
  is_capped?: boolean;
  ceiling_threshold?: number;
  trend: TrendDirection;
  data_status: PredictiveDataSufficiency;
  confidence_score: number;
  confidence_label: string;
  contributing_factors: string[];
  limitations: string[];
  weather_contribution?: number | null;
  sensor_contribution?: number | null;
  incident_contribution?: number | null;
  field_contribution?: number | null;
  monitoring_contribution?: number | null;
  task_contribution?: number | null;
  weather_forecast?: WeatherForecastPeriod | null;
}

export interface IncidentPredictionResponse {
  incident_id: string;
  incident_title?: string | null;
  emergency_type?: string | null;
  prediction_status: string;
  data_status: PredictiveDataSufficiency;
  current_authoritative_severity: string;
  current_severity_score: number;
  is_officer_override: boolean;
  forecast: ForecastHorizonResult;
  horizons: Record<string, ForecastHorizonResult>;
  all_horizons_capped?: boolean;
  independent_sources_count?: number;
  independent_physical_sources_count?: number;
  external_context_sources_count?: number;
  weather?: WeatherEvidence | null;
  features: PredictiveFeature[];
  missing_features: string[];
  evidence: PredictiveEvidenceItem[];
  data_points_used: Record<string, number>;
  historical_window_minutes: number;
  model: Record<string, string>;
  limitations: string[];
  advisory_notice: string;
  generated_at: string;
}

export interface PredictiveTrendPoint {
  time_label: string;
  minutes_from_now: number;
  risk_score: number;
  risk_level: string;
  is_forecast: boolean;
  data_status: string;
}

export interface PredictiveTrendResponse {
  incident_id: string;
  data_status: string;
  trend_direction: string;
  historical_window_minutes: number;
  timeline_points: PredictiveTrendPoint[];
  summary: string;
  generated_at: string;
}

export interface PredictiveFeaturesResponse {
  incident_id: string;
  historical_window_minutes: number;
  data_status: string;
  features: PredictiveFeature[];
  missing_features: string[];
  total_records_evaluated: number;
  records_by_source: Record<string, number>;
  generated_at: string;
}

export interface PredictiveHealthResponse {
  status: string;
  engine_version: string;
  model_name: string;
  supported_horizons_minutes: number[];
  default_window_minutes: number;
  zero_dummy_data_enforced: boolean;
  advisory_mode_enforced: boolean;
  checked_at: string;
}


