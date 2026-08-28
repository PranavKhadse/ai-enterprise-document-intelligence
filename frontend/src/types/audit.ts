/**
 * Phase 11 Administrative Audit Logging & Security Observability Types.
 */

export type AuditEventType =
  | 'auth_login_success'
  | 'auth_login_failure'
  | 'auth_register'
  | 'auth_logout'
  | 'auth_token_revoked'
  | 'auth_account_disabled'
  | 'authorization_denied'
  | 'authorization_granted'
  | 'document_created'
  | 'document_read'
  | 'document_updated'
  | 'document_deleted'
  | 'document_compared'
  | 'rag_query'
  | 'rag_access_denied'
  | 'rbac_filter_applied'
  | 'admin_action'
  | 'security_event'
  | 'system_event';

export type AuditSeverity = 'info' | 'warning' | 'high' | 'critical';
export type AuthorizationResult = 'allowed' | 'denied' | 'unknown';

export interface AuditEventResponse {
  id: string;
  created_at: string;
  request_id?: string | null;
  event_type: string;
  severity: string;
  user_id?: string | null;
  email?: string | null;
  department_id?: string | null;
  roles: string[];
  clearance_level?: number | null;
  action: string;
  resource_type?: string | null;
  resource_id?: string | null;
  authorization_result: string;
  http_method?: string | null;
  api_path?: string | null;
  status_code?: number | null;
  source_ip?: string | null;
  user_agent?: string | null;
  query_fingerprint?: string | null;
  event_hash?: string | null;
  previous_event_hash?: string | null;
  metadata_json: Record<string, unknown>;
}

export interface AuditEventListResponse {
  items: AuditEventResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditQueryFilter {
  event_type?: AuditEventType | null;
  severity?: AuditSeverity | null;
  user_id?: string | null;
  request_id?: string | null;
  resource_type?: string | null;
  resource_id?: string | null;
  authorization_result?: AuthorizationResult | null;
  start_time?: string | null;
  end_time?: string | null;
  limit?: number;
  offset?: number;
}

export interface AuditStatisticsResponse {
  total_events: number;
  events_by_type: Record<string, number>;
  events_by_severity: Record<string, number>;
  authorization_denials: number;
  authentication_failures: number;
  active_users_with_events: number;
  unique_resources_accessed: number;
  time_window_start?: string | null;
  time_window_end?: string | null;
}
