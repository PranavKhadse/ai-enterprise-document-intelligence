import { apiClient } from './client';
import { DocumentSearchRequest, HybridRetrievalResponse } from '../types/search';

export const searchApi = {
  search: async (request: DocumentSearchRequest): Promise<HybridRetrievalResponse> => {
    const response = await apiClient.post<HybridRetrievalResponse>('/documents/search', request);
    return response.data;
  },
};
