/** Settings Control Room (v4.1.0 — kimi §7.2). */
export function useGovernance() {
  const TIER1 = {
    ai: [
      'ai_mode', 'feature_ai_summary', 'feature_ai_explain', 'feature_ai_insights',
      'feature_ai_narrative', 'feature_nlp_sentiment', 'feature_osint_feed',
      'ai_model_risk_explain', 'ai_model_market_overview', 'ai_model_market_narrative',
      'ai_model_insight_summary', 'ai_model_anomaly_investigation',
    ],
    data: [
      'refresh_core_seconds', 'refresh_osint_minutes', 'funding_rate_poll_interval_seconds',
      'retention_asset_trend_snapshots_days', 'retention_osint_articles_days',
      'retention_funding_rate_snapshots_days', 'retention_signal_events_days',
    ],
    alerts: [
      'webhook_enabled', 'webhook_url', 'webhook_min_severity',
      'blacklist_monitor_enabled', 'blacklist_poll_interval_seconds',
    ],
    security: ['api_auth_mode', 'ai_require_token'],
  };

  const ADVANCED_ALLOWLIST = new Set([
    'feature_multi_user', 'feature_onchain_signals', 'anomaly_std_floor',
    'ai_cache_enabled', 'ai_cache_ttl_seconds', 'semantic_cache_enabled',
    'retention_chain_trend_snapshots_days', 'retention_yield_bearing_snapshots_days',
    'retention_collateral_snapshots_days', 'retention_whale_activity_snapshots_days',
    'retention_forecast_runs_days', 'retention_ai_narrative_history_days',
    'retention_settings_audit_log_days', 'retention_source_usage_days', 'retention_ai_usage_days',
    'retention_fred_yields_days', 'retention_fiat_reserve_snapshots_days',
    'webhook_timeout_seconds', 'external_intel_webhook_enabled',
  ]);

  return {
    settingsList: [],
    settingsError: '',
    controlSubTab: 'overview',
    controlSubTabs: [
      { id: 'overview', label: 'Overview' },
      { id: 'ai', label: 'AI & Models' },
      { id: 'data', label: 'Data & Sources' },
      { id: 'alerts', label: 'Alerts & Notify' },
      { id: 'security', label: 'Security' },
      { id: 'advanced', label: 'Advanced' },
    ],

    opsStatus: null,
    qualitySummary: null,
    auditTail: [],
    apiKeys: [],
    newApiKeyName: '',
    createdApiKeyRaw: '',
    advancedSearch: '',
    advancedDirty: {},
    advancedSaving: false,

    playbookLoading: null,
    playbooks: [
      { name: 'max_free', label: 'Off / Minimal', is_builtin: true },
      { name: 'balanced', label: 'Lite (balanced)', is_builtin: true },
      { name: 'quality', label: 'Full (quality)', is_builtin: true },
    ],

    toastMessage: '',
    toastType: '',
    toastVisible: false,
    toastTimer: null,

    setupDone: typeof localStorage !== 'undefined' && localStorage.getItem('helix_setup_done') === '1',
    wizardStep: 1,
    wizardPlaybook: 'balanced',
    wizardFeatures: {
      feature_ai_summary: true,
      feature_ai_explain: true,
      feature_ai_insights: true,
      feature_ai_narrative: true,
      feature_nlp_sentiment: false,
      feature_osint_feed: true,
    },
    testAiLoading: false,
    testAiResult: '',
    providerTestLoading: false,
    providerTestResult: '',
    assetCatalog: [],
    assetCatalogLoading: false,

    aiFeatureMap: [
      { ui: 'Risk explanation', tab: 'Signal → Risk Terminal', toggle: 'feature_ai_explain', kind: 'LLM', effectTab: 'signal', effectSelector: '#chart-risk-terminal' },
      { ui: 'Market overview', tab: 'Signal → Overview', toggle: 'feature_ai_summary', kind: 'LLM', effectTab: 'signal', effectAiSubTab: 'overview', effectSelector: '#signal-ai-overview' },
      { ui: 'Market narrative', tab: 'Signal → Narrative', toggle: 'feature_ai_narrative', kind: 'LLM', effectTab: 'signal', effectAiSubTab: 'narrative', effectSelector: '#signal-ai-narrative' },
      { ui: 'Insights', tab: 'Signal → Insights', toggle: 'feature_ai_insights', kind: 'LLM', effectTab: 'signal', effectAiSubTab: 'insights', effectSelector: '#signal-ai-insights' },
      { ui: 'OSINT sentiment', tab: 'Intel', toggle: 'feature_nlp_sentiment', kind: 'LLM', effectTab: 'intel', effectSelector: '#chart-sentiment' },
      { ui: 'Predictive regime', tab: 'Signal → Risk Terminal', toggle: '—', kind: 'Statistical', effectTab: 'signal', effectSelector: '#chart-risk-terminal' },
      { ui: 'DEWS score', tab: 'Signal', toggle: '—', kind: 'Statistical', effectTab: 'signal', effectSelector: '#chart-risk-terminal' },
    ],

    _toBool(v) {
      return v === true || v === 'true' || v === 1 || v === '1';
    },

    tier1Settings(group) {
      const keys = TIER1[group] || [];
      return keys
        .map(k => this.settingsList.find(s => s.key === k))
        .filter(Boolean);
    },

    get advancedSettings() {
      const tier1 = new Set(Object.values(TIER1).flat());
      const q = (this.advancedSearch || '').trim().toLowerCase();
      return (this.settingsList || []).filter(s => {
        if (!s?.key || tier1.has(s.key) || s.type === 'secret') return false;
        if (!ADVANCED_ALLOWLIST.has(s.key)) return false;
        if (!q) return true;
        return s.key.toLowerCase().includes(q)
          || (s.label || '').toLowerCase().includes(q)
          || (s.description || '').toLowerCase().includes(q);
      });
    },

    get advancedDirtyCount() {
      return Object.keys(this.advancedDirty).length;
    },

    markAdvancedDirty(key, value) {
      this.advancedDirty = { ...this.advancedDirty, [key]: value };
    },

    async saveAdvancedDirty() {
      if (!this.adminToken || !this.advancedDirtyCount) return;
      this.advancedSaving = true;
      try {
        for (const [key, value] of Object.entries(this.advancedDirty)) {
          await this.toggleSetting(key, value);
        }
        this.advancedDirty = {};
        this.showToast('Advanced settings saved', 'success');
        await this.loadSettings();
      } catch (e) {
        this.showToast(e.message, 'error');
      } finally {
        this.advancedSaving = false;
      }
    },

    settingInputType(s) {
      if (!s) return 'text';
      if (s.type === 'bool') return 'checkbox';
      if (s.type === 'int') return 'number';
      if (s.type === 'enum') return 'select';
      return 'text';
    },

    async loadOpsStatus() {
      if (!this.adminToken) return;
      try {
        const [opsR, dqR, auditR] = await Promise.all([
          this._adminFetch('/api/settings/ops', { cache: 'no-store' }),
          fetch('/api/data-quality/summary', { cache: 'no-store' }),
          this._adminFetch('/api/settings/audit/recent?limit=8', { cache: 'no-store' }),
        ]);
        if (opsR.ok) this.opsStatus = await opsR.json();
        if (dqR.ok) this.qualitySummary = await dqR.json();
        if (auditR.ok) this.auditTail = await auditR.json();
      } catch {
        /* ignore */
      }
    },

    async loadApiKeys() {
      if (!this.adminToken) return;
      try {
        const r = await this._adminFetch('/api/v1/api-keys', { cache: 'no-store' });
        if (r.ok) this.apiKeys = await r.json();
      } catch {
        this.apiKeys = [];
      }
    },

    async createApiKey() {
      if (!this.newApiKeyName.trim()) {
        this.showToast('Key name required', 'error');
        return;
      }
      try {
        const r = await this._adminFetch('/api/v1/api-keys', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: this.newApiKeyName.trim() }),
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.detail || 'Create failed');
        this.createdApiKeyRaw = j.api_key || '';
        this.newApiKeyName = '';
        await this.loadApiKeys();
        this.showToast('API key created — copy it now', 'success');
      } catch (e) {
        this.showToast(e.message, 'error');
      }
    },

    async revokeApiKey(id) {
      try {
        const r = await this._adminFetch(`/api/v1/api-keys/${id}`, { method: 'DELETE' });
        if (!r.ok) throw new Error('Revoke failed');
        await this.loadApiKeys();
        this.showToast('API key revoked', 'success');
      } catch (e) {
        this.showToast(e.message, 'error');
      }
    },

    async rotateSecretKey(key) {
      const newVal = prompt(`Paste new value for ${key} (masked in UI after save):`);
      if (newVal == null || !newVal.trim()) return;
      try {
        await this.toggleSetting(key, newVal.trim());
        this.showToast(`${key} rotated`, 'success');
        await this.loadSettings();
      } catch (e) {
        this.showToast(e.message, 'error');
      }
    },

    qualitySparkline() {
      const hist = this.qualitySummary?.history || [];
      if (!hist.length) return '';
      const vals = hist.map(h => h.overall_score).reverse();
      const max = Math.max(...vals, 1);
      return vals.map(v => Math.round((v / max) * 8)).join(',');
    },

    isFeatureEnabled(toggleKey) {
      if (!toggleKey || toggleKey === '—') return null;
      const s = this.settingsList?.find(x => x.key === toggleKey);
      if (!s) return null;
      return this._toBool(s.value);
    },

    async _scrollToSelector(selector, { timeoutMs = 2500 } = {}) {
      const start = Date.now();
      while (Date.now() - start < timeoutMs) {
        const el = document.querySelector(selector);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
          return true;
        }
        await new Promise(r => setTimeout(r, 50));
      }
      return false;
    },

    async navigateAiEffect(row) {
      if (!row?.effectSelector) return;
      const destTab = row.effectTab;
      if (destTab && destTab !== this.$store.ui.tab) {
        this.$store.ui.setTab(destTab);
      }
      if (row.effectAiSubTab && destTab === 'signal') {
        await new Promise(r => setTimeout(r, 60));
        window.dispatchEvent(new CustomEvent('ai-subtab-set', { detail: { subtab: row.effectAiSubTab } }));
      }
      await this._scrollToSelector(row.effectSelector);
    },

    openAdminPanel() {
      window.open('/admin', '_blank', 'noopener,noreferrer');
    },

    _syncWizardFeaturesFromSettings() {
      if (!this.settingsList) return;
      for (const key of Object.keys(this.wizardFeatures || {})) {
        const s = this.settingsList.find(x => x.key === key);
        if (s) this.wizardFeatures[key] = this._toBool(s.value);
      }
    },

    get aiModeLabel() {
      const s = this.settingsList.find(x => x.key === 'ai_mode');
      const mode = s?.value || 'ai_off';
      if (mode === 'ai_full') return 'Full';
      if (mode === 'ai_lite') return 'Lite';
      return 'Off';
    },

    get authModeLabel() {
      const s = this.settingsList.find(x => x.key === 'api_auth_mode');
      return s?.value || 'open';
    },

    get adminToken() {
      return this.$store.ui.adminToken;
    },

    async runTestAi() {
      this.testAiLoading = true;
      this.testAiResult = '';
      try {
        const r = await this.$store.ui.adminFetch('/api/ai/narrative?asset=USDT', { cache: 'no-store' });
        const j = await r.json();
        if (r.ok && j.available) {
          this.testAiResult = `OK: ${(j.summary || '').slice(0, 120)}...`;
        } else {
          this.testAiResult = j.reason || j.detail || `HTTP ${r.status}`;
        }
      } catch (e) {
        this.testAiResult = e.message;
      } finally {
        this.testAiLoading = false;
      }
    },

    async runProviderTest() {
      this.providerTestLoading = true;
      this.providerTestResult = '';
      try {
        const r = await this._adminFetch('/api/ai/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        const j = await r.json().catch(() => ({}));
        if (r.ok) {
          this.providerTestResult = j.message || j.status || JSON.stringify(j).slice(0, 160);
        } else {
          this.providerTestResult = j.detail || j.message || `HTTP ${r.status}`;
        }
      } catch (e) {
        this.providerTestResult = e.message;
      } finally {
        this.providerTestLoading = false;
      }
    },

    async wizardApplyAiMode() {
      const pb = this.wizardPlaybook || 'balanced';
      await this.applyPlaybook(pb);
      this._syncWizardFeaturesFromSettings();
      this.wizardStep = 2;
    },

    async wizardApplyFeatures() {
      if (!this.adminToken) {
        this.settingsError = 'Sign in to save feature toggles';
        return;
      }
      for (const [key, val] of Object.entries(this.wizardFeatures)) {
        const s = this.settingsList.find(x => x.key === key);
        if (s) await this.toggleSetting(key, val);
      }
      try { localStorage.setItem('helix_setup_done', '1'); } catch {}
      this.setupDone = true;
      this.wizardStep = 3;
      this.showToast('Quick Setup complete', 'success');
    },

    async loadAssetCatalog() {
      if (!this.adminToken) return;
      this.assetCatalogLoading = true;
      try {
        const r = await this._adminFetch('/api/assets/catalog', { cache: 'no-store' });
        if (r.ok) this.assetCatalog = await r.json();
      } catch {
        /* ignore */
      } finally {
        this.assetCatalogLoading = false;
      }
    },

    async toggleAssetEnabled(row) {
      if (!this.adminToken || !row?.symbol) return;
      const next = !row.enabled;
      try {
        const r = await this._adminFetch(`/api/assets/${encodeURIComponent(row.symbol)}/enabled`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: next }),
        });
        if (r.ok) {
          row.enabled = next;
          this.showToast(`${row.symbol} ${next ? 'enabled' : 'disabled'}`, 'success');
        } else {
          const j = await r.json().catch(() => ({}));
          this.showToast(j.detail || `Failed to update ${row.symbol}`, 'error');
        }
      } catch (e) {
        this.showToast(e.message, 'error');
      }
    },

    _adminHeaders(extra = {}) {
      return this.$store.ui.adminHeaders(extra);
    },

    async _adminFetch(path, opts = {}) {
      return this.$store.ui.adminFetch(path, opts);
    },

    async submitAdminLogin() {
      this.settingsError = '';
      try {
        await this.$store.ui.login();
        if (this.$store.ui.adminToken) {
          await this.loadSettings();
          await this.loadPlaybooks();
          await this.loadAssetCatalog();
          await this.loadOpsStatus();
          await this.loadApiKeys();
        }
      } catch (e) {
        this.settingsError = e.message || 'Login failed';
      }
    },

    showToast(message, type = 'info') {
      this.toastMessage = message;
      this.toastType = type;
      this.toastVisible = true;
      if (this.toastTimer) clearTimeout(this.toastTimer);
      this.toastTimer = setTimeout(() => { this.toastVisible = false; }, 3500);
    },

    async applyPlaybook(name) {
      if (!this.adminToken || !name) return;
      this.playbookLoading = name;
      try {
        const r = await this._adminFetch(`/api/ai/playbook/${encodeURIComponent(name)}`, { method: 'POST' });
        const j = await r.json().catch(() => ({}));
        if (r.ok) {
          this.showToast(`Applied playbook: ${name}`, 'success');
          await this.loadSettings();
        } else {
          this.showToast(j.detail || `Playbook failed (${r.status})`, 'error');
        }
      } catch (e) {
        this.showToast(e.message, 'error');
      } finally {
        this.playbookLoading = null;
      }
    },

    async loadPlaybooks() {
      if (!this.adminToken) return;
      try {
        const r = await this._adminFetch('/api/playbooks', { cache: 'no-store' });
        if (r.ok) {
          const rows = await r.json();
          if (Array.isArray(rows) && rows.length) this.playbooks = rows;
        }
      } catch {
        /* keep built-in defaults */
      }
    },

    async loadSettings() {
      if (!this.adminToken) return;
      try {
        const r = await this._adminFetch('/api/settings', { cache: 'no-store' });
        if (r.ok) {
          this.settingsList = await r.json();
          this._syncWizardFeaturesFromSettings();
        }
      } catch (e) {
        this.settingsError = e.message;
      }
    },

    async toggleSetting(key, value) {
      const r = await this._adminFetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, value }),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j.detail || `Failed to update ${key}`);
      }
      const s = this.settingsList.find(x => x.key === key);
      if (s) s.value = value;
      window.dispatchEvent(new CustomEvent('settings-changed'));
    },

    async onTier1Change(s, event) {
      if (!s) return;
      let val = event?.target?.value;
      if (s.type === 'bool') val = event.target.checked;
      if (s.type === 'int') val = parseInt(val, 10);
      try {
        await this.toggleSetting(s.key, val);
        this.showToast(`${s.label || s.key} updated`, 'success');
      } catch (e) {
        this.showToast(e.message, 'error');
      }
    },

    async exportSettings() {
      try {
        const r = await this._adminFetch('/api/settings/export/json', { cache: 'no-store' });
        const j = await r.json();
        if (!r.ok) throw new Error(j.detail || 'Export failed');
        const blob = new Blob([j.content || JSON.stringify(j)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = j.filename || 'helix-settings.json';
        a.click();
        URL.revokeObjectURL(a.href);
        this.showToast('Settings exported', 'success');
      } catch (e) {
        this.showToast(e.message, 'error');
      }
    },

    triggerImport() {
      this.$refs?.settingsImportInput?.click();
    },

    async importSettings(event) {
      const file = event?.target?.files?.[0];
      if (!file) return;
      try {
        const fd = new FormData();
        fd.append('file', file);
        const r = await this._adminFetch('/api/settings/import/json', { method: 'POST', body: fd });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.detail || 'Import failed');
        this.showToast(`Imported ${j.imported ?? '?'} settings`, 'success');
        await this.loadSettings();
      } catch (e) {
        this.showToast(e.message, 'error');
      } finally {
        if (event?.target) event.target.value = '';
      }
    },
  };
}
