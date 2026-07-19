import { gaugeArc, gaugeColor, formatWhen, formatAiAge, formatUsd, pegLabel, formatFreshnessLabel, freshnessBandClass, formatDisplayName, depegVelocityMeta } from '../utils.js';
import { renderCharts, destroyCharts, _makeBar, loadTrendChart, renderSupplyChart, _setupResizeHandler, _disposeAllCharts, _disposeChart, renderRiskTerminalChart, renderContagionGraph, resizeAllHelixCharts } from '../charts.js';

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
    
    showAllChains: false,
    aiSubTab: 'overview',

    // Chart-related properties
    _charts: new Map(),
    
    // Additional data needed for dashboard cards
    errorOverview: '',

    aiOverviewError: '',
    aiNarrativeError: '',
    aiInsightsError: '',

    marketOverview: '',
    aiSummary: '',
    aiNarrative: '',
    aiInsights: '',
    predictive: {},
    dews: {},
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
    
    _computeSpark(pts) {
      if (!pts || pts.length < 2) return '0,10 60,10';
      const max = Math.max(...pts), min = Math.min(...pts);
      const range = max - min || 1;
      const w = 60, h = 20, step = w / (pts.length - 1);
      return pts.map((v, i) =>
        `${(i*step).toFixed(1)},` +
        `${(h-((v-min)/range)*(h-4)-2).toFixed(1)}`
      ).join(' ');
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
        this.loadChartRange();
      }
    },
    
    downloadDiagnostics() {
      const snapshot = {
        timestamp: new Date().toISOString(),
        asset: this.asset,
        signal: this.signal,
        depeg: this.depeg,
        dews: this.dews,
      };
      const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `helix-diagnostics-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    },
    
    loadChartRange() {
      this.$nextTick(() => {
        this.loadTrendChart();
        this.renderSupplyChart();
      });
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
    renderRiskTerminalChart,
    renderContagionGraph,
    resizeAllHelixCharts,
    
    // Init — called automatically by Alpine when component mounts
    async init() {
      // NOTE: We intentionally do NOT flip `$store.dashboard.loading` to `true`
      // here. Mutating a store flag synchronously inside x-data init() (before
      // the child x-show effects are registered) races Alpine's reactivity and
      // can leave the `x-show="!$store.dashboard.loading"` panel wedged at
      // display:none even after loading settles to false. The dashboard cards
      // already render graceful placeholders ("--"/"N/A") until data arrives,
      // so the panel stays visible and simply fills in once fetches resolve.
      try {
        // Skip redundant API calls if dashboard already loaded (tabs share `$store.dashboard`)
        if (!this.$store.dashboard.chains?.length) {
          await this.loadDashboard(this.asset);
          await this.loadAllAssetSnapshots();
          await this.loadAnomalies();
          await this.loadPredictive();
          await this.loadDews();
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
      } finally {
        this.$store.dashboard.loading = false;
      }
      
      // Render charts after data is loaded
      this.$nextTick(() => {
        this.renderCharts({ chains: this.chains });
        this.renderSupplyChart();
        this.renderRiskTerminalChart(this.predictive);
        this.renderContagionGraph(this.rotation);
      });
      
      // Set up resize handler
      this._setupResizeHandler();
      
      // Clean up charts when switching away from tab
      this.$watch('$store.ui.tab', (newTab) => {
        if (newTab !== 'signal' && newTab !== 'market') {
          this._disposeAllCharts();
        } else {
          this.$nextTick(() => {
            this.renderRiskTerminalChart(this.predictive);
            if (newTab === 'market') this.renderContagionGraph(this.rotation);
            this.resizeAllHelixCharts();
          });
        }
      });
      
      // Reload AI panels when admin session changes
      this.$watch('$store.ui.adminToken', () => this._reloadAiPanels());

      // Reload AI panels when settings change (cross-tab)
      this._settingsChangedHandler = () => this._reloadAiPanels();
      window.addEventListener('settings-changed', this._settingsChangedHandler);

      // Reload data and charts when asset changes
      this.$watch('$store.dashboard.asset', async (newAsset) => {
        if (this.chains.length === 0) this.$store.dashboard.loading = true;
        try {
          await Promise.all([
            this.loadDashboard(newAsset),
            this.loadAllAssetSnapshots(),
            this.loadAnomalies(),
            this.loadPredictive(),
            this.loadDews(),
            this.loadMarketOverview(),
            this.loadAiExplain(),
            this.loadNarrative(),
            this.loadInsights(),
            this.loadStressLeaderboard(),
            this.loadRotation(),
          ]);
        } finally {
          this.$store.dashboard.loading = false;
        }
        
        // Re-render charts after data reload
        this.$nextTick(() => {
          this.renderCharts({ chains: this.chains });
          this.renderSupplyChart();
          this.renderRiskTerminalChart(this.predictive);
          this.renderContagionGraph(this.rotation);
        });
      });

      // Cross-component navigation (Settings -> Signal AI sub-tabs)
      this._aiSubtabSetHandler = (e) => {
        const sub = e?.detail?.subtab;
        if (sub === 'overview' || sub === 'narrative' || sub === 'insights') this.aiSubTab = sub;
      };
      window.addEventListener('ai-subtab-set', this._aiSubtabSetHandler);

      this.$watch('$store.ui.refreshTick', () => this.reloadOnTick());
    },

    async reloadOnTick() {
      const tab = this.$store.ui.tab;
      if (tab !== 'signal' && tab !== 'market') return;
      this.$store.ui.beginFetch();
      try {
        const asset = this.$store.dashboard.asset || this.asset;
        await Promise.all([
          this.loadDashboard(asset),
          this.loadAllAssetSnapshots(),
          this.loadAnomalies(),
          this.loadPredictive(),
          this.loadDews(),
          this.loadStressLeaderboard(),
          this.loadRotation(),
        ]);
      } finally {
        this.$store.ui.endFetch();
      }
      this.$nextTick(() => {
        this.renderCharts({ chains: this.chains });
        this.renderSupplyChart();
        this.renderRiskTerminalChart(this.predictive);
        this.renderContagionGraph(this.rotation);
        this.resizeAllHelixCharts();
      });
    },

    destroy() {
      // Alpine x-if unmount: ensure we dispose chart instances we own.
      if (this._aiSubtabSetHandler) window.removeEventListener('ai-subtab-set', this._aiSubtabSetHandler);
      this._aiSubtabSetHandler = null;
      if (this._settingsChangedHandler) window.removeEventListener('settings-changed', this._settingsChangedHandler);
      this._settingsChangedHandler = null;
      this._disposeAllCharts();
    },

    async loadAllAssetSnapshots() {
      try {
        const r = await fetch('/api/dashboard/summary', { cache: 'no-store' });
        if (!r.ok) return;
        const rows = await r.json();
        const snaps = {};
        for (const row of rows || []) {
          if (!row?.symbol) continue;
          snaps[row.symbol] = {
            totalSupply: row.supply,
            signal: { score: row.score, band: row.band },
            depeg: { current_price: row.peg, peg_status: row.peg != null ? undefined : undefined },
            chains: this.assetSnapshots[row.symbol]?.chains || (row.symbol === this.asset ? this.chains : []),
          };
        }
        this.assetSnapshots = { ...this.assetSnapshots, ...snaps };
      } catch {
        // Keep existing snapshots on failure
      }
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
        this.$store.ui.dataHealthLabel = formatFreshnessLabel(d.freshness?.status) || '—';
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
          this.$nextTick(() => this.renderRiskTerminalChart(j));
          return j; 
        } 
      } catch (e) {}
      return null;
    },

    async loadDews() {
      try {
        const r = await fetch(`/api/dews?asset=${this.asset}`, { cache: 'no-store' });
        if (r.ok) {
          this.dews = await r.json();
          this.$store.dashboard.dews = this.dews;
        }
      } catch (e) {
        this.dews = {};
      }
    },
    
    // Additional loading methods needed for dashboard cards
    async _reloadAiPanels() {
      await Promise.all([
        this.loadMarketOverview(),
        this.loadAiExplain(),
        this.loadNarrative(),
        this.loadInsights(),
      ]);
    },

    _formatAiFetchError(r, label) {
      if (!r) return `Network error loading ${label}.`;
      if (r.status === 401 || r.status === 403) return `Sign in via Settings to load ${label}.`;
      if (r.status >= 500) return `Server error loading ${label} — retry later.`;
      return `${label} unavailable (HTTP ${r.status}). Check AI toggles in Settings.`;
    },

    async loadMarketOverview() {
      this.aiOverviewError = '';
      try {
        const r = await this.$store.ui.adminFetch('/api/ai/market-overview', { cache: 'no-store' });
        if (r.ok) {
          const j = await r.json();
          if (j.available) {
            this.marketOverview = j.summary || '';
          } else {
            this.marketOverview = '';
            this.aiOverviewError = j.reason || 'AI overview disabled — enable feature_ai_summary in Settings.';
          }
          this.marketOverviewGeneratedAt = j.generated_at || '';
          this.marketOverviewExpiresAt = j.expires_at || '';
          return { summary: this.marketOverview, generatedAt: this.marketOverviewGeneratedAt, expiresAt: this.marketOverviewExpiresAt };
        }
        this.marketOverview = '';
        this.aiOverviewError = this._formatAiFetchError(r, 'market overview');
      } catch (e) {
        this.marketOverview = '';
        this.aiOverviewError = `Network error: ${e.message}`;
      }
      return { summary: '', generatedAt: '', expiresAt: '' };
    },
    
    async loadAiExplain() {
      try {
        const r = await this.$store.ui.adminFetch(`/api/ai/explain?asset=${this.asset}`, { cache: 'no-store' });
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
      this.aiNarrativeError = '';
      try {
        const r = await this.$store.ui.adminFetch(`/api/ai/narrative?asset=${this.asset}`, { cache: 'no-store' });
        if (r.ok) {
          const j = await r.json();
          if (j.available) {
            this.aiNarrative = j.summary || '';
          } else {
            this.aiNarrative = '';
            this.aiNarrativeError = j.reason || 'Narrative disabled — enable feature_ai_narrative in Settings.';
          }
          this.aiNarrativeGeneratedAt = j.generated_at || '';
          this.aiNarrativeExpiresAt = j.expires_at || '';
          return { summary: this.aiNarrative, generatedAt: this.aiNarrativeGeneratedAt, expiresAt: this.aiNarrativeExpiresAt };
        }
        this.aiNarrative = '';
        this.aiNarrativeError = this._formatAiFetchError(r, 'narrative');
      } catch (e) {
        this.aiNarrative = '';
        this.aiNarrativeError = `Network error: ${e.message}`;
      }
      return { summary: '', generatedAt: '', expiresAt: '' };
    },
    
    async loadInsights() {
      this.aiInsightsError = '';
      try {
        const r = await this.$store.ui.adminFetch(`/api/ai/insights?asset=${this.asset}`, { cache: 'no-store' });
        if (r.ok) {
          const j = await r.json();
          if (j.available) {
            this.aiInsights = j.summary || '';
          } else {
            this.aiInsights = '';
            this.aiInsightsError = j.reason || 'Insights disabled — enable feature_ai_insights in Settings.';
          }
          this.aiInsightsGeneratedAt = j.generated_at || '';
          this.aiInsightsExpiresAt = j.expires_at || '';
          return { summary: this.aiInsights, generatedAt: this.aiInsightsGeneratedAt, expiresAt: this.aiInsightsExpiresAt };
        }
        this.aiInsights = '';
        this.aiInsightsError = this._formatAiFetchError(r, 'insights');
      } catch (e) {
        this.aiInsights = '';
        this.aiInsightsError = `Network error: ${e.message}`;
      }
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
        this.$store.dashboard.rotation = d;
        this.$nextTick(() => this.renderContagionGraph(d));
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