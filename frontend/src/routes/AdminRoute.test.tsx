import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AdminRoute } from './AdminRoute';
import * as AuthHook from '../hooks/useAuth';

describe('AdminRoute', () => {
  it('renders ForbiddenPage (403) when user is not admin', () => {
    vi.spyOn(AuthHook, 'useAuth').mockReturnValue({
      user: {
        id: 'u-2',
        email: 'employee@corp.com',
        is_active: true,
        roles: ['Employee'],
        clearance_level: 1,
      },
      isAuthenticated: true,
      isLoading: false,
      isAdmin: false,
      clearanceLevel: 1,
      roles: ['Employee'],
      departmentName: 'General',
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/audit']}>
        <Routes>
          <Route
            path="/audit"
            element={
              <AdminRoute>
                <div>Admin Audit Vault</div>
              </AdminRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.queryByText('Admin Audit Vault')).not.toBeInTheDocument();
    expect(screen.getByText('403 HTTP FORBIDDEN')).toBeInTheDocument();
  });

  it('renders protected child component when user is admin', () => {
    vi.spyOn(AuthHook, 'useAuth').mockReturnValue({
      user: {
        id: 'u-admin',
        email: 'admin@corp.com',
        is_active: true,
        roles: ['Admin'],
        clearance_level: 4,
      },
      isAuthenticated: true,
      isLoading: false,
      isAdmin: true,
      clearanceLevel: 4,
      roles: ['Admin'],
      departmentName: 'Security',
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/audit']}>
        <Routes>
          <Route
            path="/audit"
            element={
              <AdminRoute>
                <div>Admin Audit Vault</div>
              </AdminRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('Admin Audit Vault')).toBeInTheDocument();
  });
});
