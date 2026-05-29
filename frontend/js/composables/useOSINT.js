import { renderSentimentChart, _disposeChart } from '../charts.js';

export function useOSINT() {
  return {
    _charts: new Map(),
    _echarts: new Map(),
    _disposeChart,

    get attestation() { return this.$store.osint.attestation; },
    get osintArticles() { return this.$store.osint.osintArticles; },
    get events() { return this.$store.osint.events; },
    get loadingEvents() { return this.$store.osint.loadingEvents; },
    get errorEvents() { return this.$store.osint.errorEvents; },
    get _sentimentSeries() { return this.$store.osint._sentimentSeries; },

    async loadAttestation() {
      await this.$store.osint.loadAttestation();
    },

    async loadEvents(asset) {
      await this.$store.osint.loadEvents(asset);
    },

    _renderSentiment() {
      if (!this._sentimentSeries.length) return;
      renderSentimentChart.call(this, this._sentimentSeries);
    },

    _destroyCharts() {
      for (const [, c] of this._charts) this._disposeChart(c);
      this._charts.clear();
      for (const [, c] of this._echarts) this._disposeChart(c);
      this._echarts.clear();
    },

    init() {
      this.$nextTick(() => {
        // Render charts when sentiment data changes
        Alpine.effect(() => {
          const series = this._sentimentSeries;
          if (series.length) {
            requestAnimationFrame(() => this._renderSentiment());
          }
        });
        
        // Re-render charts on theme change
        Alpine.effect(() => {
          Alpine.store('ui').theme;
          if (this._sentimentSeries.length) {
            requestAnimationFrame(() => this._renderSentiment());
          }
        });
        
        // Clean up charts when switching away from tab
        this.$watch('$store.ui.tab', (newTab) => {
          if (newTab !== 'events' && newTab !== 'intel') {
            this._destroyCharts();
          }
        });
        
        // Handle window resize
        const resizeHandler = () => {
          if (this._sentimentSeries.length) {
            this._renderSentiment();
          }
        };
        window.addEventListener('resize', resizeHandler);
        // Clean up resize handler when component is destroyed
        this.$watch('$store.ui.tab', (newTab) => {
          if (newTab !== 'events' && newTab !== 'intel') {
            window.removeEventListener('resize', resizeHandler);
          }
        });
      });
    },
  };
}
