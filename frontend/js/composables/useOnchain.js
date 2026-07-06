/** On-chain whale flow + holder concentration (Intel tab). */

export function useOnchain() {
  return {
    whaleFlow: null,
    holderConcentration: null,
    loadingOnchain: false,
    errorOnchain: '',

    async loadOnchain(asset) {
      const sym = asset || this.$store.dashboard.asset || 'USDT';
      this.loadingOnchain = true;
      this.errorOnchain = '';
      try {
        const [whaleRes, holderRes] = await Promise.all([
          fetch(`/api/onchain/whale-flow?asset=${sym}`, { cache: 'no-store' }),
          fetch(`/api/onchain/holder-concentration?asset=${sym}`, { cache: 'no-store' }),
        ]);
        this.whaleFlow = whaleRes.ok ? await whaleRes.json() : null;
        this.holderConcentration = holderRes.ok ? await holderRes.json() : null;
        if (!whaleRes.ok && !holderRes.ok) {
          this.errorOnchain = `On-chain HTTP ${whaleRes.status}`;
        }
      } catch (e) {
        this.errorOnchain = e.message;
        this.whaleFlow = null;
        this.holderConcentration = null;
      } finally {
        this.loadingOnchain = false;
      }
    },

    onchainConfigured() {
      const w = this.whaleFlow;
      const h = this.holderConcentration;
      return Boolean(w?.configured || h?.configured || w?.available || h?.available);
    },

    onchainEmptyMessage() {
      const w = this.whaleFlow;
      const h = this.holderConcentration;
      return w?.message || h?.message || 'Configure Moralis / Flipside API keys in Settings → API Keys';
    },

    init() {
      this.loadOnchain(this.$store.dashboard.asset);
      this.$watch('$store.dashboard.asset', (a) => this.loadOnchain(a));
      this.$watch('$store.ui.tab', (tab) => {
        if (tab === 'intel') this.loadOnchain(this.$store.dashboard.asset);
      });
    },
  };
}
