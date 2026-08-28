import { describe, it, expect } from 'vitest';
import { escapeHtml, sanitizeMetadata } from './sanitizer';

describe('sanitizer utility', () => {
  it('escapes dangerous HTML characters', () => {
    const raw = '<script>alert("xss")</script>&"\'';
    const escaped = escapeHtml(raw);
    expect(escaped).not.toContain('<script>');
    expect(escaped).toContain('&lt;script&gt;');
    expect(escaped).toContain('&amp;');
    expect(escaped).toContain('&quot;');
  });

  it('redacts sensitive security keys recursively in metadata', () => {
    const metadata = {
      filename: 'policy.pdf',
      api_key: 'secret-key-12345',
      user_password_hash: 'hash-xyz',
      nested: {
        jwt_token: 'bearer.token.jwt',
        safe_field: 'valid_value',
      },
    };

    const sanitized = sanitizeMetadata(metadata);
    expect(sanitized.filename).toBe('policy.pdf');
    expect(sanitized.api_key).toBe('[REDACTED]');
    expect(sanitized.user_password_hash).toBe('[REDACTED]');
    expect((sanitized.nested as Record<string, unknown>).jwt_token).toBe('[REDACTED]');
    expect((sanitized.nested as Record<string, unknown>).safe_field).toBe('valid_value');
  });
});
