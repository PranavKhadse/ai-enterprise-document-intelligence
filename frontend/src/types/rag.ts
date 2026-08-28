/**
 * Phase 8 Grounded RAG Synthesis, Citations, Claims and Diagnostics Types.
 */

import { RetrievalFilter } from './search';

export type GroundingStatus =
  | 'fully_grounded'
  | 'partially_grounded'
  | 'unsupported'
  | 'insufficient_evidence'
  | 'refused';

export type ClaimStatus =
  | 'supported'
  | 'partially_supported'
  | 'unsupported'
  | 'insufficient_evidence';

export interface Citation {
  citation_id: number;
  chunk_id: string;
  document_id: string;
  document_title?: string | null;
  page_number?: number | null;
  section_path?: string | null;
  quoted_or_supported_text: string;
  relevance_score: number;
  is_table: boolean;
}

export interface ClaimVerification {
  claim_text: string;
  citation_ids: number[];
  status: ClaimStatus;
  entailment_score: number;
  unsupported_entities: string[];
  explanation: string;
}

export interface RAGDiagnostics {
  query: string;
  provider: string;
  model: string;
  llm_latency_ms: number;
  prompt_builder_latency_ms: number;
  citation_verifier_latency_ms: number;
  grounding_verifier_latency_ms: number;
  conflict_detector_latency_ms: number;
  total_rag_latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  evidence_count: number;
  citation_count: number;
  total_claims_count: number;
  supported_claims_count: number;
  unsupported_claims_count: number;
  degraded_mode: boolean;
  warnings: string[];
}

export interface RAGAnswer {
  query: string;
  answer: string;
  grounding_status: GroundingStatus;
  citations: Citation[];
  claims: ClaimVerification[];
  insufficient_evidence: boolean;
  conflicts_detected: boolean;
  conflict_details?: string | null;
  warnings: string[];
  diagnostics: RAGDiagnostics;
}

export interface RAGQueryRequest {
  query: string;
  filter?: RetrievalFilter | null;
  top_k?: number | null;
  max_context_tokens?: number | null;
  temperature?: number;
  enable_verification?: boolean;
}
