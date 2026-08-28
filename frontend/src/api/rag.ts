import { apiClient } from './client';
import { RAGAnswer, RAGQueryRequest } from '../types/rag';

export const ragApi = {
  query: async (request: RAGQueryRequest): Promise<RAGAnswer> => {
    const response = await apiClient.post<RAGAnswer>('/rag/query', request);
    return response.data;
  },
};
