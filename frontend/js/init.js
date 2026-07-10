import Alpine from 'alpinejs';
import { formatUsd, formatFreshnessLabel, freshnessBandClass, formatDisplayName, depegVelocityMeta } from './utils.js';
import { registerDashboardStore } from 'stores/dashboard.js';
import { registerUiStore } from 'stores/ui.js';
import { registerOsintStore } from 'stores/osint.js';
import { registerForecastStore } from 'stores/forecast.js';
import { useGovernance } from 'composables/useGovernance.js';
import { useOSINT } from 'composables/useOSINT.js';
import { useForecast } from 'composables/useForecast.js';
import { useMarket } from 'composables/useMarket.js';
import { useMarketSupplyCharts } from 'composables/useMarketSupplyCharts.js';
import { useQuality } from 'composables/useQuality.js';
import { useHealth } from 'composables/useHealth.js';
import { useSMIDGE } from 'composables/useSMIDGE.js';
import { useOnchain } from 'composables/useOnchain.js';
import { useForensics } from 'composables/useForensics.js';
import { useAlerts } from 'composables/useAlerts.js';
import { useTags } from 'composables/useTags.js';
import { useFundamentals } from 'composables/useFundamentals.js';
import { useAnalytics } from 'composables/useAnalytics.js';
import { useTrendsDeepDive } from 'composables/useTrendsDeepDive.js';
import { useAdminOps } from 'composables/useAdminOps.js';
import { setupVisibilityDispose } from './charts.js';

// Register global infrastructure
registerDashboardStore(Alpine);
registerUiStore(Alpine);
registerOsintStore(Alpine);
registerForecastStore(Alpine);
Alpine.data('governance', useGovernance);
Alpine.data('osint', useOSINT);
Alpine.data('forecast', useForecast);
Alpine.data('market', useMarket);
Alpine.data('marketSupplyCharts', useMarketSupplyCharts);
Alpine.data('qualityDashboard', useQuality);
Alpine.data('healthDashboard', useHealth);
Alpine.data('smidgePanel', useSMIDGE);
Alpine.data('onchainPanel', useOnchain);
Alpine.data('forensics', useForensics);
Alpine.data('alertsPanel', useAlerts);
Alpine.data('tagsPanel', useTags);
Alpine.data('fundamentalsPanel', useFundamentals);
Alpine.data('analyticsPanel', useAnalytics);
Alpine.data('trendsDeepDive', useTrendsDeepDive);
Alpine.data('adminOps', useAdminOps);

// Minimal root application component
Alpine.data('helixApp', () => ({
  // Essential global state needed by template
  tab: location.hash.slice(1) || 'signal',
  theme: 'light',
  asset: 'USDT', // Needed by asset select dropdown
  searchQuery: '',
  searchResults: [],
  version: '', // Needed by footer
  refreshing: false, // Needed by refresh button
  staleWarning: '',
  rateLimitWarning: '',
  warnings: [],
  _refreshTimer: null,
  _inFlight: false,
  enabledAssets: ['USDT', 'USDC', 'DAI', 'PYUSD'],

  _refreshingStale: false,
  formatUsd,
  formatFreshnessLabel,
  freshnessBandClass,
  formatDisplayName,
  depegVelocityMeta,

  async init() {
    const root = document.documentElement;
    this.theme = root.getAttribute('data-theme') || 'light';

    const validTabs = ['signal', 'market', 'analytics', 'intel', 'forensics', 'alerts', 'system', 'settings'];
    const hashTab = location.hash.slice(1);
    this.tab = validTabs.includes(hashTab) ? hashTab : 'signal';
    this.$store.ui.tab = this.tab;

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

    try {
      const ar = await fetch('/api/assets', { cache: 'no-store' });
      if (ar.ok) {
        const list = await ar.json();
        const symbols = (list || []).map(a => a.symbol).filter(Boolean);
        if (symbols.length) {
          this.enabledAssets = symbols;
          this.$store.ui.enabledAssets = symbols;
        }
      }
    } catch {}

    // Analytics tab merged into Signal — redirect hash for one release
    if (this.tab === 'analytics') {
      this.tab = 'signal';
      this.$store.ui.tab = 'signal';
      location.hash = 'signal';
    }
    
    // Watch for tab changes — dispose charts on leave to prevent memory leaks
    let prevTab = this.tab;
    this.$watch('tab', val => {
      if (val === 'analytics') {
        this.tab = 'signal';
        this.$store.ui.tab = 'signal';
        location.hash = 'signal';
        this.$nextTick(() => document.getElementById('signal-analytics-section')?.scrollIntoView({ behavior: 'smooth' }));
        val = 'signal';
      }
      if (prevTab !== val) {
        prevTab = val;
      }
      location.hash = val;
      this.$dispatch('tab-changed', { tab: val });
    });

    // Dispose charts when page becomes hidden (Phase 3.3)
    setupVisibilityDispose();

    // Browser back/forward support — sync tab from URL hash (Phase 3.1)
    window.addEventListener('popstate', () => {
      const hashTab = location.hash.slice(1);
      if (validTabs.includes(hashTab) && hashTab !== this.tab) {
        this.tab = hashTab;
        this.$store.ui.tab = hashTab;
        this.$dispatch('tab-changed', { tab: hashTab });
      }
    });
    
    // Sync asset changes to dashboard store
    this.$watch('asset', val => this.$store.dashboard.asset = val);
    
    // Load warnings
    await this._loadWarnings();
    // Start global refresh cycle with backpressure
    this._scheduleNextRefresh();
  },

  async _loadWarnings() {
    const headers = this.$store?.ui?.adminHeaders?.() || {};
    if (!headers['X-Admin-Token']) {
      this.warnings = [];
      this.rateLimitWarning = '';
      return;
    }
    try {
      const r = await fetch('/api/ai/warnings', { cache: 'no-store', headers });
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

  _scheduleNextRefresh() {
    this._refreshTimer = setTimeout(async () => {
      if (document.hidden) return;
      if (this._inFlight) return;
      this._inFlight = true;
      try {
        this.$dispatch('global-refresh');
        await this._loadWarnings();
      } catch (e) {
        console.warn('refresh cycle failed', e);
      } finally {
        this._inFlight = false;
        this._scheduleNextRefresh();
      }
    }, 60000);
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
    if (this._refreshTimer) clearTimeout(this._refreshTimer);
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

  downloadDiagnostics() {
    const snapshot = {
      timestamp: new Date().toISOString(),
      store: {
        dashboard: Alpine.store('dashboard'),
        ui: Alpine.store('ui')
      }
    };
    const blob = new Blob(
      [JSON.stringify(snapshot, null, 2)],
      { type: 'application/json' }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `helix-diagnostics-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  },

  selectSearchResult(r) {
    this.searchQuery = '';
    this.searchResults = [];
    if (r && r.symbol) {
      this.asset = r.symbol;
      this.$dispatch('asset-changed', { asset: r.symbol });
    }
  },

}));

Alpine.start();
Alpine.store('ui').initAuthSync();
Alpine.store('ui').restoreSession();
