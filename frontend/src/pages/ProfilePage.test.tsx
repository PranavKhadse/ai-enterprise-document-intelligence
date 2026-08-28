import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProfilePage } from './ProfilePage';
import * as AuthHook from '../hooks/useAuth';

describe('ProfilePage component', () => {
  it('renders authenticated user clearance level, roles, and department', () => {
    vi.spyOn(AuthHook, 'useAuth').mockReturnValue({
      user: {
        id: 'u-corp-42',
        email: 'security.lead@enterprise.com',
        is_active: true,
        department_id: 'dept-sec',
        department: { id: 'dept-sec', name: 'Information Security' },
        roles: ['Admin', 'Auditor'],
        clearance_level: 4,
      },
      isAuthenticated: true,
      isLoading: false,
      isAdmin: true,
      clearanceLevel: 4,
      roles: ['Admin', 'Auditor'],
      departmentName: 'Information Security',
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <MemoryRouter>
        <ProfilePage />
      </MemoryRouter>
    );

    expect(screen.getByText('security.lead@enterprise.com')).toBeInTheDocument();
    expect(screen.getByText('u-corp-42')).toBeInTheDocument();
    expect(screen.getByText(/Information Security/i)).toBeInTheDocument();
    expect(screen.getByText('Level 4 of 4')).toBeInTheDocument();
    expect(screen.getByText('ACCOUNT ACTIVE')).toBeInTheDocument();
  });
});
