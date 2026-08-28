import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LoginPage } from './LoginPage';
import * as AuthHook from '../hooks/useAuth';
import * as ToastHook from '../hooks/useToast';

describe('LoginPage component', () => {
  it('renders email and password inputs and triggers login on submit', async () => {
    const mockLogin = vi.fn().mockResolvedValue({
      id: 'u-1',
      email: 'user@corp.com',
      roles: ['Employee'],
      clearance_level: 1,
    });

    vi.spyOn(AuthHook, 'useAuth').mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      isAdmin: false,
      clearanceLevel: 1,
      roles: [],
      departmentName: 'General',
      login: mockLogin,
      register: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    vi.spyOn(ToastHook, 'useToast').mockReturnValue({
      toasts: [],
      addToast: vi.fn(),
      removeToast: vi.fn(),
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
    });

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    const emailInput = screen.getByLabelText(/corporate email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const submitBtn = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'user@corp.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password123' } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith({
        email: 'user@corp.com',
        password: 'password123',
      });
    });
  });
});
