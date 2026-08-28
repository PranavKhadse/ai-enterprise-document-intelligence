/**
 * Formatting helpers for enterprise presentation: dates, sizes, latencies, hashes.
 */

export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return 'N/A';
  try {
    const d = new Date(dateString);
    if (isNaN(d.getTime())) return dateString;
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(d);
  } catch {
    return dateString;
  }
}

export function formatBytes(bytes: number, decimals = 2): string {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

export function formatLatency(ms: number | undefined | null): string {
  if (ms === undefined || ms === null) return '0 ms';
  if (ms < 1000) {
    return `${ms.toFixed(1)} ms`;
  }
  return `${(ms / 1000).toFixed(2)} s`;
}

export function truncateHash(hash: string | undefined | null, lead = 8, trail = 6): string {
  if (!hash) return '';
  if (hash.length <= lead + trail) return hash;
  return `${hash.substring(0, lead)}...${hash.substring(hash.length - trail)}`;
}

export function formatPercentage(score: number | undefined | null): string {
  if (score === undefined || score === null) return '0%';
  return `${(score * 100).toFixed(1)}%`;
}
