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
    },

    async _loadAll() {
      this.loading = true;
      this.error = '';
      const failures = [];
      try {
        const [sourcesRes, usageRes, dashRes, eventsRes] = await Promise.all([
          fetch('/api/sources/status', { cache: 'no-store' }),
          fetch('/api/sources/usage', { cache: 'no-store' }),
          fetch('/api/dashboard', { cache: 'no-store' }),
          fetch('/api/events?limit=50', { cache: 'no-store' }),
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
          this.dataQualityHistory = [
            { label: 'Degraded sources', value: (d.data_quality?.degraded_sources || []).length || 0 },
            { label: 'Using cached data', value: d.data_quality?.using_cached_data ? 'Yes' : 'No' },
            { label: 'NLP available', value: d.data_quality?.nlp_available ? 'Yes' : 'No' },
          ];
        } else {
          failures.push(`dashboard (${dashRes.status})`);
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
