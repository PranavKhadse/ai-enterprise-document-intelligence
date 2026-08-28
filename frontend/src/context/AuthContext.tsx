import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { UserResponse, UserLoginRequest, UserRegisterRequest } from '../types/auth';
import { authApi } from '../api/auth';
import { storage } from '../utils/storage';

interface AuthContextType {
  user: UserResponse | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isAdmin: boolean;
  clearanceLevel: number;
  roles: string[];
  departmentName: string;
  login: (credentials: UserLoginRequest) => Promise<UserResponse>;
  register: (data: UserRegisterRequest) => Promise<UserResponse>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const logout = useCallback(() => {
    storage.clearToken();
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    const token = storage.getToken();
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }

    try {
      const userData = await authApi.getMe();
      setUser(userData);
    } catch {
      // Clear token on 401 or resolution failure
      storage.clearToken();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();

    // Listen for session expiration events emitted by HTTP client
    const handleAuthExpired = () => {
      logout();
    };

    window.addEventListener('edi:auth:expired', handleAuthExpired);
    return () => {
      window.removeEventListener('edi:auth:expired', handleAuthExpired);
    };
  }, [refreshUser, logout]);

  const login = async (credentials: UserLoginRequest): Promise<UserResponse> => {
    setIsLoading(true);
    try {
      const response = await authApi.login(credentials);
      storage.setToken(response.access_token);
      setUser(response.user);
      return response.user;
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (data: UserRegisterRequest): Promise<UserResponse> => {
    return await authApi.register(data);
  };

  const isAdmin = user ? user.roles.includes('Admin') || user.clearance_level === 4 : false;
  const clearanceLevel = user ? user.clearance_level : 1;
  const roles = user ? user.roles : [];
  const departmentName = user?.department?.name || 'General';

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        isAdmin,
        clearanceLevel,
        roles,
        departmentName,
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
