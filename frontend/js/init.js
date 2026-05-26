import { formatUsd, formatWhen, formatFeedAge, statusBand, pegLabel } from './utils.js';
import { helixMarket } from './market.js';
import { helixOSINT } from './osint.js';
import { helixGovernance } from './governance.js';
import { helixForecast } from './forecast.js';

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
    tickerItems: [],
    evidenceOpen: false,
    evidenceTitle: '',
    evidenceFormula: '',
    evidenceComponents: {},
    evidenceSources: {},
    dataQualityHistory: [],

    async init() {
      const root = document.documentElement;
      this.theme = root.getAttribute('data-theme') || 'light';
      await this.loadAssets();
      await this.loadDashboard();
      await this.loadAttestation();
      this._timer = setInterval(() => { this.loadDashboard(); }, 60000);
      this._setupResizeHandler();
    },

    _setupResizeHandler() {
      if (window._helixResizeHandler) return;
      window._helixResizeHandler = () => {
        for (const [, c] of this._charts) {
          if (typeof c.resize === 'function') c.resize();
        }
        for (const [, c] of this._echarts) {
          if (typeof c.isDisposed === 'function' && !c.isDisposed()) c.resize();
        }
      };
      window.addEventListener('resize', window._helixResizeHandler);
    },

    _disposeChart(c) {
      if (!c) return;
      if (typeof c.dispose === 'function') {
        if (typeof c.isDisposed !== 'function' || !c.isDisposed()) c.dispose();
      } else if (typeof c.destroy === 'function') {
        c.destroy();
      }
    },

    destroyCharts() {
      for (const [, c] of this._charts) this._disposeChart(c);
      this._charts.clear();
    },

    destroyForecastCharts() {
      for (const [, c] of this._echarts) this._disposeChart(c);
      this._echarts.clear();
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

        this.aiSummary = await this.loadAiExplain(this.asset);
        this.aiNarrative = await this.loadNarrative(this.asset);
        this.aiInsights = await this.loadInsights(this.asset);

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
      if (this.tab === 'settings') await this.loadSettings();
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
      this.destroyCharts();
      this.destroyForecastCharts();
      await this.loadDashboard();
    },

    loadChartRange() {
      this.loadTrendChart();
      this.renderCharts({ chains: this.chains });
      this.destroyForecastCharts();
    },

    renderCharts(data) {
      this.destroyCharts();
      if (typeof Chart === 'undefined') return;
      const primary = getComputedStyle(document.documentElement).getPropertyValue('--spark').trim() || '#60a5fa';
      const chains = data.chains || [];
      if (chains.length) {
        const sorted = [...chains].sort((a, b) => Number(b.chain_share_pct || 0) - Number(a.chain_share_pct || 0)).slice(0, 12);
        const labels = sorted.map(c => c.chain_name);
        const vals = sorted.map(c => c.chain_share_pct || 0);
        const supplyVals = sorted.map(c => c.supply_current || 0);
        this._makeBar('chart-distribution', labels, vals, primary);
        this._makeBar('chart-supply-bar', labels, supplyVals, primary);
      }
      this.loadTrendChart();
    },

    loadTrendChart() {
      const _asset = this.asset;
      try {
        const muted = getComputedStyle(document.documentElement).getPropertyValue('--muted').trim() || '#9aa8c4';
        const primary = getComputedStyle(document.documentElement).getPropertyValue('--spark').trim() || '#60a5fa';
        const tr = this.timeRange || '7d';
        fetch(`/api/trends?asset=${this.asset}&window=${tr}`, { cache: 'no-store' })
          .then(r => r.ok ? r.json() : null)
          .then(t => {
            if (this.asset !== _asset) return;
            if (!t || !t.points || !t.points.length || typeof Chart === 'undefined') return;
            const el = document.getElementById('chart-trend-signal');
            if (!el) return;
            if (this._charts.has('chart-trend-signal')) this._disposeChart(this._charts.get('chart-trend-signal'));
            const pts = t.points.map(p => ({ x: new Date(p.timestamp).getTime(), y: p.signal_score != null ? Number(p.signal_score) : null }));
            this._charts.set('chart-trend-signal', new Chart(el.getContext('2d'), {
              type: 'line',
              data: { datasets: [{ data: pts, borderColor: primary, backgroundColor: 'rgba(59,130,246,0.08)', fill: true, tension: 0.25, pointRadius: 0, borderWidth: 2 }] },
              options: {
                responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } },
                scales: { x: { type: 'linear', ticks: { color: muted }, grid: { color: 'rgba(128,128,128,0.1)' } }, y: { min: 0, max: 100, ticks: { color: muted }, grid: { color: 'rgba(128,128,128,0.1)' } } },
              },
            }));
          })
          .catch(() => {});
      } catch (e) {}
    },

    _makeBar(canvasId, labels, values, color) {
      if (this._charts.has(canvasId)) this._disposeChart(this._charts.get(canvasId));
      const el = document.getElementById(canvasId);
      if (!el || typeof Chart === 'undefined') return;
      const muted = getComputedStyle(document.documentElement).getPropertyValue('--muted').trim() || '#9aa8c4';
      this._charts.set(canvasId, new Chart(el.getContext('2d'), {
        type: 'bar', data: { labels, datasets: [{ label: '', data: values, backgroundColor: color, borderRadius: 4 }] },
        options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: muted }, grid: { color: 'rgba(128,128,128,0.1)' } }, y: { ticks: { color: muted }, grid: { color: 'rgba(128,128,128,0.1)' } } } },
      }));
    },

    renderSentimentChart(series) {
      if (!series || !series.length || typeof Chart === 'undefined') return;
      if (this._charts.has('chart-sentiment')) this._disposeChart(this._charts.get('chart-sentiment'));
      const el = document.getElementById('chart-sentiment');
      if (!el) return;
      const primary = getComputedStyle(document.documentElement).getPropertyValue('--spark').trim() || '#60a5fa';
      this._charts.set('chart-sentiment', new Chart(el.getContext('2d'), {
        type: 'line',
        data: { labels: series.map(s => s.date), datasets: [{ label: 'Avg Sentiment', data: series.map(s => s.avg_sentiment), borderColor: primary, fill: false, tension: 0.25 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { min: -1, max: 1 } } },
      }));
    },

    renderForecastCharts() {
      if (typeof echarts === 'undefined') return;
      const elPeg = document.getElementById('chart-peg-forecast');
      const elSupply = document.getElementById('chart-supply-forecast');
      if (!elPeg || !elSupply) return;
      const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#e8edf7';
      const lineColor = getComputedStyle(document.documentElement).getPropertyValue('--line').trim() || '#273247';
      const baseConfig = {
        tooltip: { trigger: 'axis' }, grid: { left: 50, right: 16, top: 20, bottom: 36 },
        xAxis: { type: 'time', axisLine: { lineStyle: { color: lineColor } }, axisLabel: { color: textColor } },
        yAxis: { type: 'value', splitLine: { lineStyle: { color: lineColor, opacity: 0.2 } }, axisLabel: { color: textColor } },
        legend: { bottom: 0, textStyle: { color: textColor, fontSize: 11 } },
        animation: false,
      };
      const data = this._forecastData || {};
      const pegForecast = (data.forecast_points?.peg) || [];
      const pegHistorical = (data.historical?.peg) || [];
      const supplyForecast = (data.forecast_points?.supply) || [];
      const supplyHistorical = (data.historical?.supply) || [];
      this._renderForecastCanvas(elPeg, 'Peg Forecast', pegHistorical, pegForecast, baseConfig, textColor, lineColor);
      this._renderForecastCanvas(elSupply, 'Supply Forecast', supplyHistorical, supplyForecast, baseConfig, textColor, lineColor);
    },

    _renderForecastCanvas(el, title, historical, forecast, baseConfig, textColor, lineColor) {
      if (this._echarts.has(el.id)) { this._disposeChart(this._echarts.get(el.id)); this._echarts.delete(el.id); }
      const chart = echarts.init(el);
      this._echarts.set(el.id, chart);
      const series = forecast && forecast.length
        ? [
            { name: 'q10 base', type: 'line', data: forecast.map(p => [p.timestamp, p.q10 ?? p.q50 * 0.997]), lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 }, stack: 'confidence', areaStyle: { color: 'rgba(59,130,246,0.06)' }, symbol: 'none' },
            { name: '90% Band', type: 'line', data: forecast.map(p => [p.timestamp, Math.max(0, (p.q90 ?? p.q50) - p.q10)]), lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 }, stack: 'confidence', areaStyle: { color: 'rgba(59,130,246,0.08)' }, symbol: 'none' },
            { name: 'Median', type: 'line', data: forecast.map(p => [p.timestamp, p.q50]), lineStyle: { width: 2, color: '#3b82f6' }, symbol: 'none', z: 10 },
            { name: 'Historical', type: 'line', data: historical.map(p => [p.timestamp, p.value]), lineStyle: { width: 1.5, color: textColor }, symbolSize: 2, z: 10 },
          ]
        : [{ name: 'No forecast data', type: 'line', data: historical.map(p => [p.timestamp, p.value]), lineStyle: { width: 1.5, color: textColor }, symbolSize: 2, z: 10 }];
      chart.setOption({ ...baseConfig,
        title: { text: title, left: 'center', top: 0, textStyle: { color: textColor, fontSize: 13, fontWeight: 500 } },
        grid: { left: 50, right: 16, top: 36, bottom: 40 },
        series,
      });
    },

    async renderSupplyChart() {
      const d = await this.loadSupplyTrend();
      if (!d || !d.points || !d.points.length || typeof Chart === 'undefined') return;
      const el = document.getElementById('chart-supply-trend');
      if (!el) return;
      if (this._charts.has('chart-supply-trend')) this._disposeChart(this._charts.get('chart-supply-trend'));
      const pts = d.points.filter(p => p.total_supply != null).map(p => ({ x: new Date(p.timestamp).getTime(), y: Number(p.total_supply) }));
      const primary = getComputedStyle(document.documentElement).getPropertyValue('--spark').trim() || '#60a5fa';
      this._charts.set('chart-supply-trend', new Chart(el.getContext('2d'), {
        type: 'line',
        data: { datasets: [{ data: pts, borderColor: primary, backgroundColor: 'rgba(59,130,246,0.08)', fill: true, tension: 0.25, pointRadius: 0, borderWidth: 2 }] },
        options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } }, scales: { x: { type: 'linear', ticks: { display: false }, grid: { display: false } }, y: { ticks: { callback: v => formatUsd(v) } } } },
      }));
    },
  };
});

Alpine.prefix('x-');
Alpine.initTree(document.documentElement);
