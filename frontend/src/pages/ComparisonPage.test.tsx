import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ComparisonPage } from './ComparisonPage';
import { comparisonApi } from '../api/comparison';
import { documentsApi } from '../api/documents';
import * as ToastHook from '../hooks/useToast';

describe('ComparisonPage component', () => {
  it('executes document comparison and displays executive summary, diff statistics, and aligned clauses', async () => {
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
          id: 'doc-a',
          title: 'NDA Agreement 2025',
          file_hash: 'hash-a',
          file_type: 'pdf',
          current_version: '1.0',
          created_at: '2026-08-28T10:00:00Z',
          chunks_count: 5,
        },
        {
          id: 'doc-b',
          title: 'NDA Agreement 2026',
          file_hash: 'hash-b',
          file_type: 'pdf',
          current_version: '2.0',
          created_at: '2026-08-28T11:00:00Z',
          chunks_count: 6,
        },
      ],
      total: 2,
      limit: 100,
      offset: 0,
    });

    const mockCompare = vi.spyOn(comparisonApi, 'compare').mockResolvedValue({
      title_a: 'NDA Agreement 2025',
      title_b: 'NDA Agreement 2026',
      statistics: {
        total_clauses_a: 5,
        total_clauses_b: 6,
        added_clauses_count: 1,
        removed_clauses_count: 0,
        modified_clauses_count: 1,
        conflicting_clauses_count: 1,
        unchanged_clauses_count: 3,
        divergence_index: 0.35,
      },
      aligned_clauses: [
        {
          clause_id: 'cl-1',
          section_path_a: 'Clause 3 > Confidentiality Term',
          section_path_b: 'Clause 3 > Confidentiality Term',
          text_a: 'Confidentiality obligations survive for 2 years.',
          text_b: 'Confidentiality obligations survive for 5 years.',
          diff_type: 'conflict',
          similarity_score: 0.88,
          conflict_severity: 'high',
          change_summary: 'Confidentiality survival period was extended from 2 years to 5 years.',
          entity_diffs: [
            {
              entity_type: 'duration',
              value_a: '2 years',
              value_b: '5 years',
              is_divergent: true,
            },
          ],
          conflict_verified: true,
        },
      ],
      conflicts: [],
      executive_summary: 'The 2026 update increases the confidentiality duration obligation from 2 years to 5 years.',
      diagnostics: {
        extraction_latency_ms: 10.0,
        alignment_latency_ms: 15.0,
        entity_diff_latency_ms: 8.0,
        llm_latency_ms: 40.0,
        total_latency_ms: 73.0,
        clauses_a: 5,
        clauses_b: 6,
        aligned_pairs: 5,
        unmatched_a: 0,
        unmatched_b: 1,
        llm_used: true,
        llm_fallback_used: false,
        warnings: [],
      },
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ComparisonPage />
      </QueryClientProvider>
    );

    // Switch to ad-hoc text mode for quick testing
    fireEvent.click(screen.getByRole('button', { name: /ad-hoc text input/i }));

    const textareas = screen.getAllByRole('textbox');
    fireEvent.change(textareas[1], { target: { value: 'Confidentiality obligations survive for 2 years.' } });
    fireEvent.change(textareas[3], { target: { value: 'Confidentiality obligations survive for 5 years.' } });

    fireEvent.click(screen.getByRole('button', { name: /execute comparison/i }));

    await waitFor(() => {
      expect(mockCompare).toHaveBeenCalled();
      expect(screen.getByText('EXECUTIVE SUMMARY')).toBeInTheDocument();
      expect(screen.getByText(/increases the confidentiality duration/i)).toBeInTheDocument();
      expect(screen.getByText(/35.0%/)).toBeInTheDocument();
      expect(screen.getByText('CONFLICT')).toBeInTheDocument();
      expect(screen.getByText('HIGH SEVERITY')).toBeInTheDocument();
    });
  });
});
