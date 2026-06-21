import Alpine from 'alpinejs';
import { registerDashboardStore } from 'stores/dashboard.js';
import { registerUiStore } from 'stores/ui.js';
import { registerOsintStore } from 'stores/osint.js';
import { registerForecastStore } from 'stores/forecast.js';
import { useGovernance } from 'composables/useGovernance.js';
import { useOSINT } from 'composables/useOSINT.js';
import { useForecast } from 'composables/useForecast.js';
import { useMarket } from 'composables/useMarket.js';
import { useQuality } from 'composables/useQuality.js';
import { useHealth } from 'composables/useHealth.js';

// Register global infrastructure
registerDashboardStore(Alpine);
registerUiStore(Alpine);
registerOsintStore(Alpine);
registerForecastStore(Alpine);
Alpine.data('governance', useGovernance);
Alpine.data('osint', useOSINT);
Alpine.data('forecast', useForecast);
Alpine.data('market', useMarket);
Alpine.data('qualityDashboard', useQuality);
Alpine.data('healthDashboard', useHealth);

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
  rateLimitWarning: '',
  warnings: [],
  _timer: null,
  enabledAssets: ['USDT', 'USDC', 'DAI', 'PYUSD'],
  _loadingDashboard: false,
  _refreshingStale: false,
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
      this._loadWarnings();
    }, 60000);
    
    // Watch for tab changes
    this.$watch('tab', val => location.hash = val);
    
    // Sync asset changes to dashboard store
    this.$watch('asset', val => this.$store.dashboard.asset = val);
    
    // Load warnings
    await this._loadWarnings();
  },

  async _loadWarnings() {
    try {
      const r = await fetch('/api/ai/warnings', { cache: 'no-store' });
      if (r.ok) {
        this.warnings = await r.json();
        this.rateLimitWarning = this._formatWarningBanner(this.warnings);
      }
    } catch (e) {}
  },

  _formatWarningBanner(warnings) {
    const critical = warnings.filter(w => w.severity === 'critical');
    const normal = warnings.filter(w => w.severity === 'warning');
    const parts = [];
    for (const w of critical) parts.push(`[CRITICAL] ${w.message}`);
    for (const w of normal) parts.push(`[WARN] ${w.message}`);
    return parts.join(' | ') || '';
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
  },

  loadTab() {
    // Request focused data reload from current tab component
    this.$dispatch('tab-changed', { tab: this.tab });
    // Update the UI store with the current tab
    this.$store.ui.tab = this.tab;
  },

  selectSearchResult(r) {
    this.searchQuery = '';
    this.searchResults = [];
    if (r && r.symbol) {
      this.asset = r.symbol;
      this.$dispatch('asset-changed', { asset: r.symbol });
    }
  },

  showEvidence(type) {
    this.evidenceOpen = true;
    this.evidenceTitle = type === 'score' ? 'Signal Score' : 'Peg Status';
    if (type === 'score') {
      this.evidenceFormula = 'Weighted composite of all signal components';
      this.evidenceComponents = this.$store.dashboard.signal?.components || {};
    } else if (type === 'peg') {
      this.evidenceFormula = 'Current price vs target peg';
      this.evidenceComponents = { current_price: this.$store.dashboard.depeg?.current_price || 0, peg_status: this.$store.dashboard.depeg?.peg_status || '' };
    }
    this.evidenceSources = {};
  },

  copyEvidence() {
    const text = [
      this.evidenceTitle,
      this.evidenceFormula,
      ...Object.entries(this.evidenceComponents).map(([k, v]) => `${k}: ${typeof v === 'number' ? v.toFixed(4) : v}`),
    ].join('\n');
    navigator.clipboard?.writeText(text).catch(() => {});
  },
}));

Alpine.start();
