import { formatWhen, formatFreshnessLabel, freshnessBandClass } from '../utils.js';

export function useHealth() {
  return {
    sources: [],
    sourceUsage: null,
    freshness: {},
    events: [],
    dataQualityHistory: [],
    loading: false,
    error: '',
    formatWhen,
    formatFreshnessLabel,
    freshnessBandClass,

    async init() {
      await this._loadAll();
      this.$watch('$store.ui.refreshTick', () => {
        if (this.$store.ui.tab === 'system') this._loadAll();
      });
    },

    async _loadAll() {
      this.loading = true;
      this.error = '';
      const failures = [];
      try {
        const [sourcesRes, usageRes, dashRes, eventsRes, dqRes] = await Promise.all([
          fetch('/api/sources/status', { cache: 'no-store' }),
          fetch('/api/sources/usage', { cache: 'no-store' }),
          fetch('/api/dashboard', { cache: 'no-store' }),
          fetch('/api/events?limit=50', { cache: 'no-store' }),
          fetch('/api/data-quality/summary', { cache: 'no-store' }),
        ]);
        if (sourcesRes.ok) {
          this.sources = await sourcesRes.json();
        } else {
          failures.push(`sources (${sourcesRes.status})`);
        }
        if (usageRes.ok) {
          this.sourceUsage = await usageRes.json();
        } else {
          failures.push(`usage (${usageRes.status})`);
        }
        if (dashRes.ok) {
          const d = await dashRes.json();
          this.freshness = d.freshness || {};
        } else {
          failures.push(`dashboard (${dashRes.status})`);
        }
        if (dqRes.ok) {
          const dq = await dqRes.json();
          const hist = dq.history || [];
          this.dataQualityHistory = hist.length
            ? hist.map(h => ({ label: h.generated_at?.slice(0, 10), value: Math.round(h.overall_score) }))
            : [{ label: 'Score', value: Math.round(dq.overall_score || 0) }];
        } else {
          failures.push(`data-quality (${dqRes.status})`);
        }
        if (eventsRes.ok) {
          const j = await eventsRes.json();
          this.events = j.events || [];
        } else {
          failures.push(`events (${eventsRes.status})`);
        }
        if (failures.length) {
          this.error = `Failed to load: ${failures.join(', ')}`;
        }
      } catch (e) {
        this.error = `Failed to load health data: ${e.message}`;
      } finally {
        this.loading = false;
      }
    },
  };
}
