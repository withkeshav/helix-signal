export function formatUsd(v) {
  return formatSI(v, { prefix: '$' });
}

/** Abbreviate large numbers with SI suffixes (K/M/B/T). */
export function formatSI(v, opts = {}) {
  const { prefix = '', suffix = '', decimals = 2 } = opts;
  if (v == null || Number.isNaN(Number(v))) return 'N/A';
  const n = Number(v);
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1e12) return `${sign}${prefix}${(abs / 1e12).toFixed(decimals)}T${suffix}`;
  if (abs >= 1e9) return `${sign}${prefix}${(abs / 1e9).toFixed(decimals)}B${suffix}`;
  if (abs >= 1e6) return `${sign}${prefix}${(abs / 1e6).toFixed(decimals)}M${suffix}`;
  if (abs >= 1e3) return `${sign}${prefix}${(abs / 1e3).toFixed(decimals)}K${suffix}`;
  return `${sign}${prefix}${n.toLocaleString(undefined, { maximumFractionDigits: decimals })}${suffix}`;
}

/** Normalize freshness status strings to lowercase canonical form. */
export function normalizeFreshnessStatus(status) {
  if (status == null || status === '') return 'unknown';
  return String(status).toLowerCase().replace(/\s+/g, '_');
}

/** Human-readable freshness label (Title Case). */
export function formatFreshnessLabel(status) {
  const s = normalizeFreshnessStatus(status);
  if (s === 'fresh') return 'Fresh';
  if (s === 'aging') return 'Aging';
  if (s === 'stale') return 'Stale';
  if (s === 'very_stale') return 'Very Stale';
  if (s === 'unknown') return 'Unknown';
  return String(status);
}

/** CSS class for freshness KPI coloring. */
export function freshnessBandClass(status) {
  const s = normalizeFreshnessStatus(status);
  if (s === 'fresh') return 'text-green';
  if (s === 'aging') return 'band-watch';
  if (s === 'stale' || s === 'very_stale') return 'text-red';
  return '';
}

export function formatWhen(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const s = (Date.now() - d.getTime()) / 1e3;
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago · ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  return `${d.toLocaleString()} · ${Intl.DateTimeFormat().resolvedOptions().timeZone}`;
}

/** Format timestamp for chart axes and tooltips. */
export function formatDate(ts, style = 'short') {
  if (ts == null || ts === '') return '';
  const d = ts instanceof Date ? ts : new Date(ts);
  if (Number.isNaN(d.getTime())) return '';
  if (style === 'axis') {
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  if (style === 'date') {
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }
  return d.toLocaleString();
}

export function formatFeedAge(minutes) {
  if (minutes == null || Number.isNaN(Number(minutes))) return 'No data';
  const m = Number(minutes);
  if (m < 1) return 'just now';
  if (m < 60) return `${Math.round(m)}m ago`;
  if (m < 1440) return `${Math.round(m / 60)}h ago`;
  return `${Math.round(m / 1440)}d ago`;
}

export function statusBand(status) {
  const s = normalizeFreshnessStatus(status);
  if (s === 'fresh' || s === 'normal' || s === 'healthy') return 'normal';
  if (s === 'aging' || s === 'watch') return 'watch';
  if (s === 'n/a' || s === 'unknown') return 'normal';
  return 'risk';
}

export function pegLabel(p) {
  const d = Math.abs(p - 1);
  if (d <= 0.001) return 'Healthy';
  if (d <= 0.005) return 'Watch';
  return 'Alert';
}

export function gaugeArc(score) {
  const s = Number(score);
  if (Number.isNaN(s)) return 0;
  return Math.max(0, Math.min(251, (s / 100) * 251));
}

export function gaugeColor(band) {
  const b = (band || '').toLowerCase();
  if (b === 'risk' || b === 'alert') return 'var(--down)';
  if (b === 'watch') return 'var(--neutral)';
  return 'var(--up)';
}

export function formatAiAge(generatedAt, expiresAt) {
  if (!generatedAt) return '';
  const gen = new Date(generatedAt);
  const genLocal = gen.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (!expiresAt) return `Updated ${genLocal}`;
  const exp = new Date(expiresAt);
  const expLocal = exp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return `Updated ${genLocal} · Next ${expLocal}`;
}

/** Display name for rotation / analytics labels (snake_case → readable). */
export function formatDisplayName(key) {
  if (!key) return '';
  const known = {
    DAI_gaining_on_USDC: 'DAI gaining on USDC',
    USDC_gaining_on_DAI: 'USDC gaining on DAI',
    USDT_gaining_on_USDC: 'USDT gaining on USDC',
    PYUSD_gaining_on_USDT: 'PYUSD gaining on USDT',
  };
  if (known[key]) return known[key];
  return String(key).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

/** Label + unit for depeg velocity fields. */
export function depegVelocityMeta(field) {
  const map = {
    '1h': { label: '1h Δ', unit: 'index pts', tooltip: 'Change in depeg index over the last hour' },
    '4h': { label: '4h Δ', unit: 'index pts', tooltip: 'Change in depeg index over the last 4 hours' },
    '12h': { label: '12h Δ', unit: 'index pts', tooltip: 'Change in depeg index over the last 12 hours' },
  };
  return map[field] || { label: field, unit: '', tooltip: '' };
}
