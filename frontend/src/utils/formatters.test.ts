import { describe, it, expect } from 'vitest';
import { formatDate, formatBytes, formatLatency, truncateHash, formatPercentage } from './formatters';

describe('formatters utility', () => {
  it('formats bytes accurately', () => {
    expect(formatBytes(0)).toBe('0 Bytes');
    expect(formatBytes(1024)).toBe('1 KB');
    expect(formatBytes(1048576)).toBe('1 MB');
    expect(formatBytes(1073741824)).toBe('1 GB');
  });

  it('formats latencies accurately', () => {
    expect(formatLatency(null)).toBe('0 ms');
    expect(formatLatency(45.67)).toBe('45.7 ms');
    expect(formatLatency(1500)).toBe('1.50 s');
  });

  it('truncates SHA-256 hashes cleanly', () => {
    expect(truncateHash('')).toBe('');
    expect(truncateHash('abc123456789def')).toBe('abc12345...789def');
  });

  it('formats percentages accurately', () => {
    expect(formatPercentage(null)).toBe('0%');
    expect(formatPercentage(0.856)).toBe('85.6%');
    expect(formatPercentage(1)).toBe('100.0%');
  });

  it('formats dates without crashing', () => {
    expect(formatDate(null)).toBe('N/A');
    expect(formatDate('2026-08-28T12:00:00Z')).toContain('2026');
  });
});
