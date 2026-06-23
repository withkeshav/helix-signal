import { gaugeArc, gaugeColor, formatWhen, formatAiAge, formatUsd, pegLabel, formatFreshnessLabel, freshnessBandClass, formatDisplayName, depegVelocityMeta } from '../utils.js';
import { renderCharts, destroyCharts, _makeBar, loadTrendChart, renderSupplyChart, _setupResizeHandler, _disposeAllCharts, _disposeChart } from '../charts.js';

export function useMarket() {
  return {
    // Core market data (from original market.js)
    asset: 'USDT',
    timeRange: '7d',
    enabledAssets: ['USDT', 'USDC', 'DAI', 'PYUSD'],
    assetSnapshots: {},
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
    
    // Chart-related properties
    _charts: new Map(),
    
    // Additional data needed for dashboard cards
    errorOverview: '',
    tickerItems: [],
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
    get adminToken() { return this.$store.ui.adminToken; },
    
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
    formatFreshnessLabel,
    freshnessBandClass,
    formatDisplayName,
    depegVelocityMeta,

    assetSupply(asset) {
      const snap = this.assetSnapshots[asset];
      return snap?.totalSupply ?? (asset === this.asset ? this.totalSupply : null);
    },

    assetScore(asset) {
      const snap = this.assetSnapshots[asset];
      return snap?.signal ?? (asset === this.asset ? this.signal : {});
    },

    assetDepeg(asset) {
      const snap = this.assetSnapshots[asset];
      return snap?.depeg ?? (asset === this.asset ? this.depeg : {});
    },

    assetChains(asset) {
      const snap = this.assetSnapshots[asset];
      return snap?.chains ?? (asset === this.asset ? this.chains : []);
    },
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
    
    // Chart methods
    renderCharts,
    destroyCharts,
    _makeBar,
    loadTrendChart,
    renderSupplyChart,
    _setupResizeHandler,
    _disposeAllCharts,
    _disposeChart,
    
    // Init — called automatically by Alpine when component mounts
    async init() {
      // Skip redundant API calls if dashboard already loaded (tabs share `$store.dashboard`)
      if (!this.$store.dashboard.chains?.length) {
        await this.loadDashboard(this.asset);
        await this.loadAllAssetSnapshots();
        await this.loadAnomalies();
        this.tickerItems = await this.loadTicker();
        await this.loadPredictive();
        await this.loadMarketOverview();
        await this.loadAiExplain();
        await this.loadNarrative();
        await this.loadInsights();
        await this.loadStressLeaderboard();
        await this.loadRotation();
      } else {
        // Sync shared store data to this component's local state
        const s = this.$store.dashboard;
        this.chains = s.chains || [];
        this.signal = s.signal || {};
        this.crossSource = s.crossSource || {};
        this.supplyFeed = s.supplyFeed || {};
        this.attSignal = s.attSignal || {};
        this.depeg = s.depeg || {};
        this.concentration = s.concentration || {};
        this.totalSupply = s.totalSupply;
        this.supplyChange = s.supplyChange;
      }
      
      // Render charts after data is loaded
      this.$nextTick(() => {
        this.renderCharts({ chains: this.chains });
        this.renderSupplyChart();
      });
      
      // Set up resize handler
      this._setupResizeHandler();
      
      // Clean up charts when switching away from tab
      this.$watch('$store.ui.tab', (newTab) => {
        if (newTab !== 'overview' && newTab !== 'supply') {
          this._disposeAllCharts();
        }
      });
      
      // Reload data and charts when asset changes
      this.$watch('$store.dashboard.asset', (newAsset) => {
        this.loadDashboard(newAsset);
        this.loadAllAssetSnapshots();
        this.loadAnomalies();
        this.loadPredictive();
        this.loadMarketOverview();
        this.loadAiExplain();
        this.loadNarrative();
        this.loadInsights();
        this.loadStressLeaderboard();
        this.loadRotation();
        
        // Re-render charts after data reload
        this.$nextTick(() => {
          this.renderCharts({ chains: this.chains });
          this.renderSupplyChart();
        });
      });
    },

    async loadAllAssetSnapshots() {
      const assets = this.enabledAssets || [];
      const results = await Promise.all(
        assets.map(async (sym) => {
          try {
            const r = await fetch(`/api/dashboard?asset=${sym}`, { cache: 'no-store' });
            if (!r.ok) return [sym, null];
            const d = await r.json();
            return [sym, {
              totalSupply: d.total_supply_current,
              signal: d.asset_signal || {},
              depeg: d.depeg_index || {},
              chains: d.chains || [],
            }];
          } catch {
            return [sym, null];
          }
        }),
      );
      const snaps = {};
      for (const [sym, data] of results) {
        if (data) snaps[sym] = data;
      }
      this.assetSnapshots = snaps;
    },

    async loadDashboard(asset) {
      try {
        const r = await fetch(`/api/dashboard?asset=${asset}`, { cache: 'no-store' });
        if (!r.ok) { this.errorOverview = `Dashboard HTTP ${r.status}`; return; }
        const d = await r.json();
        this.chains = d.chains || [];
        this.signal = d.asset_signal || {};
        this.crossSource = d.cross_source_signal || {};
        this.supplyFeed = d.supply_feed || {};
        this.attSignal = d.attestation || {};
        this.depeg = d.depeg_index || {};
        this.concentration = d.chain_concentration || {};
        this.totalSupply = d.total_supply_current;
        this.supplyChange = d.total_supply_change_24h_pct;
        this.$store.dashboard.chains = d.chains || [];
        this.$store.dashboard.signal = d.asset_signal || {};
        this.$store.dashboard.crossSource = d.cross_source_signal || {};
        this.$store.dashboard.supplyFeed = d.supply_feed || {};
        this.$store.dashboard.attSignal = d.attestation || {};
        this.$store.dashboard.depeg = d.depeg_index || {};
        this.$store.dashboard.concentration = d.chain_concentration || {};
        this.$store.dashboard.totalSupply = d.total_supply_current;
        this.$store.dashboard.supplyChange = d.total_supply_change_24h_pct;
        this.$store.dashboard.freshness = d.freshness || {};
        this.$store.dashboard.sources = d.sources || [];
        this.$store.dashboard.generatedAt = d.generated_at || '';
        this.$store.dashboard.nlpAvailable = !!(d.data_quality?.nlp_available);
        this.assetSnapshots[asset] = {
          totalSupply: d.total_supply_current,
          signal: d.asset_signal || {},
          depeg: d.depeg_index || {},
          chains: d.chains || [],
        };
      } catch (e) {
        this.errorOverview = `Dashboard error: ${e.message}`;
      }
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
          this.$store.dashboard.predictive = j;
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