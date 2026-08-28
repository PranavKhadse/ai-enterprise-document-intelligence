import { apiClient } from './client';
import {
  DocumentChunksListResponse,
  DocumentItemResponse,
  DocumentListResponse,
  DocumentUploadResponse,
} from '../types/document';

export const documentsApi = {
  upload: async (
    file: File,
    title?: string,
    departmentId?: string,
    onProgress?: (percent: number) => void
  ): Promise<DocumentUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    if (title) formData.append('title', title);
    if (departmentId) formData.append('department_id', departmentId);

    const response = await apiClient.post<DocumentUploadResponse>('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onProgress) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(percent);
        }
      },
    });

    return response.data;
  },

  list: async (params?: {
    query?: string;
    department_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<DocumentListResponse> => {
    const response = await apiClient.get<DocumentListResponse>('/documents', {
      params,
    });
    return response.data;
  },

  getById: async (documentId: string): Promise<DocumentItemResponse> => {
    const response = await apiClient.get<DocumentItemResponse>(`/documents/${documentId}`);
    return response.data;
  },

  getChunks: async (
    documentId: string,
    params?: { limit?: number; offset?: number }
  ): Promise<DocumentChunksListResponse> => {
    const response = await apiClient.get<DocumentChunksListResponse>(
      `/documents/${documentId}/chunks`,
      { params }
    );
    return response.data;
  },

  delete: async (documentId: string): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.delete<{ success: boolean; message: string }>(
      `/documents/${documentId}`
    );
    return response.data;
  },
};
