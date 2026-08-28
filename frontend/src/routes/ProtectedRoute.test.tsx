import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { ProtectedRoute } from './ProtectedRoute';
import * as AuthHook from '../hooks/useAuth';

describe('ProtectedRoute', () => {
  it('redirects unauthenticated users to /login', () => {
    vi.spyOn(AuthHook, 'useAuth').mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      isAdmin: false,
      clearanceLevel: 1,
      roles: [],
      departmentName: 'General',
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div>Secret Dashboard Content</div>
              </ProtectedRoute>
            }
          />
          <Route path="/login" element={<div>Login Page Target</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.queryByText('Secret Dashboard Content')).not.toBeInTheDocument();
    expect(screen.getByText('Login Page Target')).toBeInTheDocument();
  });

  it('renders children when authenticated', () => {
    vi.spyOn(AuthHook, 'useAuth').mockReturnValue({
      user: {
        id: 'u-1',
        email: 'analyst@corp.com',
        is_active: true,
        roles: ['Analyst'],
        clearance_level: 2,
      },
      isAuthenticated: true,
      isLoading: false,
      isAdmin: false,
      clearanceLevel: 2,
      roles: ['Analyst'],
      departmentName: 'Risk',
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div>Secret Dashboard Content</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('Secret Dashboard Content')).toBeInTheDocument();
  });
});
