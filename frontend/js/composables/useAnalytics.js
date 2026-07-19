export function useAnalytics() {
  return {
    regime: null,
    changePoints: null,
    crossAssetMatrix: null,
    analyticsLoading: false,
    analyticsError: '',
    analyticsAsset: '',
    regimeWindowHours: 48,
    cpWindowDays: 14,
    matrixWindowDays: 7,

    async init() {
      this.analyticsAsset = this.$store.dashboard.asset || 'USDT';
      await this.loadAllAnalytics();
      this.$watch('$store.ui.refreshTick', () => {
        if (this.$store.ui.tab === 'signal') this.loadAllAnalytics();
      });
    },

    async loadAllAnalytics() {
      this.analyticsLoading = true;
      this.analyticsError = '';
      const failures = [];
      const asset = this.analyticsAsset;
      try {
        const [regimeRes, cpRes, matrixRes] = await Promise.all([
          fetch(`/api/analytics/regime?asset=${asset}&window_hours=${this.regimeWindowHours}`, { cache: 'no-store' }).catch(() => null),
          fetch(`/api/anomaly/change-points?asset=${asset}&window_days=${this.cpWindowDays}`, { cache: 'no-store' }).catch(() => null),
          fetch(`/api/analytics/cross-asset-matrix?window_days=${this.matrixWindowDays}`, { cache: 'no-store' }).catch(() => null),
        ]);
        if (regimeRes && regimeRes.ok) this.regime = await regimeRes.json();
        else if (regimeRes) failures.push(`regime (${regimeRes.status})`);
        if (cpRes && cpRes.ok) this.changePoints = await cpRes.json();
        else if (cpRes) failures.push(`change-points (${cpRes.status})`);
        if (matrixRes && matrixRes.ok) this.crossAssetMatrix = await matrixRes.json();
        else if (matrixRes) failures.push(`cross-asset (${matrixRes.status})`);
        if (failures.length) this.analyticsError = `Failed: ${failures.join(', ')}`;
      } catch (e) {
        this.analyticsError = `Failed to load analytics: ${e.message}`;
      } finally {
        this.analyticsLoading = false;
      }
    },

    async reloadForAsset(symbol) {
      this.analyticsAsset = symbol;
      await this.loadAllAnalytics();
    },

    regimeColor(state) {
      const s = (state || '').toLowerCase();
      if (s === 'crisis') return 'badge-critical';
      if (s === 'elevated') return 'badge-warning';
      return 'badge-info';
    },

    fmtNum(v, digits = 2) {
      if (v == null) return '-';
      return Number(v).toFixed(digits);
    },
  };
}