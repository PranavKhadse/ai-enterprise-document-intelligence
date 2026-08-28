/**
 * Phase 5 & 6 Hybrid Retrieval, Rank Fusion and Diagnostics Types.
 */

export type QueryType = 'exact_identifier' | 'keyword_search' | 'semantic_question' | 'mixed';
export type FusionStrategy = 'rrf' | 'weighted_score' | 'dense_only' | 'sparse_only';

export interface RetrievalFilter {
  document_id?: string | null;
  version_id?: string | null;
  department_id?: string | null;
  is_table?: boolean | null;
  allowed_department_ids?: string[] | null;
  max_clearance_level?: number | null;
  allowed_roles?: string[] | null;
  allowed_document_ids?: string[] | null;
}

export interface ScoredChunk {
  chunk_id: string;
  document_id: string;
  version_id?: string | null;
  department_id?: string | null;
  content: string;
  page_number?: number | null;
  section_path?: string | null;
  final_score: number;
  dense_score?: number | null;
  sparse_score?: number | null;
  dense_rank?: number | null;
  sparse_rank?: number | null;
  rrf_score?: number | null;
  normalized_dense_score?: number | null;
  normalized_sparse_score?: number | null;
  retrieval_methods: string[];
  explanation: string;
  metadata: Record<string, unknown>;
}

export interface RetrievalDiagnostics {
  query: string;
  query_type: string;
  dense_latency_ms: number;
  sparse_latency_ms: number;
  fusion_latency_ms: number;
  total_latency_ms: number;
  dense_candidates_count: number;
  sparse_candidates_count: number;
  merged_candidates_count: number;
  fusion_strategy: string;
  degraded_mode: boolean;
  warnings: string[];
}

export interface HybridRetrievalResponse {
  results: ScoredChunk[];
  diagnostics: RetrievalDiagnostics;
}

export interface DocumentSearchRequest {
  query: string;
  filter?: RetrievalFilter | null;
  strategy?: FusionStrategy | null;
  top_k?: number;
}
