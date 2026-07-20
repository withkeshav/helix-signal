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
  theme: 'dark',
  asset: 'USDT', // Needed by asset select dropdown
  searchQuery: '',
  searchResults: [],
  paletteOpen: false,
  paletteQuery: '',
  paletteIndex: 0,
  version: '', // Needed by footer
  staleWarning: '',
  rateLimitWarning: '',
  operationalWarning: '',
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

  get paletteItems() {
    const q = (this.paletteQuery || '').trim().toLowerCase();
    const tabs = [
      { type: 'tab', label: 'Signal', sub: 'Risk & analytics', run: () => this.goTab('signal') },
      { type: 'tab', label: 'Market', sub: 'Supply & chains', run: () => this.goTab('market') },
      { type: 'tab', label: 'Intel', sub: 'OSINT feed', run: () => this.goTab('intel') },
      { type: 'tab', label: 'Forensics', sub: 'Graph & blacklist', run: () => this.goTab('forensics') },
      { type: 'tab', label: 'Alerts', sub: 'Rules & history', run: () => this.goTab('alerts') },
      { type: 'tab', label: 'System', sub: 'Health & quality', run: () => this.goTab('system') },
      { type: 'tab', label: 'Settings', sub: 'Control Room', run: () => this.goTab('settings') },
    ];
    const settings = [
      { type: 'settings', label: 'Settings → Overview', run: () => this.goSettings('overview') },
      { type: 'settings', label: 'Settings → AI & Models', run: () => this.goSettings('ai') },
      { type: 'settings', label: 'Settings → Data & Sources', run: () => this.goSettings('data') },
      { type: 'settings', label: 'Settings → Security', run: () => this.goSettings('security') },
    ];
    const assets = (this.enabledAssets || []).map(sym => ({
      type: 'asset',
      label: sym,
      sub: 'Switch asset',
      run: () => this.switchTo(sym),
    }));
    let items = [...assets, ...tabs, ...settings];
    if (q.startsWith('0x') && q.length >= 10) {
      items.unshift({
        type: 'investigate',
        label: `Investigate ${q.slice(0, 10)}…`,
        sub: 'Forensics tab',
        run: () => this.investigateAddress(q),
      });
    }
    if (q) {
      items = items.filter(i =>
        i.label.toLowerCase().includes(q) ||
        (i.sub || '').toLowerCase().includes(q) ||
        i.type.includes(q)
      );
    }
    return items.slice(0, 12);
  },

  goTab(name) {
    this.tab = name;
    this.$store.ui.tab = name;
    location.hash = name;
    this.paletteOpen = false;
    this.paletteQuery = '';
  },

  goSettings(sub) {
    this.goTab('settings');
    this.$nextTick(() => {
      const gov = document.querySelector('#tab-settings')?._x_dataStack?.[0];
      if (gov) gov.controlSubTab = sub;
    });
  },

  investigateAddress(addr) {
    this.goTab('forensics');
    this.$nextTick(() => {
      const panel = document.querySelector('#tab-forensics')?._x_dataStack?.[0];
      if (panel) {
        panel.investigateAddress = addr;
        // Forensics composable method is investigate(), not runInvestigate
        if (typeof panel.investigate === 'function') panel.investigate();
        else if (typeof panel.runInvestigate === 'function') panel.runInvestigate();
      }
    });
  },

  openPalette() {
    this.paletteOpen = true;
    this.paletteQuery = '';
    this.paletteIndex = 0;
    this.$nextTick(() => document.getElementById('cmdk-input')?.focus());
  },

  closePalette() {
    this.paletteOpen = false;
    this.paletteQuery = '';
  },

  runPaletteItem(item) {
    if (!item?.run) return;
    item.run();
    this.closePalette();
  },

  paletteKeydown(e) {
    if (!this.paletteOpen) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      this.paletteIndex = Math.min(this.paletteIndex + 1, this.paletteItems.length - 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      this.paletteIndex = Math.max(this.paletteIndex - 1, 0);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const item = this.paletteItems[this.paletteIndex];
      if (item) this.runPaletteItem(item);
    } else if (e.key === 'Escape') {
      this.closePalette();
    }
  },

  async init() {
    const root = document.documentElement;
    const storedTheme = (() => {
      try { return localStorage.getItem('helix_theme'); } catch { return null; }
    })();
    this.theme = storedTheme || root.getAttribute('data-theme') || 'dark';
    root.setAttribute('data-theme', this.theme);
    document.body?.setAttribute('data-bs-theme', this.theme === 'light' ? 'light' : 'dark');
    this.$store.ui.setTheme(this.theme);

    // Cmd+K command palette
    document.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (this.paletteOpen) this.closePalette();
        else this.openPalette();
      }
    });

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
    
    // Watch for tab changes
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
    });

    // Instant catch-up when tab becomes visible again
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) this.$store.ui.refreshTick++;
    });

    // Browser back/forward support — sync tab from URL hash (Phase 3.1)
    window.addEventListener('popstate', () => {
      const hashTab = location.hash.slice(1);
      if (validTabs.includes(hashTab) && hashTab !== this.tab) {
        this.tab = hashTab;
        this.$store.ui.tab = hashTab;
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
      this.operationalWarning = '';
      return;
    }
    try {
      const r = await fetch('/api/ai/warnings', { cache: 'no-store', headers });
      if (r.ok) {
        this.warnings = await r.json();
        this.rateLimitWarning = this._formatWarningBanner(this.warnings);
        this.operationalWarning = this._formatOperationalBanner(this.warnings);
      }
    } catch (e) {}
  },

  _formatWarningBanner(warnings) {
    const actionable = warnings.filter(w =>
      w.severity === 'critical' && w.type !== 'source_rate_limit' && w.type !== 'ai_budget'
    );
    const normal = warnings.filter(w =>
      w.severity === 'warning' && w.type !== 'source_rate_limit' && w.type !== 'ai_budget'
    );
    const parts = [];
    for (const w of actionable) parts.push(`[CRITICAL] ${w.message}`);
    for (const w of normal) parts.push(`[WARN] ${w.message}`);
    return parts.join(' | ') || '';
  },

  _formatOperationalBanner(warnings) {
    const operational = warnings.filter(w =>
      w.type === 'source_rate_limit' || w.type === 'ai_budget'
    );
    if (operational.length === 0) return '';
    return operational.map(w => w.message).join(' | ');
  },

  _scheduleNextRefresh() {
    this._refreshTimer = setTimeout(async () => {
      this._scheduleNextRefresh();
      if (document.hidden || this._inFlight) return;
      this._inFlight = true;
      try {
        this.$store.ui.refreshTick++;
        await this._loadWarnings();
      } catch (e) {
        console.warn('refresh cycle failed', e);
      } finally {
        this._inFlight = false;
      }
    }, 60000);
  },

  async refresh() {
    this.$store.ui.beginFetch();
    try {
      this.$store.ui.refreshTick++;
      await this._loadWarnings();
    } finally {
      this.$store.ui.endFetch();
    }
  },

  cycleTheme() {
    const root = document.documentElement;
    this.theme = this.theme === 'light' ? 'dark' : 'light';
    root.setAttribute('data-theme', this.theme);
    document.body?.setAttribute('data-bs-theme', this.theme === 'light' ? 'light' : 'dark');
    try { localStorage.setItem('helix_theme', this.theme); } catch {}
    this.$store.ui.setTheme(this.theme);
  },

  destroy() {
    if (this._refreshTimer) clearTimeout(this._refreshTimer);
  },
  
  switchTo(symbol) {
    if (this.enabledAssets.includes(symbol)) {
      this.asset = symbol;
      this.$store.dashboard.asset = symbol;
      window.dispatchEvent(new CustomEvent('asset-changed', { detail: { asset: symbol } }));
    }
  },

  switchAsset() {
    this.$store.dashboard.asset = this.asset;
    window.dispatchEvent(new CustomEvent('asset-changed', { detail: { asset: this.asset } }));
  },

  loadTab() {
    this.$store.ui.tab = this.tab;
    location.hash = this.tab;
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
      this.$store.dashboard.asset = r.symbol;
    }
  },

}));

Alpine.start();
Alpine.store('ui').initAuthSync();
Alpine.store('ui').restoreSession();
