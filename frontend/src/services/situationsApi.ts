import api from './api';
import type {
  SituationCluster,
  SituationDetailResponse,
  PaginatedSituationsResponse,
  SituationStatsResponse,
  OfficerSituationReviewRequest,
  SituationStatus,
  EmergencyType,
  SeverityLevel,
} from '../types';

export interface ListSituationsParams {
  status?: SituationStatus;
  emergency_type?: EmergencyType;
  severity_level?: SeverityLevel;
  search?: string;
  page?: number;
  limit?: number;
}

export const getSituationStats = async (): Promise<SituationStatsResponse> => {
  const response = await api.get<SituationStatsResponse>('/officer/situations/stats');
  return response.data;
};

export const listSituations = async (params: ListSituationsParams = {}): Promise<PaginatedSituationsResponse> => {
  const response = await api.get<PaginatedSituationsResponse>('/officer/situations', { params });
  return response.data;
};

export const getSituationDetail = async (situationId: string): Promise<SituationDetailResponse> => {
  const response = await api.get<SituationDetailResponse>(`/officer/situations/${encodeURIComponent(situationId)}`);
  return response.data;
};

export const assessSituation = async (situationId: string): Promise<SituationCluster> => {
  const response = await api.post<SituationCluster>(`/officer/situations/${encodeURIComponent(situationId)}/assess`);
  return response.data;
};

export const reviewSituation = async (
  situationId: string,
  payload: OfficerSituationReviewRequest
): Promise<SituationCluster> => {
  const response = await api.post<SituationCluster>(`/officer/situations/${encodeURIComponent(situationId)}/review`, payload);
  return response.data;
};

export const getSituationTimeline = async (situationId: string): Promise<any[]> => {
  const response = await api.get<any[]>(`/officer/situations/${encodeURIComponent(situationId)}/timeline`);
  return response.data;
};

export const fuseAllReports = async (): Promise<{ message: string; total_situations: number }> => {
  const response = await api.post<{ message: string; total_situations: number }>('/officer/situations/fuse-all');
  return response.data;
};

export const getSituationEvolutionTimeline = async (
  situationId: string,
  params?: { order?: 'asc' | 'desc'; category?: string }
): Promise<import('../types').IncidentEvolutionTimelineResponse> => {
  const response = await api.get<import('../types').IncidentEvolutionTimelineResponse>(
    `/officer/situations/${encodeURIComponent(situationId)}/evolution-timeline`,
    { params }
  );
  return response.data;
};
