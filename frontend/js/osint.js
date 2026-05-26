export function helixOSINT() {
  return {
    attestation: {},
    osintArticles: [],
    events: [],
    nlpAvailable: false,
    loadingEvents: false,
    errorEvents: '',
    _sentimentSeries: [],

    async loadAttestation() {
      try { const r = await fetch('/api/osint/attestation', { cache: 'no-store' }); if (r.ok) this.attestation = await r.json(); } catch (e) {}
    },

    async loadEvents(asset) {
      this.loadingEvents = true;
      this.errorEvents = '';
      try {
        const ev = await fetch(`/api/events?asset=${asset}&limit=30`, { cache: 'no-store' });
        if (ev.ok) { const j = await ev.json(); this.events = j.events || []; }
      } catch (e) { this.errorEvents = 'Failed to load events'; }
      try {
        const r = await fetch(`/api/osint/feed?asset=${asset}&limit=15`, { cache: 'no-store' });
        if (r.ok) { this.osintArticles = await r.json(); }
      } catch (e) { if (!this.errorEvents) this.errorEvents = 'Failed to load OSINT feed'; }
      try {
        const s = await fetch(`/api/osint/sentiment?asset=${asset}&window_days=7`, { cache: 'no-store' });
        if (s.ok) {
          const series = await s.json();
          if (Array.isArray(series)) { this._sentimentSeries = series; }
        }
      } catch (e) {} finally {
        this.loadingEvents = false;
        if (typeof this.renderSentimentChart === 'function' && Array.isArray(this._sentimentSeries) && this._sentimentSeries.length) {
          this.renderSentimentChart(this._sentimentSeries);
        }
      }
    },

    async loadAiExplain(asset) {
      try {
        const r = await fetch(`/api/ai/explain?asset=${asset}`, { cache: 'no-store' });
        if (r.ok) { const j = await r.json(); return j.available ? j.summary : (j.reason || ''); }
      } catch (e) {}
      return '';
    },

    async loadNarrative(asset) {
      try {
        const r = await fetch(`/api/ai/narrative?asset=${asset}`, { cache: 'no-store' });
        if (r.ok) { const j = await r.json(); return j.available ? j.summary : (j.reason || ''); }
      } catch (e) {}
      return '';
    },

    async loadInsights(asset) {
      try {
        const r = await fetch(`/api/ai/insights?asset=${asset}`, { cache: 'no-store' });
        if (r.ok) { const j = await r.json(); return j.available ? j.summary : (j.reason || ''); }
      } catch (e) {}
      return '';
    },
  };
}
