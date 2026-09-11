import api from './api';
import type {
  CoordinationPlan,
  PlanReviewPayload,
  AgentRunRecord,
} from '../types';

export const orchestrateSituation = async (
  situationId: string,
  forceRefresh: boolean = false
): Promise<CoordinationPlan> => {
  const response = await api.post<CoordinationPlan>(
    `/officer/coordination/situations/${encodeURIComponent(situationId)}/orchestrate`,
    { force_refresh: forceRefresh }
  );
  return response.data;
};

export const getCoordinationPlan = async (planId: string): Promise<CoordinationPlan> => {
  const response = await api.get<CoordinationPlan>(
    `/officer/coordination/plans/${encodeURIComponent(planId)}`
  );
  return response.data;
};

export const listSituationCoordinationPlans = async (
  situationId: string
): Promise<CoordinationPlan[]> => {
  const response = await api.get<CoordinationPlan[]>(
    `/officer/coordination/situations/${encodeURIComponent(situationId)}/plans`
  );
  return response.data;
};

export const reviewCoordinationPlan = async (
  planId: string,
  payload: PlanReviewPayload
): Promise<CoordinationPlan> => {
  const response = await api.post<CoordinationPlan>(
    `/officer/coordination/plans/${encodeURIComponent(planId)}/review`,
    payload
  );
  return response.data;
};

export const listSituationAgentRuns = async (
  situationId: string
): Promise<AgentRunRecord[]> => {
  const response = await api.get<AgentRunRecord[]>(
    `/officer/coordination/situations/${encodeURIComponent(situationId)}/agent-runs`
  );
  return response.data;
};

export const getAgentRunDetail = async (runId: string): Promise<AgentRunRecord> => {
  const response = await api.get<AgentRunRecord>(
    `/officer/coordination/agent-runs/${encodeURIComponent(runId)}`
  );
  return response.data;
};
