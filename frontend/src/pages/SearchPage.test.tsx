import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SearchPage } from './SearchPage';
import { searchApi } from '../api/search';

describe('SearchPage component', () => {
  it('renders search input and displays hybrid results when search is performed', async () => {
    const mockSearch = vi.spyOn(searchApi, 'search').mockResolvedValue({
      results: [
        {
          chunk_id: 'chunk-101',
          document_id: 'doc-1',
          content: 'Severance payment equals two months base salary for standard terminations.',
          page_number: 3,
          section_path: 'HR Policy > Severance',
          final_score: 0.892,
          dense_rank: 1,
          sparse_rank: 2,
          retrieval_methods: ['dense', 'bm25'],
          explanation: 'Retrieved via dense semantic match and BM25 keyword match.',
          metadata: {},
        },
      ],
      diagnostics: {
        query: 'severance pay',
        query_type: 'semantic_question',
        dense_latency_ms: 12.5,
        sparse_latency_ms: 4.2,
        fusion_latency_ms: 1.1,
        total_latency_ms: 17.8,
        dense_candidates_count: 20,
        sparse_candidates_count: 15,
        merged_candidates_count: 35,
        fusion_strategy: 'rrf',
        degraded_mode: false,
        warnings: [],
      },
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <SearchPage />
      </QueryClientProvider>
    );

    const input = screen.getByPlaceholderText(/enter semantic questions/i);
    const searchBtn = screen.getByRole('button', { name: /search/i });

    fireEvent.change(input, { target: { value: 'severance pay' } });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(mockSearch).toHaveBeenCalledWith({
        query: 'severance pay',
        strategy: 'rrf',
        top_k: 10,
      });
      expect(screen.getByText(/Severance payment equals two months base salary/i)).toBeInTheDocument();
      expect(screen.getByText(/HR Policy > Severance/i)).toBeInTheDocument();
      expect(screen.getByText(/0.8920/)).toBeInTheDocument();
    });
  });
});
