import { renderSentimentChart, _disposeChart } from '../charts.js';
import { formatWhen, statusBand, formatFeedAge } from '../utils.js';

export function useOSINT() {
  return {
    _charts: new Map(),
    _echarts: new Map(),
    _disposeChart,
    formatWhen,
    statusBand,
    formatFeedAge,

    get attestation() { return this.$store.osint.attestation; },
    get osintArticles() { return this.$store.osint.osintArticles; },
    get events() { return this.$store.osint.events; },
    get loadingEvents() { return this.$store.osint.loadingEvents; },
    get errorEvents() { return this.$store.osint.errorEvents; },
    get _sentimentSeries() { return this.$store.osint._sentimentSeries; },
    get nlpAvailable() { return this.$store.dashboard.nlpAvailable; },

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
        // Load data if we're on intel tab
        const currentTab = this.$store.ui.tab || location.hash.slice(1) || 'signal';
        if (currentTab === 'intel') {
          const asset = this.$store.dashboard.asset || 'USDT';
          this.loadEvents(asset);
          this.loadAttestation();
        }

        // Initial render if data exists
        if (this._sentimentSeries.length) {
          requestAnimationFrame(() => this._renderSentiment());
        }

        // Render charts when sentiment data changes
        this.$watch('$store.osint._sentimentSeries', () => {
          if (this._sentimentSeries.length) {
            requestAnimationFrame(() => this._renderSentiment());
          }
        });

        // Re-render charts on theme change
        this.$watch('$store.ui.theme', () => {
          this.$nextTick(() => {
            if (this._sentimentSeries.length) {
              requestAnimationFrame(() => this._renderSentiment());
            }
          });
        });

        // Handle window resize + tab-switch cleanup
        const resizeHandler = () => {
          if (this._sentimentSeries.length) {
            this._renderSentiment();
          }
        };

        // Load data when tab changes to intel
        this.$watch('$store.ui.tab', (newTab) => {
          if (newTab === 'intel') {
            const asset = this.$store.dashboard.asset || 'USDT';
            this.loadEvents(asset);
            this.loadAttestation();
          }
          
          if (newTab !== 'intel') {
            this._destroyCharts();
            window.removeEventListener('resize', resizeHandler);
          } else {
            window.addEventListener('resize', resizeHandler);
          }
        });

        // Reload data when asset changes
        this.$watch('$store.dashboard.asset', (newAsset) => {
          const currentTab = this.$store.ui.tab || location.hash.slice(1) || 'signal';
          if (currentTab === 'intel') {
            this.loadEvents(newAsset);
            this.loadAttestation();
          }
        });
      });
    },
  };
}
