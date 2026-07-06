import { renderSmidgeRadar, destroySmidgeChart, reserveGrade } from '../charts.js';
import { statusBand, formatFeedAge } from '../utils.js';

export function useSMIDGE() {
  return {
    smidge: null,
    loadingSmidge: false,
    errorSmidge: '',
    statusBand,
    formatFeedAge,
    reserveGrade,

    get attestation() { return this.$store.osint.attestation; },

    async loadSmidge(asset) {
      const sym = asset || this.$store.dashboard.asset || 'USDT';
      this.loadingSmidge = true;
      this.errorSmidge = '';
      try {
        const r = await fetch(`/api/smidge?asset=${sym}`, { cache: 'no-store' });
        if (!r.ok) {
          this.errorSmidge = `SMIDGE HTTP ${r.status}`;
          this.smidge = null;
          return;
        }
        this.smidge = await r.json();
        this.$nextTick(() => renderSmidgeRadar.call(this, this.smidge));
      } catch (e) {
        this.errorSmidge = e.message;
        this.smidge = null;
      } finally {
        this.loadingSmidge = false;
      }
    },

    init() {
      this.$store.osint.loadAttestation();
      this.loadSmidge(this.$store.dashboard.asset);
      this.$watch('$store.dashboard.asset', (a) => this.loadSmidge(a));
      this.$watch('$store.ui.tab', (tab) => {
        if (tab !== 'intel') destroySmidgeChart.call(this);
        else if (this.smidge) this.$nextTick(() => renderSmidgeRadar.call(this, this.smidge));
      });
    },
  };
}
