import { formatUsd } from '../utils.js';

export function useTrendsDeepDive() {
  return {
    trendsDeepDiveVisible: false,
    chainTrends: null,
    trendsLoading: false,
    trendsError: '',

    async openTrendsDeepDive() {
      this.trendsDeepDiveVisible = true;
      await this.loadChainBreakdown();
    },

    async loadChainBreakdown() {
      const asset = this.$store.dashboard.asset || this.asset || 'USDT';
      const tr = this.timeRange || '7d';
      this.trendsLoading = true;
      this.trendsError = '';
      try {
        const res = await fetch(`/api/trends/chains?asset=${asset}&window=${tr}`, { cache: 'no-store' });
        if (res.ok) {
          this.chainTrends = await res.json();
        } else {
          this.trendsError = `Chain breakdown failed (${res.status})`;
        }
      } catch (e) {
        this.trendsError = `Chain breakdown failed: ${e.message}`;
      } finally {
        this.trendsLoading = false;
      }
    },

    async exportTrendsCsv() {
      const asset = this.$store.dashboard.asset || this.asset || 'USDT';
      const tr = this.timeRange || '7d';
      try {
        const res = await fetch(`/api/trends/export?asset=${asset}&window=${tr}&format=csv`);
        if (res.ok) {
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `trends_${asset}_${tr}.csv`;
          a.click();
          URL.revokeObjectURL(url);
        } else {
          this.trendsError = `Export failed (${res.status})`;
        }
      } catch (e) {
        this.trendsError = `Export failed: ${e.message}`;
      }
    },

    fmtUsd: formatUsd,

    fmtPct(v) {
      if (v == null) return '-';
      return (v * 100).toFixed(2) + '%';
    },
  };
}