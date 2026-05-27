export function formatUsd(v) {
  if (v == null || Number.isNaN(Number(v))) return 'N/A';
  const n = Number(v);
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
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

export function formatFeedAge(minutes) {
  if (minutes == null || Number.isNaN(Number(minutes))) return 'No data';
  const m = Number(minutes);
  if (m < 1) return 'just now';
  if (m < 60) return `${Math.round(m)}m ago`;
  if (m < 1440) return `${Math.round(m / 60)}h ago`;
  return `${Math.round(m / 1440)}d ago`;
}

export function statusBand(status) {
  if (status === 'fresh' || status === 'normal') return 'normal';
  if (status === 'aging' || status === 'watch') return 'watch';
  if (status === 'n/a') return 'normal';
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
  if (b === 'risk') return 'var(--down)';
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
