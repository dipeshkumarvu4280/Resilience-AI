import api from './api';
import type {
  IncidentPredictionResponse,
  PredictiveTrendResponse,
  PredictiveFeaturesResponse,
  PredictiveHealthResponse,
} from '../types';

export interface GetPredictionParams {
  window_minutes?: number;
  horizon_minutes?: number;
}

/**
 * Fetch authoritative advisory escalation risk prediction for an incident.
 */
export const getIncidentPrediction = async (
  incidentId: string,
  params: GetPredictionParams = {}
): Promise<IncidentPredictionResponse> => {
  const response = await api.get<IncidentPredictionResponse>(
    `/officer/predictive/incidents/${encodeURIComponent(incidentId)}`,
    { params }
  );
  return response.data;
};

/**
 * Fetch temporal trend points (current state vs 15m, 30m, 60m horizon forecast).
 */
export const getIncidentTrend = async (
  incidentId: string,
  window_minutes: number = 60
): Promise<PredictiveTrendResponse> => {
  const response = await api.get<PredictiveTrendResponse>(
    `/officer/predictive/incidents/${encodeURIComponent(incidentId)}/trend`,
    { params: { window_minutes } }
  );
  return response.data;
};

/**
 * Fetch explainable feature provenance for an incident.
 */
export const getIncidentFeatures = async (
  incidentId: string,
  window_minutes: number = 60
): Promise<PredictiveFeaturesResponse> => {
  const response = await api.get<PredictiveFeaturesResponse>(
    `/officer/predictive/incidents/${encodeURIComponent(incidentId)}/features`,
    { params: { window_minutes } }
  );
  return response.data;
};

/**
 * Health check for the predictive intelligence engine.
 */
export const getPredictiveHealth = async (): Promise<PredictiveHealthResponse> => {
  const response = await api.get<PredictiveHealthResponse>('/officer/predictive/health');
  return response.data;
};
