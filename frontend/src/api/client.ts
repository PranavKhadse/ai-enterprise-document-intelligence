import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { ApiError } from '../types/api';
import { storage } from '../utils/storage';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request Interceptor: inject Bearer token and correlation X-Request-ID
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = storage.getToken();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    if (config.headers && !config.headers['X-Request-ID']) {
      config.headers['X-Request-ID'] = `edi-client-${Math.random().toString(36).substring(2, 11)}`;
    }

    return config;
  },
  (error) => Promise.reject(normalizeError(error))
);

// Response Interceptor: extract request ID, handle 401/403, normalize errors
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error: AxiosError) => {
    const normalized = normalizeError(error);

    if (normalized.statusCode === 401) {
      // Notify application of session expiration
      window.dispatchEvent(new CustomEvent('edi:auth:expired', { detail: normalized }));
    }

    return Promise.reject(normalized);
  }
);

export function normalizeError(error: unknown): ApiError {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status || (error.code === 'ECONNABORTED' ? 504 : 500);
    const requestId =
      (error.response?.headers?.['x-request-id'] as string) ||
      (error.config?.headers?.['X-Request-ID'] as string) ||
      null;

    let message = error.message || 'An unexpected network error occurred.';
    let detail: string | null = null;

    if (error.response?.data) {
      const data = error.response.data as Record<string, unknown>;
      if (typeof data.detail === 'string') {
        detail = data.detail;
        message = data.detail;
      } else if (typeof data.message === 'string') {
        message = data.message;
      } else if (Array.isArray(data.detail)) {
        // Pydantic validation error array
        detail = JSON.stringify(data.detail);
        message = 'Request validation error.';
      }
    }

    if (!error.response && error.request) {
      message = 'Backend API is unreachable. Please verify the server is running.';
    }

    return {
      message,
      statusCode: status,
      requestId,
      detail,
      raw: error,
    };
  }

  if (error instanceof Error) {
    return {
      message: error.message,
      statusCode: 500,
      requestId: null,
      detail: null,
      raw: error,
    };
  }

  return {
    message: 'An unknown system error occurred.',
    statusCode: 500,
    requestId: null,
    detail: null,
    raw: error,
  };
}
