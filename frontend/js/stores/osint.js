export function registerOsintStore(Alpine) {
  Alpine.store('osint', {
    attestation: {},
    osintArticles: [],
    events: [],
    loadingEvents: false,
    errorEvents: '',
    _sentimentSeries: [],

    async loadAttestation() {
      try { const r = await fetch('/api/osint/attestation', { cache: 'no-store' }); if (r.ok) this.attestation = await r.json(); } catch (e) {}
    },

    _formatIntelError(r, label) {
      if (!r) return `Network error loading ${label}.`;
      if (r.status >= 500) return `Server error loading ${label} — retry later.`;
      return `Failed to load ${label} (HTTP ${r.status}).`;
    },

    async loadEvents(asset) {
      this.loadingEvents = true;
      this.errorEvents = '';
      try {
        const ev = await fetch(`/api/events?asset=${asset}&limit=30`, { cache: 'no-store' });
        if (ev.ok) { const j = await ev.json(); this.events = j.events || []; }
        else if (ev.status >= 500) this.errorEvents = this._formatIntelError(ev, 'signal events');
      } catch (e) { this.errorEvents = `Network error loading events: ${e.message}`; }
      try {
        const r = await fetch(`/api/osint/feed?asset=${asset}&limit=15`, { cache: 'no-store' });
        if (r.ok) { this.osintArticles = await r.json(); }
        else if (!this.errorEvents && r.status >= 500) this.errorEvents = this._formatIntelError(r, 'OSINT feed');
      } catch (e) { if (!this.errorEvents) this.errorEvents = `Network error loading OSINT feed: ${e.message}`; }
      try {
        const s = await fetch(`/api/osint/sentiment?asset=${asset}&window_days=7`, { cache: 'no-store' });
        if (s.ok) {
          const series = await s.json();
          if (Array.isArray(series)) { this._sentimentSeries = series; }
        }
      } catch (e) {} finally {
        this.loadingEvents = false;
      }
    },
  });
}
