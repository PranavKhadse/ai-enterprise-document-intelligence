/**
 * Phase 9 Document Comparison, Semantic Clause Alignment & Conflict Intelligence Types.
 */

export type DiffType = 'added' | 'removed' | 'modified' | 'unchanged' | 'conflict';
export type ConflictSeverity = 'high' | 'medium' | 'low';

export interface EntityDiffItem {
  entity_type: string;
  value_a?: string | null;
  value_b?: string | null;
  normalized_value_a?: string | null;
  normalized_value_b?: string | null;
  is_divergent: boolean;
}

export interface AlignedClause {
  clause_id: string;
  section_path_a?: string | null;
  section_path_b?: string | null;
  text_a?: string | null;
  text_b?: string | null;
  page_a?: number | null;
  page_b?: number | null;
  diff_type: DiffType;
  similarity_score: number;
  conflict_severity?: ConflictSeverity | null;
  change_summary?: string | null;
  entity_diffs: EntityDiffItem[];
  heading_similarity?: number | null;
  lexical_similarity?: number | null;
  alignment_method?: string | null;
  conflict_verified: boolean;
}

export interface ComparisonStatistics {
  total_clauses_a: number;
  total_clauses_b: number;
  added_clauses_count: number;
  removed_clauses_count: number;
  modified_clauses_count: number;
  conflicting_clauses_count: number;
  unchanged_clauses_count: number;
  divergence_index: number;
}

export interface ComparisonDiagnostics {
  extraction_latency_ms: number;
  alignment_latency_ms: number;
  entity_diff_latency_ms: number;
  llm_latency_ms: number;
  total_latency_ms: number;
  clauses_a: number;
  clauses_b: number;
  aligned_pairs: number;
  unmatched_a: number;
  unmatched_b: number;
  llm_used: boolean;
  llm_fallback_used: boolean;
  warnings: string[];
}

export interface DocumentComparisonRequest {
  document_a_id?: string | null;
  document_b_id?: string | null;
  text_a?: string | null;
  text_b?: string | null;
  title_a?: string | null;
  title_b?: string | null;
  similarity_threshold?: number;
  detect_conflicts_only?: boolean;
}

export interface DocumentComparisonResponse {
  document_a_id?: string | null;
  document_b_id?: string | null;
  title_a: string;
  title_b: string;
  statistics: ComparisonStatistics;
  aligned_clauses: AlignedClause[];
  conflicts: AlignedClause[];
  executive_summary: string;
  diagnostics: ComparisonDiagnostics;
}
