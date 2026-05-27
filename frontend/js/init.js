import { formatUsd, formatWhen, formatFeedAge, statusBand, pegLabel, formatAiAge } from './utils.js';
import { helixMarket } from './market.js';
import { helixOSINT } from './osint.js';
import { helixGovernance } from './governance.js';
import { helixForecast } from './forecast.js';
import {
  _disposeChart, destroyCharts, destroyForecastCharts, _disposeAllCharts,
  _setupResizeHandler, renderCharts, loadTrendChart, _makeBar,
  renderSentimentChart, renderForecastCharts, _renderForecastChartsImpl,
  _renderForecastCanvas, renderSupplyChart,
} from './charts.js';
import Alpine from 'https://cdn.jsdelivr.net/npm/alpinejs@3.14.9/dist/module.esm.js';

Alpine.data('helixApp', () => {
  const m = helixMarket();
  const o = helixOSINT();
  const g = helixGovernance();
  const f = helixForecast();

  return {
    ...m,
    ...o,
    ...g,
    ...f,

    formatUsd,
    formatWhen,
    formatFeedAge,
    statusBand,
    pegLabel,
    formatAiAge,

    _disposeChart,
    destroyCharts,
    destroyForecastCharts,
    _disposeAllCharts,
    _setupResizeHandler,
    renderCharts,
    loadTrendChart,
    _makeBar,
    renderSentimentChart,
    renderForecastCharts,
    _renderForecastChartsImpl,
    _renderForecastCanvas,
    renderSupplyChart,

    tab: 'overview',
    theme: 'light',
    searchQuery: '',
    searchResults: [],
    freshness: {},
    sources: [],
    staleWarning: '',
    generatedAt: '',
    _charts: new Map(),
    _echarts: new Map(),
    _timer: null,
    _loadingDashboard: false,
    _refreshingStale: false,
    refreshing: false,
    predictive: {},
    aiSummary: '',
    aiNarrative: '',
    aiInsights: '',
    marketOverview: '',
    _marketOverviewLoaded: false,
    aiGeneratedAt: '',
    aiExpiresAt: '',
    aiNarrativeGeneratedAt: '',
    aiNarrativeExpiresAt: '',
    aiInsightsGeneratedAt: '',
    aiInsightsExpiresAt: '',
    marketOverviewGeneratedAt: '',
    marketOverviewExpiresAt: '',
    tickerItems: [],
    stressLeaderboard: [],
    adminOk: false,
    evidenceOpen: false,
    evidenceTitle: '',
    evidenceFormula: '',
    evidenceComponents: {},
    evidenceSources: {},
    dataQualityHistory: [],
    rotation: {},

    aiStillFresh(expiresAt) {
      if (!expiresAt) return false;
      return Date.now() < new Date(expiresAt).getTime();
    },

    async init() {
      const root = document.documentElement;
      this.theme = root.getAttribute('data-theme') || 'light';
      await this.loadAssets();
      await this.loadDashboard();
      await this.loadAttestation();
      this._timer = setInterval(() => {
        if (document.hidden) return;
        this.loadDashboard();
      }, 60000);
      this._setupResizeHandler();
    },

    search() {
      const q = this.searchQuery.trim();
      if (!q || q.length < 2) { this.searchResults = []; return; }
      this.searchResults = [];
      for (const a of this.enabledAssets) {
        if (a.toLowerCase().includes(q.toLowerCase())) {
          this.searchResults.push({ id: `asset-${a}`, label: a, type: 'Asset' });
        }
      }
      if (this.searchResults.length === 0 && q.length >= 2) {
        this.searchResults.push({ id: 'custom', label: q.toUpperCase(), type: 'Switch asset' });
      }
    },

    selectSearchResult(r) {
      if (r.id === 'custom' && !this.enabledAssets.includes(r.label)) {
        this.enabledAssets.push(r.label);
      }
      this.asset = r.label;
      this.searchQuery = '';
      this.searchResults = [];
      this.switchAsset();
    },

    showEvidence(type) {
      if (type === 'score') {
        this.evidenceTitle = `Risk Score Evidence · ${this.asset}`;
        this.evidenceFormula = 'score = peg_deviation * w1 + concentration * w2 + liquidity * w3 + supply_momentum * w4';
        this.evidenceComponents = this.signal.components || {};
        this.evidenceSources = {};
        for (const s of this.sources) this.evidenceSources[s.source_name] = { status: s.status };
      } else if (type === 'peg') {
        this.evidenceTitle = `Peg Evidence · ${this.asset}`;
        this.evidenceFormula = 'depeg_index = round(abs(deviation_bps) / 100 * 100, 0)';
        this.evidenceComponents = {
          current_price: this.depeg.current_price,
          deviation_abs: this.depeg.deviation_abs,
          deviation_pct: this.depeg.deviation_pct,
          peg_status: this.depeg.peg_status,
          depeg_index: this.depeg.score,
        };
        this.evidenceSources = { defillama: { status: 'ok' }, coingecko: { status: 'ok' }, dexscreener: { status: 'ok' } };
      }
      this.evidenceOpen = true;
    },

    copyEvidence() {
      const txt = [`Title: ${this.evidenceTitle}`];
      if (this.evidenceFormula) txt.push(`Formula: ${this.evidenceFormula}`);
      const comps = Object.entries(this.evidenceComponents).map(([k, v]) => `  ${k}: ${v}`);
      if (comps.length) txt.push('Components:', ...comps);
      navigator.clipboard?.writeText(txt.join('\n'));
    },

    async loadAssets() {
      try { const r = await fetch('/api/assets', { cache: 'no-store' }); if (r.ok) { const a = await r.json(); this.enabledAssets = a.map(x => x.symbol); } } catch (e) {}
    },

    async loadDashboard() {
      if (this._loadingDashboard) return;
      this._loadingDashboard = true;
      try {
        const r = await fetch(`/api/dashboard?asset=${this.asset}`, { cache: 'no-store' });
        if (!r.ok) throw Error(`HTTP ${r.status}`);
        const d = await r.json();

        this.chains = d.chains || [];
        this.signal = d.asset_signal || {};
        this.crossSource = d.cross_source_signal || {};
        this.supplyFeed = d.supply_feed || {};
        this.attSignal = d.attestation || {};
        this.depeg = d.depeg_index || {};
        this.concentration = d.chain_concentration || {};
        this.freshness = d.freshness || {};
        this.sources = d.sources || [];
        this.totalSupply = d.total_supply_current;
        this.supplyChange = d.total_supply_change_24h_pct;
        this.generatedAt = new Date().toLocaleTimeString();
        this.nlpAvailable = !!(d.data_quality && d.data_quality.nlp_available);
        this.staleWarning = this.freshness.status === 'Stale' ? 'Data is stale. Metrics may not reflect current conditions.' : '';

        { const s = Number(this.signal.score); if (!Number.isNaN(s)) { const a = this._trendCache.signal || []; a.push(s); if (a.length > 120) a.splice(0, a.length - 120); this._trendCache.signal = a; } }
        { const p = d.depeg_index?.current_price; if (p != null) { const a = this._trendCache.peg || []; a.push(Number(p)); if (a.length > 120) a.splice(0, a.length - 120); this._trendCache.peg = a; } }
        { const sp = d.total_supply_current; if (sp != null) { const a = this._trendCache.supply || []; a.push(Number(sp)); if (a.length > 120) a.splice(0, a.length - 120); this._trendCache.supply = a; } }

        if (d.data_quality) {
          this.dataQualityHistory = [
            { label: 'NLP sentiment', value: d.data_quality.nlp_available ? 'ON' : 'OFF' },
            { label: 'Cached data', value: d.data_quality.using_cached_data ? 'YES' : 'NO' },
            { label: 'Degraded sources', value: (d.data_quality.degraded_sources || []).join(', ') || 'none' },
          ];
        }

        if (this.freshness.status === 'Stale' && this.adminToken && !this._refreshingStale) {
          this._refreshingStale = true;
          this.refresh().finally(() => { this._refreshingStale = false; });
        }

        this.renderCharts(d);
        await this.loadAnomalies();

        const pred = await this.loadPredictive();
        this.predictive = pred || {};
        this.tickerItems = await this.loadTicker();
        await this.loadStressLeaderboard();
        await this.loadRotation();

        if (!this.aiStillFresh(this.aiExpiresAt)) {
          const r = await this.loadAiExplain(this.asset); this.aiSummary = r.summary; this.aiGeneratedAt = r.generatedAt; this.aiExpiresAt = r.expiresAt;
        }
        if (!this.aiStillFresh(this.aiNarrativeExpiresAt)) {
          const r = await this.loadNarrative(this.asset); this.aiNarrative = r.summary; this.aiNarrativeGeneratedAt = r.generatedAt; this.aiNarrativeExpiresAt = r.expiresAt;
        }
        if (!this.aiStillFresh(this.aiInsightsExpiresAt)) {
          const r = await this.loadInsights(this.asset); this.aiInsights = r.summary; this.aiInsightsGeneratedAt = r.generatedAt; this.aiInsightsExpiresAt = r.expiresAt;
        }

        if (!this._marketOverviewLoaded && !this.aiStillFresh(this.marketOverviewExpiresAt)) {
          const r = await this.loadMarketOverview();
          this.marketOverview = r.summary;
          this.marketOverviewGeneratedAt = r.generatedAt;
          this.marketOverviewExpiresAt = r.expiresAt;
          this._marketOverviewLoaded = true;
        }

        if (this.tab === 'intel') await this.loadIntel();
        if (this.tab === 'events') await this.loadEvents(this.asset);
        else if (this._sentimentSeries.length) this.renderSentimentChart(this._sentimentSeries);
        if (this.tab === 'forecast') { await this.loadForecastData(this.asset); await this.loadForecastAccuracy(this.asset); }
      } catch (e) { this.staleWarning = `Dashboard error: ${e.message}`; }
      finally { this._loadingDashboard = false; }
    },

    async loadIntel() {
      await this.loadAttestation();
    },

    async loadTab() {
      if (this.tab === 'forecast') await this.loadForecastData(this.asset);
      if (this.tab === 'intel') await this.loadIntel();
      if (this.tab === 'events') await this.loadEvents(this.asset);
      if (this.tab === 'supply') await this.renderSupplyChart();
      if (this.tab === 'health') await this.loadEvents(this.asset);
      if (this.tab === 'settings') { this.adminOk = await this.loadSettings(); await this.loadAiBudget(); }
    },

    async refresh() {
      this.refreshing = true;
      try {
        const r = await fetch('/api/refresh', { method: 'POST', cache: 'no-store', headers: this._adminHeaders() });
        if (!r.ok) throw Error(`HTTP ${r.status}`);
      } catch (e) { this.staleWarning = 'Refresh failed. Set admin token in Settings if HELIX_ADMIN_TOKEN is configured.'; }
      await this.loadDashboard();
      this.refreshing = false;
    },

    cycleTheme() {
      const root = document.documentElement;
      this.theme = this.theme === 'light' ? 'dark' : 'light';
      root.setAttribute('data-theme', this.theme);
      if (this.chains.length) {
        this.destroyCharts();
        this.renderCharts({ chains: this.chains });
      }
      this.destroyForecastCharts();
      if (this._forecastData) this.renderForecastCharts();
    },

    switchTo(symbol) {
      this.asset = symbol;
      this.switchAsset();
    },

    async switchAsset() {
      this._disposeAllCharts();
      await this.loadDashboard();
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

    loadChartRange() {
      this.loadTrendChart();
      this.renderCharts({ chains: this.chains });
      this.destroyForecastCharts();
    },
  };
});

Alpine.start();
