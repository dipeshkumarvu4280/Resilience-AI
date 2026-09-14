import api from './api';
import type {
  ResponseTask,
  OperationsOverview,
  PaginatedTasksResponse,
  FieldUpdateRecord,
  FieldUpdateType,
  TaskLocation,
  IncidentResolutionSummary,
} from '../types';

export const getOperationsOverview = async (
  options?: { situation_id?: string; assigned_to_me?: boolean } | string
): Promise<OperationsOverview> => {
  const params: Record<string, any> = {};
  if (typeof options === 'string') {
    params.situation_id = options;
  } else if (options) {
    if (options.situation_id) params.situation_id = options.situation_id;
    if (options.assigned_to_me) params.assigned_to_me = options.assigned_to_me;
  }
  const res = await api.get<OperationsOverview>(
    '/field-operations/overview',
    { params }
  );
  return res.data;
};

export const listTasks = async (params?: {
  situation_id?: string;
  plan_id?: string;
  status?: string;
  task_type?: string;
  priority?: string;
  assigned_to_me?: boolean;
  search?: string;
  page?: number;
  limit?: number;
}): Promise<PaginatedTasksResponse> => {
  const res = await api.get<PaginatedTasksResponse>(
    '/field-operations/tasks',
    { params }
  );
  return res.data;
};

export const getTask = async (taskId: string): Promise<ResponseTask> => {
  const res = await api.get<ResponseTask>(
    `/field-operations/tasks/${taskId}`
  );
  return res.data;
};

export const approveTask = async (taskId: string): Promise<ResponseTask> => {
  const res = await api.post<ResponseTask>(
    `/field-operations/tasks/${taskId}/approve`,
    {}
  );
  return res.data;
};

export const assignTask = async (
  taskId: string,
  data: {
    assigned_team_id?: string | null;
    assigned_team_name?: string | null;
    assigned_volunteer_ids?: string[];
    assigned_volunteer_names?: string[];
    assigned_vehicle_id?: string | null;
    assigned_vehicle_name?: string | null;
    notes?: string;
  }
): Promise<ResponseTask> => {
  const res = await api.post<ResponseTask>(
    `/field-operations/tasks/${taskId}/assign`,
    data
  );
  return res.data;
};

export const acceptTask = async (taskId: string): Promise<ResponseTask> => {
  const res = await api.post<ResponseTask>(
    `/field-operations/tasks/${taskId}/accept`,
    {}
  );
  return res.data;
};

export const startTask = async (taskId: string): Promise<ResponseTask> => {
  const res = await api.post<ResponseTask>(
    `/field-operations/tasks/${taskId}/start`,
    {}
  );
  return res.data;
};

export const completeTask = async (
  taskId: string,
  data?: {
    notes?: string;
    completion_notes?: string;
    consumed_resources?: any[];
  }
): Promise<ResponseTask> => {
  const res = await api.post<ResponseTask>(
    `/field-operations/tasks/${taskId}/complete`,
    data || {}
  );
  return res.data;
};

export const blockTask = async (
  taskId: string,
  data: { reason: string; notes?: string }
): Promise<ResponseTask> => {
  const res = await api.post<ResponseTask>(
    `/field-operations/tasks/${taskId}/block`,
    data
  );
  return res.data;
};

export const failTask = async (
  taskId: string,
  data: { reason: string; notes?: string }
): Promise<ResponseTask> => {
  const res = await api.post<ResponseTask>(
    `/field-operations/tasks/${taskId}/fail`,
    data
  );
  return res.data;
};

export const submitFieldUpdate = async (
  taskId: string,
  data: {
    event_type: FieldUpdateType;
    message: string;
    location?: TaskLocation | null;
    details?: Record<string, any>;
  }
): Promise<FieldUpdateRecord> => {
  const res = await api.post<FieldUpdateRecord>(
    `/field-operations/tasks/${taskId}/field-update`,
    data
  );
  return res.data;
};

export const getTaskTimeline = async (taskId: string): Promise<any[]> => {
  const res = await api.get<any[]>(
    `/field-operations/tasks/${taskId}/timeline`
  );
  return res.data;
};

export const resolveIncident = async (
  situationId: string,
  data: {
    resolution_notes: string;
    force_override_uncompleted?: boolean;
    override_reason?: string;
  }
): Promise<any> => {
  const res = await api.post(
    `/field-operations/incidents/${situationId}/resolve`,
    data
  );
  return res.data;
};

export const closeIncident = async (
  situationId: string,
  data: {
    close_notes: string;
    final_summary_notes?: string;
    force_override_uncompleted?: boolean;
    override_reason?: string;
  }
): Promise<IncidentResolutionSummary> => {
  const res = await api.post<IncidentResolutionSummary>(
    `/field-operations/incidents/${situationId}/close`,
    data
  );
  return res.data;
};

export const getIncidentSummary = async (
  situationId: string
): Promise<IncidentResolutionSummary> => {
  const res = await api.get<IncidentResolutionSummary>(
    `/field-operations/incidents/${situationId}/summary`
  );
  return res.data;
};

// ============================================================================
// PHASE C: FIELD OFFICER LIVE VERIFICATION & INCIDENT EVOLUTION TIMELINE
// ============================================================================

export const submitFieldVerification = async (
  data: import('../types').FieldVerificationCreateRequest
): Promise<import('../types').FieldVerificationRecord> => {
  const res = await api.post<import('../types').FieldVerificationRecord>(
    '/field/verify',
    data
  );
  return res.data;
};

export const listFieldVerifications = async (params?: {
  target_id?: string;
  target_type?: string;
  responder_id?: string;
  page?: number;
  limit?: number;
}): Promise<import('../types').PaginatedFieldVerificationsResponse> => {
  const res = await api.get<import('../types').PaginatedFieldVerificationsResponse>(
    '/field/verifications',
    { params }
  );
  return res.data;
};

export const getSituationEvolutionTimeline = async (
  situationId: string,
  params?: { order?: 'asc' | 'desc'; category?: string }
): Promise<import('../types').IncidentEvolutionTimelineResponse> => {
  const res = await api.get<import('../types').IncidentEvolutionTimelineResponse>(
    `/officer/situations/${encodeURIComponent(situationId)}/evolution-timeline`,
    { params }
  );
  return res.data;
};

export const getReportEvolutionTimeline = async (
  reportId: string,
  params?: { order?: 'asc' | 'desc'; category?: string }
): Promise<import('../types').IncidentEvolutionTimelineResponse> => {
  const res = await api.get<import('../types').IncidentEvolutionTimelineResponse>(
    `/citizen/reports/${reportId}/evolution-timeline`,
    { params }
  );
  return res.data;
};

