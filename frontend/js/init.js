import Alpine from 'alpinejs';
import { registerDashboardStore } from 'stores/dashboard.js';
import { registerUiStore } from 'stores/ui.js';
import { registerOsintStore } from 'stores/osint.js';
import { registerForecastStore } from 'stores/forecast.js';
import { useGovernance } from 'composables/useGovernance.js';
import { useOSINT } from 'composables/useOSINT.js';
import { useForecast } from 'composables/useForecast.js';
import { useMarket } from 'composables/useMarket.js';

// Register global infrastructure
registerDashboardStore(Alpine);
registerUiStore(Alpine);
registerOsintStore(Alpine);
registerForecastStore(Alpine);
Alpine.data('governance', useGovernance);
Alpine.data('osint', useOSINT);
Alpine.data('forecast', useForecast);
Alpine.data('market', useMarket);

// Minimal root application component
Alpine.data('helixApp', () => ({
  // Essential global state needed by template
  tab: location.hash.slice(1) || 'overview',
  theme: 'light',
  asset: 'USDT', // Needed by asset select dropdown
  searchQuery: '',
  searchResults: [],
  version: '', // Needed by footer
  refreshing: false, // Needed by refresh button
  staleWarning: '',
  _timer: null,
  _loadingDashboard: false,
  _refreshingStale: false,
  refreshing: false,
  evidenceOpen: false,
  evidenceTitle: '',
  evidenceFormula: '',
  evidenceComponents: {},
  evidenceSources: {},
  
  async init() {
    const root = document.documentElement;
    this.theme = root.getAttribute('data-theme') || 'light';
    
    // Load version from API
    try {
      const r = await fetch('/api/version', { cache: 'no-store' });
      if (r.ok) {
        const data = await r.json();
        this.version = data.version || '?';
      } else {
        this.version = '?';
      }
    } catch (e) {
      this.version = '?';
    }
    
    // Start global refresh timer
    this._timer = setInterval(() => {
      if (document.hidden) return;
      this.$dispatch('global-refresh');
    }, 60000);
    
    // Watch for tab changes
    this.$watch('tab', val => location.hash = val);
    
    // Load source usage
    await this._loadSourceUsage();
  },

  // Essential coordination methods only
  async refresh() {
    this.refreshing = true;
    this.$dispatch('refresh-requested');
    // Simulate refresh completion - components will handle actual work
    setTimeout(() => { this.refreshing = false; }, 1000);
  },

  cycleTheme() {
    const root = document.documentElement;
    this.theme = this.theme === 'light' ? 'dark' : 'light';
    root.setAttribute('data-theme', this.theme);
    this.$dispatch('theme-changed', { theme: this.theme });
  },

  search() {
    // Search coordination - let components filter results
    this.$dispatch('search-requested', { query: this.searchQuery });
  },

  destroy() {
    if (this._timer) clearInterval(this._timer);
  },
  
  switchTo(symbol) {
    // Dispatch event for components to handle asset switching
    this.$dispatch('asset-switched', { symbol });
  },

  switchAsset() {
    // Dispatch event for components to handle asset switching  
    this.$dispatch('asset-changed', { asset: this.asset });
  }
}));

Alpine.start();
