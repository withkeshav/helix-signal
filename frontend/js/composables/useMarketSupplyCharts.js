import { formatUsd } from '../utils.js';
import {
  _disposeChart,
  _disposeAllCharts,
  _setupResizeHandler,
  _makeBar,
  renderSupplyChart,
  destroyCharts,
  destroyForecastCharts,
} from '../charts.js';

export function useMarketSupplyCharts() {
  return {
    // UI helpers (used directly from index.html)
    formatUsd,

    // Fixed label in UI: "Supply Trend (30d)"
    timeRange: '30d',

    // Local ECharts containers
    _charts: new Map(),
    _echarts: new Map(),

    // "Store-backed" UI state (keeps index.html markup mostly unchanged)
    get asset() { return this.$store.dashboard.asset || 'USDT'; },
    get totalSupply() { return this.$store.dashboard.totalSupply; },
    get supplyChange() { return this.$store.dashboard.supplyChange; },
    get chains() { return this.$store.dashboard.chains || []; },
    get concentration() { return this.$store.dashboard.concentration || {}; },

    // Reuse chart helpers (they depend on `this` having _charts/_echarts)
    _disposeChart,
    _disposeAllCharts,
    _setupResizeHandler,
    _makeBar,
    renderSupplyChart,
    destroyCharts,
    destroyForecastCharts,

    _didOwnCharts: false,

    async init() {
      // If signal tab is x-show-mounted, it may already own these charts.
      // We only render supply charts when the canvas has no ECharts instances.
      this._activateIfNeeded();

      // Render/update when entering market tab (x-show during early phases,
      // x-if later).
      this.$watch('$store.ui.tab', (tab) => {
        if (tab === 'market') this._activateIfNeeded();
        else this._maybeDeactivate();
      });
    },

    _maybeDeactivate() {
      // Once x-if unmounts Market, destroy() will run. During x-show phases,
      // disposing here avoids hidden chart churn if we owned them.
      if (this._didOwnCharts) this._disposeAllCharts();
      this._didOwnCharts = false;
    },

    _hasSupplyChartInstances() {
      if (typeof echarts === 'undefined' || !echarts.getInstanceByDom) return false;
      const bar = document.getElementById('chart-supply-bar');
      const trend = document.getElementById('chart-supply-trend');
      const barInst = bar ? echarts.getInstanceByDom(bar) : null;
      const trendInst = trend ? echarts.getInstanceByDom(trend) : null;
      return !!(barInst || trendInst);
    },

    async _activateIfNeeded() {
      if (this.$store.ui.tab !== 'market') return;

      // If another component already initialized charts on these nodes,
      // do not re-init.
      if (this._hasSupplyChartInstances()) return;

      // Ensure dashboard summary is present for the KPIs + supply-by-chain chart.
      await this._ensureDashboardSummary();

      // Only render when DOM nodes exist.
      this._renderSupplyByChain();
      await this.renderSupplyChart();

      this._didOwnCharts = true;
      this._setupResizeHandler();
    },

    async _ensureDashboardSummary() {
      const d = this.$store.dashboard;
      if (d.chains && d.chains.length && d.totalSupply != null && d.concentration) return;

      this.$store.dashboard.loading = true;
      try {
        const r = await fetch(`/api/dashboard?asset=${encodeURIComponent(this.asset)}`, { cache: 'no-store' });
        if (!r.ok) return;
        const payload = await r.json();
        d.chains = payload.chains || [];
        d.concentration = payload.chain_concentration || {};
        d.totalSupply = payload.total_supply_current;
        d.supplyChange = payload.total_supply_change_24h_pct;
      } catch {
        // Leave dashboard values as-is; UI should render placeholder empty states.
      } finally {
        this.$store.dashboard.loading = false;
      }
    },

    _renderSupplyByChain() {
      const chains = this.chains || [];
      if (!chains.length) return;

      const sorted = [...chains]
        .sort((a, b) => Number(b.chain_share_pct || 0) - Number(a.chain_share_pct || 0))
        .slice(0, 12);

      const labels = sorted.map(c => c.chain_name);
      const supplyVals = sorted.map(c => c.supply_current || 0);

      const primary = getComputedStyle(document.documentElement).getPropertyValue('--spark').trim() || '#60a5fa';
      this._makeBar.call(this, 'chart-supply-bar', labels, supplyVals, primary, '$');
    },

    destroy() {
      if (this._didOwnCharts) this._disposeAllCharts();
      this._didOwnCharts = false;
    },
  };
}

