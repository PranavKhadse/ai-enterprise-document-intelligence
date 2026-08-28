import { apiClient } from './client';
import {
  AuditEventListResponse,
  AuditEventResponse,
  AuditQueryFilter,
  AuditStatisticsResponse,
} from '../types/audit';

export const auditApi = {
  getEvents: async (filter?: AuditQueryFilter): Promise<AuditEventListResponse> => {
    const response = await apiClient.get<AuditEventListResponse>('/audit/events', {
      params: filter,
    });
    return response.data;
  },

  getEventById: async (eventId: string): Promise<AuditEventResponse> => {
    const response = await apiClient.get<AuditEventResponse>(`/audit/events/${eventId}`);
    return response.data;
  },

  getStatistics: async (params?: {
    start_time?: string;
    end_time?: string;
  }): Promise<AuditStatisticsResponse> => {
    const response = await apiClient.get<AuditStatisticsResponse>('/audit/statistics', {
      params,
    });
    return response.data;
  },
};
