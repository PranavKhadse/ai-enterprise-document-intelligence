import { apiClient } from './client';
import { DocumentComparisonRequest, DocumentComparisonResponse } from '../types/comparison';

export const comparisonApi = {
  compare: async (request: DocumentComparisonRequest): Promise<DocumentComparisonResponse> => {
    const response = await apiClient.post<DocumentComparisonResponse>(
      '/documents/compare',
      request
    );
    return response.data;
  },
};
