import { apiClient } from './client';
import { HealthResponse } from '../types/health';

export const healthApi = {
  getHealth: async (): Promise<HealthResponse> => {
    // Health is at root /health or /api/v1/health
    const response = await apiClient.get<HealthResponse>('/health');
    return response.data;
  },
};
