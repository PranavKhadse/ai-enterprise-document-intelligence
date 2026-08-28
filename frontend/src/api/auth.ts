import { apiClient } from './client';
import { TokenResponse, UserLoginRequest, UserRegisterRequest, UserResponse } from '../types/auth';

export const authApi = {
  login: async (data: UserLoginRequest): Promise<TokenResponse> => {
    const response = await apiClient.post<TokenResponse>('/auth/login', data);
    return response.data;
  },

  register: async (data: UserRegisterRequest): Promise<UserResponse> => {
    const response = await apiClient.post<UserResponse>('/auth/register', data);
    return response.data;
  },

  getMe: async (): Promise<UserResponse> => {
    const response = await apiClient.get<UserResponse>('/auth/me');
    return response.data;
  },
};
