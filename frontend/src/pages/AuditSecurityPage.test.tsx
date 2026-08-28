import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuditSecurityPage } from './AuditSecurityPage';
import { auditApi } from '../api/audit';
import * as ToastHook from '../hooks/useToast';

describe('AuditSecurityPage component', () => {
  it('renders audit events table and compliance telemetry metrics cards', async () => {
    vi.spyOn(ToastHook, 'useToast').mockReturnValue({
      toasts: [],
      addToast: vi.fn(),
      removeToast: vi.fn(),
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
    });

    vi.spyOn(auditApi, 'getStatistics').mockResolvedValue({
      total_events: 142,
      events_by_type: { auth_login_success: 100, authorization_denied: 12 },
      events_by_severity: { info: 130, warning: 12 },
      authorization_denials: 12,
      authentication_failures: 4,
      active_users_with_events: 8,
      unique_resources_accessed: 24,
    });

    vi.spyOn(auditApi, 'getEvents').mockResolvedValue({
      items: [
        {
          id: 'evt-001',
          created_at: '2026-08-28T14:30:00Z',
          request_id: 'req-sec-999',
          event_type: 'authorization_denied',
          severity: 'warning',
          user_id: 'usr-1',
          email: 'analyst@corp.com',
          roles: ['Analyst'],
          clearance_level: 2,
          action: 'access_audit_log',
          authorization_result: 'denied',
          metadata_json: {},
        },
      ],
      total: 1,
      limit: 15,
      offset: 0,
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <AuditSecurityPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('142')).toBeInTheDocument();
      expect(screen.getAllByText('12').length).toBeGreaterThan(0);
      expect(screen.getByText('analyst@corp.com')).toBeInTheDocument();
      expect(screen.getByText('req-sec-999')).toBeInTheDocument();
    });
  });
});
