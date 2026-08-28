/**
 * Standard Normalized API Error Type
 */

export interface ApiError {
  message: string;
  statusCode: number;
  requestId?: string | null;
  detail?: string | null;
  raw?: unknown;
}
