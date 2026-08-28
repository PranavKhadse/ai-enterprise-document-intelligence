import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RAGAssistantPage } from './RAGAssistantPage';
import { ragApi } from '../api/rag';
import * as ToastHook from '../hooks/useToast';

describe('RAGAssistantPage component', () => {
  it('submits question and renders fully grounded answer with citation anchors and claims table', async () => {
    vi.spyOn(ToastHook, 'useToast').mockReturnValue({
      toasts: [],
      addToast: vi.fn(),
      removeToast: vi.fn(),
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
    });

    const mockQuery = vi.spyOn(ragApi, 'query').mockResolvedValue({
      query: 'What is the notice period?',
      answer: 'Standard notice period is 30 calendar days [1].',
      grounding_status: 'fully_grounded',
      citations: [
        {
          citation_id: 1,
          chunk_id: 'chk-1',
          document_id: 'doc-1',
          document_title: 'Employment Handbook 2026',
          page_number: 14,
          section_path: 'Section 4.2 > Notice Periods',
          quoted_or_supported_text: 'Employees must provide a written notice of at least 30 calendar days.',
          relevance_score: 0.94,
          is_table: false,
        },
      ],
      claims: [
        {
          claim_text: 'Standard notice period is 30 calendar days',
          citation_ids: [1],
          status: 'supported',
          entailment_score: 0.96,
          unsupported_entities: [],
          explanation: 'Fully entailed by Section 4.2 of Employment Handbook.',
        },
      ],
      insufficient_evidence: false,
      conflicts_detected: false,
      conflict_details: null,
      warnings: [],
      diagnostics: {
        query: 'What is the notice period?',
        provider: 'ollama',
        model: 'llama3:8b',
        llm_latency_ms: 120.0,
        prompt_builder_latency_ms: 5.0,
        citation_verifier_latency_ms: 8.0,
        grounding_verifier_latency_ms: 10.0,
        conflict_detector_latency_ms: 6.0,
        total_rag_latency_ms: 149.0,
        prompt_tokens: 350,
        completion_tokens: 45,
        evidence_count: 5,
        citation_count: 1,
        total_claims_count: 1,
        supported_claims_count: 1,
        unsupported_claims_count: 0,
        degraded_mode: false,
        warnings: [],
      },
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <RAGAssistantPage />
      </QueryClientProvider>
    );

    const input = screen.getByPlaceholderText(/ask a factual question/i);
    const askBtn = screen.getByRole('button', { name: /ask assistant/i });

    fireEvent.change(input, { target: { value: 'What is the notice period?' } });
    fireEvent.click(askBtn);

    await waitFor(() => {
      expect(mockQuery).toHaveBeenCalledWith({
        query: 'What is the notice period?',
        temperature: 0,
        enable_verification: true,
        top_k: 10,
      });
      expect(screen.getByText('FULLY GROUNDED')).toBeInTheDocument();
      expect(screen.getByText(/Standard notice period is 30 calendar days/i)).toBeInTheDocument();
      expect(screen.getByText(/Employment Handbook 2026/i)).toBeInTheDocument();
      expect(screen.getByText(/SUPPORTED \(96.0%\)/i)).toBeInTheDocument();
    });
  });
});
