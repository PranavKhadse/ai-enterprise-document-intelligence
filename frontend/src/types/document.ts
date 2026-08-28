/**
 * Document Ingestion, Management & Explorer Types.
 */

export interface DocumentUploadResponse {
  id: string;
  title: string;
  file_hash: string;
  file_type: string;
  status: 'uploaded' | 'already_exists';
  is_duplicate: boolean;
  department_id?: string | null;
  current_version: string;
  created_at: string;
}

export interface DocumentItemResponse {
  id: string;
  title: string;
  file_hash: string;
  file_type: string;
  total_pages?: number | null;
  department_id?: string | null;
  current_version: string;
  created_at: string;
  chunks_count: number;
}

export interface DocumentListResponse {
  items: DocumentItemResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface DocumentChunkResponse {
  id: string;
  document_id: string;
  version_id?: string | null;
  chunk_index: number;
  content: string;
  page_number?: number | null;
  section_path?: string | null;
  token_count?: number | null;
  metadata_json: Record<string, unknown>;
}

export interface DocumentChunksListResponse {
  items: DocumentChunkResponse[];
  total: number;
  limit: number;
  offset: number;
}
