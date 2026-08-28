/**
 * Sanitizer and safe text rendering utilities.
 * Ensures untrusted document evidence and LLM outputs are strictly rendered safely.
 */

export function escapeHtml(str: string): string {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export function sanitizeMetadata(metadata: Record<string, unknown>): Record<string, unknown> {
  const sensitiveKeys = ['password', 'secret', 'key', 'token', 'authorization', 'api_key', 'jwt'];
  const sanitized: Record<string, unknown> = {};

  for (const [k, v] of Object.entries(metadata)) {
    if (sensitiveKeys.some((sk) => k.toLowerCase().includes(sk))) {
      sanitized[k] = '[REDACTED]';
    } else if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
      sanitized[k] = sanitizeMetadata(v as Record<string, unknown>);
    } else {
      sanitized[k] = v;
    }
  }

  return sanitized;
}
