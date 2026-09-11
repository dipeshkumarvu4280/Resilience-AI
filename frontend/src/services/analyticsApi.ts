import api from './api';
import type {
  EmergencyAnalyticsOverview,
  ResponseMilestoneTimeline,
  BottleneckInsight,
  ResourceUtilizationAnalytics,
  ShelterAnalytics,
  HealthcareAnalytics,
  VolunteerPerformanceAnalytics,
  FleetAnalytics,
  ReplanningIntelligence,
  IncidentComparisonResponse,
  DecisionSupportResponse,
  PostIncidentIntelligence,
  AnalyticsTimeRange,
} from '../types/analytics';

export interface AnalyticsFilterParams {
  time_range?: AnalyticsTimeRange;
  start_date?: string;
  end_date?: string;
  disaster_type?: string;
  severity?: string;
  zone?: string;
}

export const analyticsApi = {
  getOverview: async (params?: AnalyticsFilterParams): Promise<EmergencyAnalyticsOverview> => {
    const res = await api.get<EmergencyAnalyticsOverview>('/officer/analytics/overview', { params });
    return res.data;
  },

  getMilestones: async (params?: AnalyticsFilterParams): Promise<ResponseMilestoneTimeline> => {
    const res = await api.get<ResponseMilestoneTimeline>('/officer/analytics/milestones', { params });
    return res.data;
  },

  getBottlenecks: async (params?: AnalyticsFilterParams): Promise<BottleneckInsight[]> => {
    const res = await api.get<BottleneckInsight[]>('/officer/analytics/bottlenecks', { params });
    return res.data;
  },

  getResources: async (params?: AnalyticsFilterParams): Promise<ResourceUtilizationAnalytics> => {
    const res = await api.get<ResourceUtilizationAnalytics>('/officer/analytics/resources', { params });
    return res.data;
  },

  getShelters: async (params?: AnalyticsFilterParams): Promise<ShelterAnalytics> => {
    const res = await api.get<ShelterAnalytics>('/officer/analytics/shelters', { params });
    return res.data;
  },

  getHealthcare: async (params?: AnalyticsFilterParams): Promise<HealthcareAnalytics> => {
    const res = await api.get<HealthcareAnalytics>('/officer/analytics/healthcare', { params });
    return res.data;
  },

  getVolunteers: async (params?: AnalyticsFilterParams): Promise<VolunteerPerformanceAnalytics> => {
    const res = await api.get<VolunteerPerformanceAnalytics>('/officer/analytics/volunteers', { params });
    return res.data;
  },

  getFleet: async (params?: AnalyticsFilterParams): Promise<FleetAnalytics> => {
    const res = await api.get<FleetAnalytics>('/officer/analytics/fleet', { params });
    return res.data;
  },

  getReplanning: async (params?: AnalyticsFilterParams): Promise<ReplanningIntelligence> => {
    const res = await api.get<ReplanningIntelligence>('/officer/analytics/replanning', { params });
    return res.data;
  },

  getComparison: async (
    dimension: 'emergency_type' | 'severity_level' | 'zone' = 'emergency_type',
    params?: AnalyticsFilterParams
  ): Promise<IncidentComparisonResponse> => {
    const res = await api.get<IncidentComparisonResponse>('/officer/analytics/comparison', {
      params: { dimension, ...params },
    });
    return res.data;
  },

  getDecisionSupport: async (params?: AnalyticsFilterParams): Promise<DecisionSupportResponse> => {
    const res = await api.get<DecisionSupportResponse>('/officer/analytics/decision-support', { params });
    return res.data;
  },

  getPostIncidentIntelligence: async (situationId: string): Promise<PostIncidentIntelligence> => {
    const res = await api.get<PostIncidentIntelligence>(`/officer/analytics/post-incident/${situationId}`);
    return res.data;
  },
};
