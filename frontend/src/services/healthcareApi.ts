import axios from 'axios';
import type {
  HealthcareFacility,
  PaginatedHealthcareFacilitiesResponse,
  HealthcareStatsResponse,
  HealthcareFacilityCreatePayload,
  HealthcareCapacityUpdatePayload,
  HealthcareFacilityType,
  HealthcareOperationalStatus,
} from '../types';

import { getApiBaseUrl } from './api';

const api = axios.create({
  baseURL: getApiBaseUrl(),
});

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

export interface HealthcareFilterParams {
  page?: number;
  limit?: number;
  search?: string;
  district?: string;
  zone?: string;
  facility_type?: HealthcareFacilityType;
  status?: HealthcareOperationalStatus;
  trauma_capable?: boolean;
  icu_capable?: boolean;
  oxygen_capable?: boolean;
  min_available_beds?: number;
}

export const getHealthcareFacilities = async (
  params: HealthcareFilterParams = {}
): Promise<PaginatedHealthcareFacilitiesResponse> => {
  const response = await api.get<PaginatedHealthcareFacilitiesResponse>('/healthcare/facilities', {
    params,
  });
  return response.data;
};

export const getHealthcareFacilityStats = async (
  district?: string,
  zone?: string
): Promise<HealthcareStatsResponse> => {
  const response = await api.get<HealthcareStatsResponse>('/healthcare/facilities/stats', {
    params: { district, zone },
  });
  return response.data;
};

export const getHealthcareFacilityById = async (
  facilityId: string
): Promise<HealthcareFacility> => {
  const response = await api.get<HealthcareFacility>(`/healthcare/facilities/${facilityId}`);
  return response.data;
};

export const createHealthcareFacility = async (
  payload: HealthcareFacilityCreatePayload
): Promise<HealthcareFacility> => {
  const response = await api.post<HealthcareFacility>('/healthcare/facilities', payload);
  return response.data;
};

export const updateHealthcareCapacity = async (
  facilityId: string,
  payload: HealthcareCapacityUpdatePayload
): Promise<HealthcareFacility> => {
  const response = await api.patch<HealthcareFacility>(
    `/healthcare/facilities/${facilityId}/capacity`,
    payload
  );
  return response.data;
};

export const updateHealthcareStatus = async (
  facilityId: string,
  status: HealthcareOperationalStatus,
  reason?: string
): Promise<HealthcareFacility> => {
  const response = await api.patch<HealthcareFacility>(
    `/healthcare/facilities/${facilityId}/status`,
    null,
    {
      params: { new_status: status, reason },
    }
  );
  return response.data;
};

export const updateHealthcareFacility = async (
  facilityId: string,
  payload: Partial<HealthcareFacilityCreatePayload>
): Promise<HealthcareFacility> => {
  const response = await api.patch<HealthcareFacility>(
    `/healthcare/facilities/${facilityId}`,
    payload
  );
  return response.data;
};

export const deleteHealthcareFacility = async (
  facilityId: string
): Promise<{ status: string; message: string }> => {
  const response = await api.delete<{ status: string; message: string }>(
    `/healthcare/facilities/${facilityId}`
  );
  return response.data;
};
