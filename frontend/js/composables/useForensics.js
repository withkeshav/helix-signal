import { formatWhen, formatUsd } from '../utils.js';
import { STABLECOIN_TAXONOMY, getTypeBadge } from '../taxonomy.js';

export function useForensics() {
  return {
    // Blacklist stats
    blacklistStats: null,
    loadingStats: false,
    errorStats: '',

    // Blacklist events
    blacklistEvents: [],
    loadingEvents: false,
    errorEvents: '',
    eventsAssetFilter: '',
    eventsOffset: 0,
    eventsLimit: 20,

    // Investigation
    investigateAddress: '',
    investigateChain: 'ethereum',
    investigateAsset: 'USDT',
    investigationResult: null,
    investigating: false,
    investigateError: '',

    // Taxonomy
    taxonomySymbols: Object.keys(STABLECOIN_TAXONOMY).sort(),

    formatWhen,
    formatUsd,
    getTypeBadge,

    async loadBlacklistStats() {
      this.loadingStats = true;
      this.errorStats = '';
      try {
        const r = await fetch('/api/v1/blacklist/stats', { cache: 'no-store' });
        if (!r.ok) { this.errorStats = `HTTP ${r.status}`; return; }
        this.blacklistStats = await r.json();
      } catch (e) {
        this.errorStats = e.message;
        this.blacklistStats = null;
      } finally {
        this.loadingStats = false;
      }
    },

    async loadBlacklistEvents() {
      this.loadingEvents = true;
      this.errorEvents = '';
      try {
        let url = `/api/v1/blacklist/events?limit=${this.eventsLimit}&offset=${this.eventsOffset}`;
        if (this.eventsAssetFilter) url += `&asset=${this.eventsAssetFilter}`;
        const r = await fetch(url, { cache: 'no-store', headers: { ...(this.$store?.ui?.adminHeaders?.() || {}) } });
        if (!r.ok) { this.errorEvents = `HTTP ${r.status}`; return; }
        this.blacklistEvents = await r.json();
      } catch (e) {
        this.errorEvents = e.message;
        this.blacklistEvents = [];
      } finally {
        this.loadingEvents = false;
      }
    },

    filterEvents() {
      this.eventsOffset = 0;
      this.loadBlacklistEvents();
    },

    nextEventsPage() {
      this.eventsOffset += this.eventsLimit;
      this.loadBlacklistEvents();
    },

    prevEventsPage() {
      if (this.eventsOffset >= this.eventsLimit) {
        this.eventsOffset -= this.eventsLimit;
        this.loadBlacklistEvents();
      }
    },

    async investigate() {
      if (!this.investigateAddress) { this.investigateError = 'Enter an address'; return; }
      this.investigating = true;
      this.investigateError = '';
      this.investigationResult = null;
      try {
        const r = await fetch('/api/v1/investigate', {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            ...(this.$store?.ui?.adminHeaders?.() || {}),
          },
          body: JSON.stringify({
            address: this.investigateAddress,
            chain: this.investigateChain,
            asset: this.investigateAsset,
          }),
        });
        if (!r.ok) { this.investigateError = `HTTP ${r.status}`; return; }
        this.investigationResult = await r.json();
      } catch (e) {
        this.investigateError = e.message;
      } finally {
        this.investigating = false;
      }
    },

    init() {
      this.loadBlacklistStats();
      this.loadBlacklistEvents();
      this.$watch('$store.ui.tab', (tab) => {
        if (tab === 'forensics') {
          this.loadBlacklistStats();
          this.loadBlacklistEvents();
        }
      });
    },
  };
}
