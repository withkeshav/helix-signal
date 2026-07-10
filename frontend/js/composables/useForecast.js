import { renderForecastCharts, destroyForecastCharts, _disposeChart, _renderForecastChartsImpl, _renderForecastCanvas, renderContagionGraph, resizeAllHelixCharts } from '../charts.js';

export function useForecast() {
  return {
    _charts: new Map(),
    _echarts: new Map(),
    _disposeChart,
    _renderForecastChartsImpl,
    _renderForecastCanvas,
    renderContagionGraph,
    resizeAllHelixCharts,

    get forecastSignals() { return this.$store.forecast.forecastSignals; },
    get correlations() { return this.$store.forecast.correlations; },
    get forecastAccuracy() { return this.$store.forecast.forecastAccuracy; },
    get refreshingForecast() { return this.$store.forecast.refreshingForecast; },
    get refreshingCorrelations() { return this.$store.forecast.refreshingCorrelations; },
    get loadingForecast() { return this.$store.forecast.loadingForecast; },
    get errorForecast() { return this.$store.forecast.errorForecast; },
    get _forecastData() { return this.$store.forecast._forecastData; },

    async loadForecastData(asset) {
      await this.$store.forecast.loadForecastData(asset);
      this._renderForecastCharts();
    },

    async loadForecastAccuracy(asset) {
      await this.$store.forecast.loadForecastAccuracy(asset);
    },

    _renderForecastCharts() {
      if (this._forecastData) {
        renderForecastCharts.call(this);
      }
    },

    _destroyCharts() {
      for (const [, c] of this._charts) this._disposeChart(c);
      this._charts.clear();
      for (const [, c] of this._echarts) this._disposeChart(c);
      this._echarts.clear();
    },

    init() {
      this.$nextTick(() => {
        // Load data if we're on forecast tab
        const currentTab = this.$store.ui.tab || location.hash.slice(1) || 'signal';
        if (currentTab === 'market') {
          const asset = this.$store.dashboard.asset || 'USDT';
          this.loadForecastData(asset);
          this.loadForecastAccuracy(asset);
        }

        // Initial render if data exists
        if (this._forecastData) {
          requestAnimationFrame(() => this._renderForecastCharts());
        }

        // Render charts when forecast data changes
        this.$watch('$store.forecast._forecastData', () => {
          if (this._forecastData) {
            requestAnimationFrame(() => this._renderForecastCharts());
          }
        });

        // Re-render charts on theme change
        this.$watch('$store.ui.theme', () => {
          this.$nextTick(() => {
            if (this._forecastData) {
              requestAnimationFrame(() => this._renderForecastCharts());
            }
          });
        });

        // Clean up charts when switching away from tab
        this.$watch('$store.ui.tab', (newTab) => {
          if (newTab !== 'market') {
            this._destroyCharts();
          } else {
            const asset = this.$store.dashboard.asset || 'USDT';
            this.loadForecastData(asset);
            this.loadForecastAccuracy(asset);
            this.$nextTick(() => {
              this.renderContagionGraph(this.$store.dashboard.rotation);
              this.resizeAllHelixCharts();
            });
          }
        });

        // Reload data when asset changes
        this.$watch('$store.dashboard.asset', (newAsset) => {
          const currentTab = this.$store.ui.tab || location.hash.slice(1) || 'signal';
          if (currentTab === 'market') {
            this.loadForecastData(newAsset);
            this.loadForecastAccuracy(newAsset);
          }
        });
      });
    },

    destroy() {
      // Alpine x-if unmount: clean up ECharts instances created here.
      this._destroyCharts();
    },
  };
}
