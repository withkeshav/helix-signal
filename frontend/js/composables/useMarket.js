import { gaugeArc, gaugeColor, formatWhen, formatAiAge, formatUsd, pegLabel } from '../utils.js';

export function useMarket() {
  return {
    // Core market data (from original market.js)
    asset: 'USDT',
    timeRange: '7d',
    enabledAssets: ['USDT', 'USDC', 'DAI', 'PYUSD'],
    chains: [],
    signal: {},
    depeg: {},
    concentration: {},
    crossSource: {},
    supplyFeed: {},
    attSignal: {},
    totalSupply: null,
    supplyChange: null,
    anomalyEvents: {},
    _trendCache: { signal: [], peg: [], supply: [] },
    
    // Additional data needed for dashboard cards
    errorOverview: '',
    marketOverview: '',
    aiSummary: '',
    aiNarrative: '',
    aiInsights: '',
    predictive: {},
    stressLeaderboard: [],
    rotation: {},
    
    // AI content timestamps
    marketOverviewGeneratedAt: '',
    marketOverviewExpiresAt: '',
    aiGeneratedAt: '',
    aiExpiresAt: '',
    aiNarrativeGeneratedAt: '',
    aiNarrativeExpiresAt: '',
    aiInsightsGeneratedAt: '',
    aiInsightsExpiresAt: '',
    
    // Computed properties
    get gaugeArc() { return gaugeArc(this.signal.score); },
    get gaugeColor() { return gaugeColor(this.signal.band); },
    
    sparkline(key) {
      const pts = this._trendCache[key || 'signal'];
      if (!pts || pts.length < 2) return '0,10 60,10';
      const max = Math.max(...pts), min = Math.min(...pts), range = max - min || 1;
      const w = 60, h = 20;
      const step = w / (pts.length - 1);
      return pts.map((v, i) => `${(i * step).toFixed(1)},${(h - ((v - min) / range) * (h - 4) - 2).toFixed(1)}`).join(' ');
    },
    
    // Formatting helpers
    formatUsd,
    formatWhen,
    formatAiAge,
    pegLabel,
    
    // UI interaction methods that dispatch events
    switchTo(symbol) {
      if (this.enabledAssets.includes(symbol)) {
        this.asset = symbol;
        this.$dispatch('asset-changed', { asset: symbol });
      }
    },
    
    setTimeRange(range) {
      if (['6h', '24h', '7d', '30d', '90d'].includes(range)) {
        this.timeRange = range;
        this.$dispatch('time-range-changed', { timeRange: range });
      }
    },
    
    downloadDiagnostics() {
      this.$dispatch('download-diagnostics');
    },
    
    loadChartRange() {
      this.$dispatch('chart-range-changed', { timeRange: this.timeRange });
    },
    
    // Core data loading methods (from original market.js)
    async loadAnomalies() {
      try { 
        const r = await fetch(`/api/anomaly/detect?asset=${this.asset}`, { cache: 'no-store' }); 
        if (r.ok) this.anomalyEvents = await r.json(); 
      } catch (e) { 
        this.anomalyEvents = {}; 
      }
    },
    
    async loadPredictive() {
      try { 
        const r = await fetch(`/api/predictive?asset=${this.asset}`, { cache: 'no-store' }); 
        if (r.ok) { 
          const j = await r.json(); 
          this.predictive = j;
          return j; 
        } 
      } catch (e) {}
      return null;
    },
    
    async loadTicker() {
      try {
        const r = await fetch(`/api/events?asset=${this.asset}&limit=12`, { cache: 'no-store' });
        if (!r.ok) return [];
        const j = await r.json();
        const evs = (j.events || []).filter(e => e.severity !== 'debug');
        return evs.length ? evs.concat(evs).map(e => `${(e.severity || 'info').toUpperCase()} · ${formatWhen(e.timestamp)}`) : [];
      } catch (e) { return []; }
    },
    
    async loadSupplyTrend() {
      try {
        const r = await fetch(`/api/trends?asset=${this.asset}&window=30d`, { cache: 'no-store' });
        if (!r.ok) return null;
        const j = await r.json();
        return j;
      } catch (e) { return null; }
    },
    
    // Additional loading methods needed for dashboard cards
    async loadMarketOverview() {
      try {
        const r = await fetch('/api/ai/market-overview', { cache: 'no-store' });
        if (r.ok) {
          const j = await r.json();
          this.marketOverview = j.available ? j.summary : (j.reason || '');
          this.marketOverviewGeneratedAt = j.generated_at || '';
          this.marketOverviewExpiresAt = j.expires_at || '';
          return { summary: this.marketOverview, generatedAt: this.marketOverviewGeneratedAt, expiresAt: this.marketOverviewExpiresAt };
        }
      } catch (e) {}
      return { summary: '', generatedAt: '', expiresAt: '' };
    },
    
    async loadAiExplain() {
      try {
        const r = await fetch(`/api/ai/explain?asset=${this.asset}`, { cache: 'no-store' });
        if (r.ok) {
          const j = await r.json();
          this.aiSummary = j.available ? j.summary : (j.reason || '');
          this.aiGeneratedAt = j.generated_at || '';
          this.aiExpiresAt = j.expires_at || '';
          return { summary: this.aiSummary, generatedAt: this.aiGeneratedAt, expiresAt: this.aiExpiresAt };
        }
      } catch (e) {}
      return { summary: '', generatedAt: '', expiresAt: '' };
    },
    
    async loadNarrative() {
      try {
        const r = await fetch(`/api/ai/narrative?asset=${this.asset}`, { cache: 'no-store' });
        if (r.ok) {
          const j = await r.json();
          this.aiNarrative = j.available ? j.summary : (j.reason || '');
          this.aiNarrativeGeneratedAt = j.generated_at || '';
          this.aiNarrativeExpiresAt = j.expires_at || '';
          return { summary: this.aiNarrative, generatedAt: this.aiNarrativeGeneratedAt, expiresAt: this.aiNarrativeExpiresAt };
        }
      } catch (e) {}
      return { summary: '', generatedAt: '', expiresAt: '' };
    },
    
    async loadInsights() {
      try {
        const r = await fetch(`/api/ai/insights?asset=${this.asset}`, { cache: 'no-store' });
        if (r.ok) {
          const j = await r.json();
          this.aiInsights = j.available ? j.summary : (j.reason || '');
          this.aiInsightsGeneratedAt = j.generated_at || '';
          this.aiInsightsExpiresAt = j.expires_at || '';
          return { summary: this.aiInsights, generatedAt: this.aiInsightsGeneratedAt, expiresAt: this.aiInsightsExpiresAt };
        }
      } catch (e) {}
      return { summary: '', generatedAt: '', expiresAt: '' };
    },
    
    async loadStressLeaderboard() {
      try {
        const r = await fetch(`/api/analytics/stress-leaderboard?asset=${this.asset}`, { cache: 'no-store' });
        if (!r.ok) return;
        const d = await r.json();
        this.stressLeaderboard = d.leaderboard || [];
      } catch (e) {
        this.stressLeaderboard = [];
      }
    },
    
    async loadRotation() {
      try {
        const assets = (this.enabledAssets || []).join(",");
        if (!assets) { this.rotation = { available: false, pairs: [] }; return; }
        const r = await fetch(`/api/analytics/rotation?assets=${encodeURIComponent(assets)}`, { cache: 'no-store' });
        if (!r.ok) { this.rotation = { available: false, pairs: [] }; return; }
        const d = await r.json();
        this.rotation = d;
      } catch (e) {
        this.rotation = { available: false, pairs: [] };
      }
    },
    
    // Utility methods
    aiStillFresh(expiresAt) {
      if (!expiresAt) return false;
      return Date.now() < new Date(expiresAt).getTime();
    },
  };
}