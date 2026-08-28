import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { DocumentsPage } from './DocumentsPage';
import { documentsApi } from '../api/documents';
import * as ToastHook from '../hooks/useToast';

describe('DocumentsPage component', () => {
  it('renders documents table and allows opening the upload modal', async () => {
    vi.spyOn(ToastHook, 'useToast').mockReturnValue({
      toasts: [],
      addToast: vi.fn(),
      removeToast: vi.fn(),
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
    });

    vi.spyOn(documentsApi, 'list').mockResolvedValue({
      items: [
        {
          id: 'doc-123',
          title: 'Corporate Security Standards',
          file_hash: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
          file_type: 'pdf',
          current_version: '1.0',
          created_at: '2026-08-28T12:00:00Z',
          chunks_count: 12,
        },
      ],
      total: 1,
      limit: 10,
      offset: 0,
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <DocumentsPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Corporate Security Standards')).toBeInTheDocument();
      expect(screen.getByText('v1.0')).toBeInTheDocument();
    });

    const ingestBtn = screen.getByRole('button', { name: /ingest document/i });
    fireEvent.click(ingestBtn);

    expect(screen.getByText(/Upload & Ingest PDF Document/i)).toBeInTheDocument();
  });
});
