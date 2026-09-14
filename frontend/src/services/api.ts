import axios from 'axios';
import type {
  OfficerReportStatsResponse,
  PaginatedOfficerReportsResponse,
  OfficerReportDetailResponse,
  ReportRejectResponse,
  TimelineEvent,
  ReportPriority,
  ReportStatus,
  ResourceResponse,
  ResourceCreatePayload,
  ResourceUpdatePayload,
  PaginatedResourcesResponse,
  ResourceStatsResponse,
  EmergencyNeedItem,
  NeedsAssessmentResponse,
  AINeedsSuggestionResponse,
  ResourceMatchingResponse,
  AllocationCreateRequest,
  AllocationResponse,
  UserResponse,
  MonitoringEvent,
  ChangeImpactResult,
  PaginatedMonitoringEventsResponse,
  MonitoringStatsResponse,
  AcknowledgeEventResponse,
  CoordinationPlan,
  PlanDiffResult,
  PlanApprovalRequest,
  PlanActivationResponse,
  PlanModifyRequest,
  PlanRejectRequest,
  SimulationRun,
  SimulationTargetLookupResponse,
  CreateSimulationRequest,
  AddScenarioRequest,
  RunSimulationResponse,
  PublicActiveHotspotsResponse,
  OfficerMapDataResponse,
  Sensor,
  SensorCreatePayload,
  SensorUpdatePayload,
  SensorReading,
  SensorReadingPayload,
  SensorAlert,
  LiveStreamStartPayload,
  LiveStreamSession,
  SensorStatsResponse,
  PaginatedSensorsResponse,
  PaginatedReadingsResponse,
  PaginatedAlertsResponse,
  EvidenceVerificationResult,
  CorroborationResult,
  SensorHealthDetail,
  SensorHealthResponse,
  ResourceBottleneckItem,
  ResourceBottlenecksResponse,
  PushSubscriptionCreate,
  CitizenSafetyGuidance,
  CitizenSafetyGuidanceResponse,
  SafetyGuidanceReviewRequest,
} from '../types';


export const getApiBaseUrl = (): string => {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl && envUrl.startsWith('http')) {
    return envUrl.replace(/\/+$/, '');
  }

  // Detect non-localhost production environments (e.g. Vercel deployment)
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '0.0.0.0';
    if (!isLocalhost || import.meta.env.PROD) {
      return 'https://resilience-ai-s2i3.onrender.com/api/v1';
    }
  }

  return envUrl ? envUrl.replace(/\/+$/, '') : '/api/v1';
};

const api = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 45000,
});

// Request interceptor to attach JWT token from localStorage
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('resilience_auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor to handle unauthorized access
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      // Token expired or invalid
      // Do not redirect automatically if currently on a login page
      const currentPath = window.location.pathname;
      if (
        !currentPath.includes('/login') &&
        !currentPath.includes('/register') &&
        !currentPath.includes('/forgot-password') &&
        currentPath !== '/'
      ) {
        localStorage.removeItem('resilience_auth_token');
        localStorage.removeItem('resilience_auth_user');
        window.location.href = '/';
      }
    }
    return Promise.reject(error);
  }
);

export default api;

// Phase 1: Citizen Emergency Reporting Services
export const sendCitizenOTP = async (phone: string, name?: string) => {
  const response = await api.post('/citizen/otp/send', { phone, name });
  return response.data;
};

export const verifyCitizenOTP = async (phone: string, otp: string) => {
  const response = await api.post('/citizen/otp/verify', { phone, otp });
  return response.data;
};

export const uploadCitizenMedia = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/citizen/upload-media', formData);
  return response.data;
};

export const createEmergencyReport = async (reportData: any) => {
  const response = await api.post('/citizen/reports', reportData);
  return response.data;
};

export const getEmergencyReport = async (reportId: string) => {
  const response = await api.get(`/citizen/reports/${reportId}`);
  return response.data;
};

export const updateCitizenReport = async (
  reportId: string,
  payload: {
    citizen_token?: string;
    description?: string;
    citizen_impact_level?: string;
    full_name?: string;
    phone?: string;
    additional_notes?: string;
  },
  citizenToken?: string
) => {
  const headers: Record<string, string> = {};
  const token = citizenToken || payload.citizen_token;
  if (token) {
    headers['X-Citizen-Token'] = token;
  }
  const response = await api.patch(`/citizen/reports/${reportId}`, payload, { headers });
  return response.data;
};

export const reverseGeocodeLocation = async (lat: number, lon: number) => {
  const response = await api.get('/citizen/location/reverse-geocode', {
    params: { lat, lon },
  });
  return response.data;
};

export const listEmergencyReports = async (params?: { status?: string; emergency_type?: string }) => {
  const response = await api.get('/citizen/reports', { params });
  return response.data;
};

export const getActiveHotspots = async (): Promise<PublicActiveHotspotsResponse> => {
  const response = await api.get<PublicActiveHotspotsResponse>('/public/map/active-hotspots');
  return response.data;
};

export const getOfficerMapData = async (params?: {
  view_mode?: 'active' | 'history' | 'all';
  emergency_type?: string;
  severity_level?: string;
}): Promise<OfficerMapDataResponse> => {
  const response = await api.get<OfficerMapDataResponse>('/map/officer/data', { params });
  return response.data;
};

// Phase 2: Emergency Operations & Situation Awareness Services
export const getOfficerReportStats = async (): Promise<OfficerReportStatsResponse> => {
  const response = await api.get<OfficerReportStatsResponse>('/officer/reports/stats');
  return response.data;
};

export const getOfficerReports = async (params?: {
  status?: ReportStatus | string;
  priority?: ReportPriority | string;
  emergency_type?: string;
  search?: string;
  page?: number;
  limit?: number;
}): Promise<PaginatedOfficerReportsResponse> => {
  const response = await api.get<PaginatedOfficerReportsResponse>('/officer/reports', { params });
  return response.data;
};

export const getOfficerReportById = async (reportId: string): Promise<OfficerReportDetailResponse> => {
  const response = await api.get<OfficerReportDetailResponse>(`/officer/reports/${reportId}`);
  return response.data;
};

export const acknowledgeOfficerReport = async (reportId: string): Promise<OfficerReportDetailResponse> => {
  const response = await api.post<OfficerReportDetailResponse>(`/officer/reports/${reportId}/acknowledge`);
  return response.data;
};

export const rejectOfficerReport = async (
  reportId: string,
  reason: string
): Promise<ReportRejectResponse> => {
  const response = await api.post<ReportRejectResponse>(`/officer/reports/${reportId}/reject`, { reason });
  return response.data;
};

export const updateOfficerReportPriority = async (
  reportId: string,
  priority: ReportPriority
): Promise<OfficerReportDetailResponse> => {
  const response = await api.patch<OfficerReportDetailResponse>(`/officer/reports/${reportId}/priority`, { priority });
  return response.data;
};

export const updateOfficerReportStatus = async (
  reportId: string,
  status: ReportStatus,
  reason?: string
): Promise<OfficerReportDetailResponse> => {
  const response = await api.patch<OfficerReportDetailResponse>(`/officer/reports/${reportId}/status`, { status, reason });
  return response.data;
};

export const addOfficerNote = async (
  reportId: string,
  note: string
): Promise<OfficerReportDetailResponse> => {
  const response = await api.post<OfficerReportDetailResponse>(`/officer/reports/${reportId}/notes`, { note });
  return response.data;
};

export const getOfficerReportTimeline = async (reportId: string): Promise<TimelineEvent[]> => {
  const response = await api.get<TimelineEvent[]>(`/officer/reports/${reportId}/timeline`);
  return response.data;
};

export const getReportEvidenceVerification = async (reportId: string): Promise<EvidenceVerificationResult> => {
  const response = await api.get<EvidenceVerificationResult>(`/citizen/reports/${reportId}/evidence-verification`);
  return response.data;
};

export const getReportCorroboration = async (reportId: string): Promise<CorroborationResult> => {
  const response = await api.get<CorroborationResult>(`/citizen/reports/${reportId}/corroboration`);
  return response.data;
};

export const getSituationCorroboration = async (situationId: string): Promise<CorroborationResult> => {
  const response = await api.get<CorroborationResult>(`/situations/${situationId}/corroboration`);
  return response.data;
};

export const analyzeOfficerVisualEvidence = async (reportId: string): Promise<OfficerReportDetailResponse> => {
  const response = await api.post<OfficerReportDetailResponse>(`/officer/reports/${reportId}/analyze-visual-evidence`);
  return response.data;
};

export const extractOfficerTextEvidence = async (reportId: string): Promise<OfficerReportDetailResponse> => {
  const response = await api.post<OfficerReportDetailResponse>(`/officer/reports/${reportId}/extract-text-evidence`);
  return response.data;
};


// Google OAuth 2.0 Helpers
export const getGoogleAuthUrl = async (intendedRole?: string, redirectUri?: string) => {
  const response = await api.get<{ auth_url: string; client_id: string; redirect_uri: string }>(
    '/auth/google/url',
    {
      params: {
        intended_role: intendedRole,
        redirect_uri: redirectUri,
      },
    }
  );
  return response.data;
};

export const exchangeGoogleCallback = async (data: {
  code?: string;
  state?: string;
  id_token?: string;
  redirect_uri?: string;
  intended_role?: string;
}) => {
  const response = await api.post('/auth/google/callback', data);
  return response.data;
};

// Phase 3: Emergency Resource Coordination Services
export const getResourceStats = async (params?: {
  domain?: string;
  resource_type?: string;
  resource_types?: string[];
}): Promise<ResourceStatsResponse> => {
  const response = await api.get<ResourceStatsResponse>('/resources/stats', { params });
  return response.data;
};

export const getResources = async (params?: {
  domain?: string;
  resource_type?: string;
  resource_types?: string[];
  status?: string;
  zone?: string;
  search?: string;
  page?: number;
  limit?: number;
}): Promise<PaginatedResourcesResponse> => {
  const response = await api.get<PaginatedResourcesResponse>('/resources', { params });
  return response.data;
};

export const listResources = getResources;

export const getAllAllocations = async (status?: string, limit: number = 50): Promise<AllocationResponse[]> => {
  const response = await api.get<AllocationResponse[]>('/needs/allocations', {
    params: { status: status || undefined, limit },
  });
  return response.data;
};

export const getResourceById = async (resourceId: string): Promise<ResourceResponse> => {
  const response = await api.get<ResourceResponse>(`/resources/${resourceId}`);
  return response.data;
};

export const createResource = async (payload: ResourceCreatePayload): Promise<ResourceResponse> => {
  const response = await api.post<ResourceResponse>('/resources', payload);
  return response.data;
};

export const updateResource = async (resourceId: string, payload: ResourceUpdatePayload): Promise<ResourceResponse> => {
  const response = await api.patch<ResourceResponse>(`/resources/${resourceId}`, payload);
  return response.data;
};

export const updateResourceQuantity = async (
  resourceId: string,
  quantity_available: number,
  quantity_total?: number,
  reason?: string
): Promise<ResourceResponse> => {
  const response = await api.patch<ResourceResponse>(`/resources/${resourceId}/quantity`, {
    quantity_available,
    quantity_total,
    reason,
  });
  return response.data;
};

export const updateResourceStatus = async (
  resourceId: string,
  status: string,
  reason?: string
): Promise<ResourceResponse> => {
  const response = await api.patch<ResourceResponse>(`/resources/${resourceId}/status`, { status, reason });
  return response.data;
};

// Phase 3: Needs Assessment & AI Suggestions
export const getReportNeeds = async (reportId: string): Promise<NeedsAssessmentResponse | null> => {
  const response = await api.get<NeedsAssessmentResponse | null>(`/officer/reports/${reportId}/needs`);
  return response.data;
};

export const createOrUpdateReportNeeds = async (
  reportId: string,
  needs: EmergencyNeedItem[]
): Promise<NeedsAssessmentResponse> => {
  const response = await api.post<NeedsAssessmentResponse>(`/officer/reports/${reportId}/needs`, { needs });
  return response.data;
};

export const getAINeedsSuggestions = async (reportId: string): Promise<AINeedsSuggestionResponse> => {
  const response = await api.post<AINeedsSuggestionResponse>(`/officer/reports/${reportId}/ai/needs-suggestion`);
  return response.data;
};

export const runResourceMatching = async (reportId: string): Promise<ResourceMatchingResponse> => {
  const response = await api.post<ResourceMatchingResponse>(`/officer/reports/${reportId}/resource-matching`);
  return response.data;
};

// Phase 3: Resource Allocations
export const getReportAllocations = async (reportId: string): Promise<AllocationResponse[]> => {
  const response = await api.get<AllocationResponse[]>(`/officer/reports/${reportId}/allocations`);
  return response.data;
};

export const proposeAllocation = async (
  reportId: string,
  payload: AllocationCreateRequest
): Promise<AllocationResponse> => {
  const response = await api.post<AllocationResponse>(`/officer/reports/${reportId}/allocations`, payload);
  return response.data;
};

export const approveAllocation = async (allocationId: string): Promise<AllocationResponse> => {
  const response = await api.post<AllocationResponse>(`/officer/allocations/${allocationId}/approve`);
  return response.data;
};

export const rejectAllocation = async (allocationId: string, reason?: string): Promise<AllocationResponse> => {
  const response = await api.post<AllocationResponse>(`/officer/allocations/${allocationId}/reject`, { reason });
  return response.data;
};

export const updateAllocationStatus = async (
  allocationId: string,
  status: string,
  reason?: string
): Promise<AllocationResponse> => {
  const response = await api.patch<AllocationResponse>(`/officer/allocations/${allocationId}/status`, null, {
    params: { status_to_set: status },
    data: { reason },
  });
  return response.data;
};

// Phase 3 & 4: Officer Volunteer Network and Audit Logs
export const listOfficerVolunteers = async (): Promise<UserResponse[]> => {
  const response = await api.get<UserResponse[]>('/officer/volunteers');
  return response.data;
};

export const listOfficerAuditLogs = async (limit: number = 50): Promise<any[]> => {
  const response = await api.get<any[]>('/officer/audit-logs', { params: { limit } });
  return response.data;
};

// Phase 6: Live Monitoring & Change Impact Analysis APIs
export const getMonitoringEvents = async (params?: {
  page?: number;
  limit?: number;
  event_type?: string;
  source_type?: string;
  impact_level?: string;
  status?: string;
  situation_id?: string;
  coordination_plan_id?: string;
  is_impacted?: boolean;
  search?: string;
}): Promise<PaginatedMonitoringEventsResponse> => {
  const response = await api.get<PaginatedMonitoringEventsResponse>('/officer/monitoring/events', { params });
  return response.data;
};

export const getMonitoringEventById = async (eventId: string): Promise<MonitoringEvent> => {
  const response = await api.get<MonitoringEvent>(`/officer/monitoring/events/${eventId}`);
  return response.data;
};

export const getEventImpact = async (eventId: string): Promise<ChangeImpactResult> => {
  const response = await api.get<ChangeImpactResult>(`/officer/monitoring/events/${eventId}/impact`);
  return response.data;
};

export const listRecentImpacts = async (params?: {
  limit?: number;
  situation_id?: string;
}): Promise<ChangeImpactResult[]> => {
  const response = await api.get<ChangeImpactResult[]>('/officer/monitoring/impacts', { params });
  return response.data;
};

export const getMonitoringStats = async (): Promise<MonitoringStatsResponse> => {
  const response = await api.get<MonitoringStatsResponse>('/officer/monitoring/stats');
  return response.data;
};

export const acknowledgeMonitoringEvent = async (
  eventId: string,
  notes?: string
): Promise<AcknowledgeEventResponse> => {
  const response = await api.post<AcknowledgeEventResponse>(
    `/officer/monitoring/events/${eventId}/acknowledge`,
    { notes }
  );
  return response.data;
};

export const reprocessMonitoringEvent = async (eventId: string): Promise<ChangeImpactResult> => {
  const response = await api.post<ChangeImpactResult>(`/officer/monitoring/reprocess/${eventId}`);
  return response.data;
};

// Phase 6.3 & 6.4: Dynamic Re-Planning & Human Approval APIs
export const triggerEventReplanning = async (eventId: string): Promise<CoordinationPlan> => {
  const response = await api.post<CoordinationPlan>(`/officer/monitoring/events/${eventId}/replan`);
  return response.data;
};

export const getPlanDiff = async (planId: string): Promise<PlanDiffResult> => {
  const response = await api.get<PlanDiffResult>(`/officer/monitoring/plans/${planId}/diff`);
  return response.data;
};

export const getSituationPlanHistory = async (situationId: string): Promise<CoordinationPlan[]> => {
  const response = await api.get<CoordinationPlan[]>(`/officer/monitoring/situations/${situationId}/plan-history`);
  return response.data;
};

export const approveAndActivatePlan = async (
  planId: string,
  payload: PlanApprovalRequest
): Promise<PlanActivationResponse> => {
  const response = await api.post<PlanActivationResponse>(`/officer/monitoring/plans/${planId}/approve`, payload);
  return response.data;
};

export const modifyRevisedPlan = async (
  planId: string,
  payload: PlanModifyRequest
): Promise<CoordinationPlan> => {
  const response = await api.post<CoordinationPlan>(`/officer/monitoring/plans/${planId}/modify`, payload);
  return response.data;
};

export const rejectRevisedPlan = async (
  planId: string,
  payload: PlanRejectRequest
): Promise<CoordinationPlan> => {
  const response = await api.post<CoordinationPlan>(`/officer/monitoring/plans/${planId}/reject`, payload);
  return response.data;
};

// ==========================================
// Phase 6.5: Simulation / What-If Engine APIs
// ==========================================

export const createSimulation = async (
  payload: CreateSimulationRequest
): Promise<SimulationRun> => {
  const response = await api.post<SimulationRun>('/officer/simulations', payload);
  return response.data;
};

export const listSimulations = async (params?: {
  situation_id?: string;
  status?: string;
  limit?: number;
}): Promise<SimulationRun[]> => {
  const response = await api.get<SimulationRun[]>('/officer/simulations', { params });
  return response.data;
};

export const getSimulationTargets = async (
  situationId: string
): Promise<SimulationTargetLookupResponse> => {
  const response = await api.get<SimulationTargetLookupResponse>(
    `/officer/simulations/targets/${situationId}`
  );
  return response.data;
};

export const getSimulation = async (
  simulationId: string
): Promise<SimulationRun> => {
  const response = await api.get<SimulationRun>(`/officer/simulations/${simulationId}`);
  return response.data;
};

export const addSimulationScenario = async (
  simulationId: string,
  payload: AddScenarioRequest
): Promise<SimulationRun> => {
  const response = await api.post<SimulationRun>(
    `/officer/simulations/${simulationId}/scenarios`,
    payload
  );
  return response.data;
};

export const removeSimulationScenario = async (
  simulationId: string,
  scenarioId: string
): Promise<SimulationRun> => {
  const response = await api.delete<SimulationRun>(
    `/officer/simulations/${simulationId}/scenarios/${scenarioId}`
  );
  return response.data;
};

export const runSimulation = async (
  simulationId: string
): Promise<RunSimulationResponse> => {
  const response = await api.post<RunSimulationResponse>(
    `/officer/simulations/${simulationId}/run`
  );
  return response.data;
};

export const getSimulationDiff = async (
  simulationId: string
): Promise<PlanDiffResult> => {
  const response = await api.get<PlanDiffResult>(
    `/officer/simulations/${simulationId}/diff`
  );
  return response.data;
};

export const discardSimulation = async (
  simulationId: string,
  reason?: string
): Promise<SimulationRun> => {
  const response = await api.post<SimulationRun>(
    `/officer/simulations/${simulationId}/discard`,
    {},
    { params: { reason } }
  );
  return response.data;
};

// ==========================================
// Platform Administration & Profile APIs
// ==========================================

export const getPlatformConfig = async () => {
  const response = await api.get('/system/config');
  return response.data;
};

export const updatePlatformConfig = async (payload: any) => {
  const response = await api.put('/system/config', payload);
  return response.data;
};

export const updateUserProfile = async (payload: any) => {
  const response = await api.patch('/users/me/profile', payload);
  return response.data;
};

export const getAdminAuditLogs = async (params?: { limit?: number; event_type?: string }) => {
  const response = await api.get<any[]>('/users/audit-logs', { params });
  return response.data;
};

// ==========================================
// IoT Sensor Network & Live Simulation APIs
// ==========================================

export const createSensor = async (payload: SensorCreatePayload): Promise<Sensor> => {
  const response = await api.post<Sensor>('/sensors', payload);
  return response.data;
};

export const updateSensor = async (sensorId: string, payload: SensorUpdatePayload): Promise<Sensor> => {
  const response = await api.put<Sensor>(`/sensors/${sensorId}`, payload);
  return response.data;
};

export const getSensors = async (params?: {
  sensor_type?: string;
  status?: string;
  in_alert?: boolean;
  linked_situation_id?: string;
  search?: string;
  page?: number;
  limit?: number;
}): Promise<PaginatedSensorsResponse> => {
  const response = await api.get<PaginatedSensorsResponse>('/sensors', { params });
  return response.data;
};

export const getSensorStats = async (): Promise<SensorStatsResponse> => {
  const response = await api.get<SensorStatsResponse>('/sensors/stats');
  return response.data;
};

export const getSensor = async (sensorId: string): Promise<Sensor> => {
  const response = await api.get<Sensor>(`/sensors/${sensorId}`);
  return response.data;
};

export const activateSensor = async (sensorId: string): Promise<Sensor> => {
  const response = await api.post<Sensor>(`/sensors/${sensorId}/activate`);
  return response.data;
};

export const pauseSensor = async (sensorId: string): Promise<Sensor> => {
  const response = await api.post<Sensor>(`/sensors/${sensorId}/pause`);
  return response.data;
};

export const resumeSensor = async (sensorId: string): Promise<Sensor> => {
  const response = await api.post<Sensor>(`/sensors/${sensorId}/resume`);
  return response.data;
};

export const deactivateSensor = async (sensorId: string): Promise<Sensor> => {
  const response = await api.post<Sensor>(`/sensors/${sensorId}/deactivate`);
  return response.data;
};

export const sendSensorReading = async (
  sensorId: string,
  payload: SensorReadingPayload
): Promise<{ success: boolean; reading: SensorReading; transition_type: string; is_breach: boolean; alert?: SensorAlert | null }> => {
  const response = await api.post(`/sensors/${sensorId}/readings`, payload);
  return response.data;
};

export const getSensorReadings = async (
  sensorId: string,
  params?: { page?: number; limit?: number }
): Promise<PaginatedReadingsResponse> => {
  const response = await api.get<PaginatedReadingsResponse>(`/sensors/${sensorId}/readings`, { params });
  return response.data;
};

export const getSensorEvents = async (
  sensorId: string,
  params?: { status?: string; page?: number; limit?: number }
): Promise<PaginatedAlertsResponse> => {
  const response = await api.get<PaginatedAlertsResponse>(`/sensors/${sensorId}/events`, { params });
  return response.data;
};

export const startLiveStream = async (
  sensorId: string,
  payload: LiveStreamStartPayload
): Promise<LiveStreamSession> => {
  const response = await api.post<LiveStreamSession>(`/sensors/${sensorId}/live-stream/start`, payload);
  return response.data;
};

export const stopLiveStream = async (
  sensorId: string
): Promise<{ success: boolean; message: string; session?: LiveStreamSession | null }> => {
  const response = await api.post(`/sensors/${sensorId}/live-stream/stop`);
  return response.data;
};

export const getLiveStreamStatus = async (
  sensorId: string
): Promise<{ is_streaming: boolean; session?: LiveStreamSession | null }> => {
  const response = await api.get(`/sensors/${sensorId}/live-stream/status`);
  return response.data;
};

// ==========================================
// Phase D: Sensor Health & Stale Data APIs
// ==========================================

export const getSensorsHealth = async (params?: {
  sensor_type?: string;
  health_state?: string;
  status?: string;
  linked_situation_id?: string;
  zone?: string;
  stale_threshold_seconds?: number;
  page?: number;
  limit?: number;
}): Promise<SensorHealthResponse> => {
  const response = await api.get<SensorHealthResponse>('/sensors/health', { params });
  return response.data;
};

export const getSensorHealthDetail = async (
  sensorId: string,
  staleThresholdSeconds?: number
): Promise<SensorHealthDetail> => {
  const response = await api.get<SensorHealthDetail>(`/sensors/${sensorId}/health`, {
    params: staleThresholdSeconds ? { stale_threshold_seconds: staleThresholdSeconds } : undefined,
  });
  return response.data;
};

// ==========================================
// Phase D: Resource Bottleneck Intelligence APIs
// ==========================================

export const getResourceBottlenecks = async (params?: {
  situation_id?: string;
  resource_type?: string;
  severity?: string;
  zone?: string;
  page?: number;
  limit?: number;
}): Promise<ResourceBottlenecksResponse> => {
  const response = await api.get<ResourceBottlenecksResponse>('/resources/bottlenecks', { params });
  return response.data;
};

export const getResourceBottleneckDetail = async (
  bottleneckId: string
): Promise<ResourceBottleneckItem> => {
  const response = await api.get<ResourceBottleneckItem>(`/resources/bottlenecks/${bottleneckId}`);
  return response.data;
};

// ==========================================
// Phase 1: Live Citizen Safety Guidance & Web Push APIs
// ==========================================

export const getVapidPublicKey = async (): Promise<{ success: boolean; vapid_public_key: string }> => {
  const response = await api.get<{ success: boolean; vapid_public_key: string }>('/citizen/push/vapid-public-key');
  return response.data;
};

export const subscribeWebPush = async (
  payload: PushSubscriptionCreate
): Promise<{ success: boolean; subscription_id: string; status: string; message: string }> => {
  const response = await api.post<{ success: boolean; subscription_id: string; status: string; message: string }>(
    '/citizen/push/subscribe',
    payload
  );
  return response.data;
};

export const unsubscribeWebPush = async (
  endpoint: string
): Promise<{ success: boolean; message: string }> => {
  const response = await api.delete<{ success: boolean; message: string }>('/citizen/push/subscribe', {
    params: { endpoint },
  });
  return response.data;
};

export const triggerTestWebPush = async (
  reportId?: string
): Promise<{ success: boolean; sent_count: number; total_targets: number; message: string }> => {
  const response = await api.post<{ success: boolean; sent_count: number; total_targets: number; message: string }>(
    '/citizen/push/test',
    null,
    { params: reportId ? { report_id: reportId } : {} }
  );
  return response.data;
};

export const getSafetyGuidanceByToken = async (
  token: string
): Promise<CitizenSafetyGuidanceResponse> => {
  const response = await api.get<CitizenSafetyGuidanceResponse>(`/citizen/safety-guidance/${token}`);
  return response.data;
};

export const getSafetyGuidanceForReport = async (
  reportId: string
): Promise<CitizenSafetyGuidanceResponse> => {
  const response = await api.get<CitizenSafetyGuidanceResponse>(`/citizen/reports/${reportId}/safety-guidance`);
  return response.data;
};

export const refreshSafetyGuidanceForReport = async (
  reportId: string
): Promise<CitizenSafetyGuidanceResponse> => {
  const response = await api.post<CitizenSafetyGuidanceResponse>(
    `/citizen/reports/${reportId}/safety-guidance/refresh`
  );
  return response.data;
};

export const reviewOfficerSafetyGuidance = async (
  guidanceId: string,
  reviewData: SafetyGuidanceReviewRequest
): Promise<{
  success: boolean;
  guidance_id: string;
  approval_state: string;
  message: string;
  guidance: CitizenSafetyGuidance;
}> => {
  const response = await api.post<{
    success: boolean;
    guidance_id: string;
    approval_state: string;
    message: string;
    guidance: CitizenSafetyGuidance;
  }>(`/citizen/officer/safety-guidance/${guidanceId}/review`, reviewData);
  return response.data;
};

export const getSafetyGuidanceHistory = async (
  token: string
): Promise<{
  success: boolean;
  report_id: string;
  total_versions: number;
  versions: any[];
}> => {
  const response = await api.get<{
    success: boolean;
    report_id: string;
    total_versions: number;
    versions: any[];
  }>(`/citizen/safety-guidance/${token}/history`);
  return response.data;
};







