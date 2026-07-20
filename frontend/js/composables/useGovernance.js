/** Settings Control Room (v4.1.0 — kimi §7.2). */
export function useGovernance() {
  const AI_MODEL_FEATURES = [
    { key: 'ai_model_risk_explain', label: 'Risk explain' },
    { key: 'ai_model_market_overview', label: 'Market overview (Insight tab)' },
    { key: 'ai_model_market_narrative', label: 'Market narrative' },
    { key: 'ai_model_insight_summary', label: 'Insights summary' },
    { key: 'ai_model_anomaly_investigation', label: 'Anomaly investigation' },
  ];

  const TIER1 = {
    ai: [
      'ai_mode', 'ai_fallback_provider', 'ai_fallback_model',
      'ai_default_fallback_provider', 'ai_default_fallback_model_id',
      'feature_ai_summary', 'feature_ai_explain', 'feature_ai_insights',
      'feature_ai_narrative', 'feature_nlp_sentiment', 'feature_osint_feed',
    ],
    data: [
      'retention_preset', 'anomaly_sensitivity',
      'refresh_core_seconds', 'refresh_osint_minutes', 'funding_rate_poll_interval_seconds',
      'retention_asset_trend_snapshots_days', 'retention_osint_articles_days',
      'retention_funding_rate_snapshots_days', 'retention_signal_events_days',
    ],
    alerts: [
      'webhook_enabled', 'webhook_url', 'webhook_min_severity',
      'alert_email_enabled', 'alert_email_to', 'alert_email_from',
      'alert_smtp_host', 'alert_smtp_port', 'alert_smtp_user',
      'alert_email_min_severity', 'alert_email_event_types',
      'blacklist_monitor_enabled', 'blacklist_poll_interval_seconds',
    ],
    security: ['api_auth_mode', 'ai_require_token'],
    display: [
      'public_history_hours', 'public_tabs_enabled', 'public_export_enabled',
      'public_show_forensics', 'public_deterministic_why',
      'demo_mode_enabled', 'demo_history_hours', 'demo_mode_until',
      'intelligence_api_enabled',
    ],
  };

  const ADVANCED_ALLOWLIST = new Set([
    // Single-operator product — no multi-user settings
    'feature_onchain_signals', 'provider_moralis', 'provider_thegraph', 'provider_flipside',
    'anomaly_std_floor', 'onchain_whale_threshold_usd',
    // Real cache keys used by ai_router / playbooks (not legacy ai_cache_enabled)
    'ai_cache_semantic_enabled', 'ai_cache_semantic_threshold',
    'ai_cache_ttl_seconds', 'ai_cache_ttl_market_narrative',
    'ai_cache_max_entries', 'ai_cache_max_semantic_entries',
    'retention_chain_trend_snapshots_days', 'retention_yield_bearing_snapshots_days',
    'retention_collateral_snapshots_days', 'retention_whale_activity_snapshots_days',
    'retention_forecast_runs_days', 'retention_ai_narrative_history_days',
    'retention_web_search_snapshots_days',
    'retention_settings_audit_log_days', 'retention_source_usage_days', 'retention_ai_usage_days',
    'retention_fred_yields_days', 'retention_fiat_reserve_snapshots_days',
    'webhook_timeout_seconds', 'external_intel_webhook_enabled',
    'ethena_enabled', 'sky_protocol_enabled', 'coinglass_enabled', 'aave_enabled',
    'ondo_enabled', 'liquity_enabled',
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
      { id: 'display', label: 'Display & Access' },
      { id: 'security', label: 'Security' },
      { id: 'advanced', label: 'Advanced' },
    ],

    aiModelFeatures: AI_MODEL_FEATURES,
    modelCatalog: { ollama_cloud: [], openrouter: [] },
    modelCatalogLoading: false,
    modelCatalogError: '',

    opsStatus: null,
    qualitySummary: null,
    auditTail: [],
    apiKeys: [],
    newApiKeyName: '',
    createdApiKeyRaw: '',
    newApiKeyBundles: ['core:read'],
    newApiKeyAssets: '',
    newApiKeyHistoryHours: '',
    apiKeyBundles: [
      'core:read', 'trends:read', 'events:read', 'osint:read', 'risk:read',
      'forensics:read', 'export:read', 'investigate:write', 'admin',
    ],
    webhookEndpoints: [],
    alertEventCatalog: [],
    newWebhook: { name: '', url: '', signing_secret: '', min_severity: 'warning', event_types: [] },
    aiProviders: [],
    webSearchStatus: null,
    aiHealth: null,
    advancedSearch: '',
    advancedDirty: {},
    advancedSaving: false,

    playbookLoading: null,
    playbooks: [
      { name: 'max_free', label: 'Off / Minimal', is_builtin: true },
      { name: 'balanced', label: 'Lite (balanced)', is_builtin: true },
      { name: 'quality', label: 'Full (quality)', is_builtin: true },
      { name: 'public_demo', label: 'Public demo', is_builtin: true },
      { name: 'data_hoarder', label: 'Data hoarder', is_builtin: true },
    ],

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

    async initControlRoom() {
      await Promise.all([
        this.loadSettings(),
        this.loadPlaybooks(),
        this.loadAssetCatalog(),
      ]);
      // Bridge: open sub-tab requested via goSettings() without Alpine internals
      const sub = this.$store?.ui?.controlSubTabRequest;
      if (sub) {
        this.controlSubTab = sub;
        this.$store.ui.controlSubTabRequest = '';
      }
      this.$watch('$store.ui.controlSubTabRequest', (v) => {
        if (v) {
          this.controlSubTab = v;
          this.$store.ui.controlSubTabRequest = '';
        }
      });
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
      const bundles = (this.newApiKeyBundles || []).filter(Boolean);
      const assets = (this.newApiKeyAssets || '').split(/[,\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean);
      const maxH = parseInt(this.newApiKeyHistoryHours, 10);
      const access_policy = {
        allowed_bundles: bundles.length ? bundles : ['core:read'],
        allowed_assets: assets,
        max_history_hours: Number.isFinite(maxH) && maxH > 0 ? maxH : null,
      };
      try {
        const r = await this._adminFetch('/api/v1/api-keys', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: this.newApiKeyName.trim(),
            scopes: access_policy.allowed_bundles,
            access_policy,
          }),
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

    toggleNewKeyBundle(bundle) {
      const set = new Set(this.newApiKeyBundles || []);
      if (set.has(bundle)) set.delete(bundle);
      else set.add(bundle);
      this.newApiKeyBundles = [...set];
    },

    async loadWebhookEndpoints() {
      if (!this.adminToken) return;
      try {
        const [epR, catR] = await Promise.all([
          this._adminFetch('/api/v1/webhook-endpoints', { cache: 'no-store' }),
          this._adminFetch('/api/v1/alert-event-catalog', { cache: 'no-store' }),
        ]);
        if (epR.ok) this.webhookEndpoints = await epR.json();
        if (catR.ok) this.alertEventCatalog = await catR.json();
      } catch {
        this.webhookEndpoints = [];
      }
    },

    async createWebhookEndpoint() {
      const body = {
        name: (this.newWebhook.name || '').trim(),
        url: (this.newWebhook.url || '').trim(),
        signing_secret: (this.newWebhook.signing_secret || '').trim(),
        min_severity: this.newWebhook.min_severity || 'warning',
        event_types: this.newWebhook.event_types || [],
      };
      if (!body.name || !body.url || body.signing_secret.length < 8) {
        this.showToast('Name, URL, and signing secret (8+) required', 'error');
        return;
      }
      try {
        const r = await this._adminFetch('/api/v1/webhook-endpoints', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.detail || 'Create failed');
        this.newWebhook = { name: '', url: '', signing_secret: '', min_severity: 'warning', event_types: [] };
        await this.loadWebhookEndpoints();
        this.showToast('Webhook endpoint created', 'success');
      } catch (e) {
        this.showToast(e.message, 'error');
      }
    },

    async testWebhookEndpoint(id) {
      try {
        const r = await this._adminFetch(`/api/v1/webhook-endpoints/${id}/test`, { method: 'POST' });
        const j = await r.json();
        if (!r.ok) throw new Error(j.detail || 'Test failed');
        this.showToast(j.dispatched ? 'Webhook delivered' : `Not delivered: ${j.reason}`, j.dispatched ? 'success' : 'error');
      } catch (e) {
        this.showToast(e.message, 'error');
      }
    },

    async deleteWebhookEndpoint(id) {
      try {
        const r = await this._adminFetch(`/api/v1/webhook-endpoints/${id}`, { method: 'DELETE' });
        if (!r.ok) throw new Error('Delete failed');
        await this.loadWebhookEndpoints();
        this.showToast('Endpoint deleted', 'success');
      } catch (e) {
        this.showToast(e.message, 'error');
      }
    },

    async sendTestEmail() {
      try {
        const r = await this._adminFetch('/api/v1/alerts/test-email', { method: 'POST' });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.detail || 'Test email failed');
        this.showToast(`Test email sent to ${j.to}`, 'success');
      } catch (e) {
        this.showToast(e.message, 'error');
      }
    },

    async loadAiProviders() {
      if (!this.adminToken) return;
      try {
        const r = await this._adminFetch('/api/v1/ai-providers', { cache: 'no-store' });
        if (r.ok) this.aiProviders = await r.json();
      } catch {
        this.aiProviders = [];
      }
    },

    async loadWebSearchStatus() {
      if (!this.adminToken) return;
      try {
        const r = await this._adminFetch('/api/settings/web-search-status', { cache: 'no-store' });
        if (r.ok) this.webSearchStatus = await r.json();
      } catch {
        this.webSearchStatus = null;
      }
    },

    async runWebSearchNow() {
      try {
        const r = await this._adminFetch('/api/settings/web-search/run', { method: 'POST' });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.detail || 'Web search run failed');
        this.showToast(`Web search: ${j.status || 'ok'}`, 'success');
        await this.loadWebSearchStatus();
      } catch (e) {
        this.showToast(e.message, 'error');
      }
    },

    async loadAiHealth() {
      if (!this.adminToken) return;
      try {
        const r = await this._adminFetch('/api/settings/ai-health', { cache: 'no-store' });
        if (r.ok) this.aiHealth = await r.json();
      } catch {
        this.aiHealth = null;
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
      let label = 'Off';
      if (mode === 'ai_full') label = 'Full';
      else if (mode === 'ai_lite') label = 'Lite';
      // Keep nav badge in sync (badge reads $store.ui.aiModeLabel, not this getter)
      if (this.$store?.ui && this.$store.ui.aiModeLabel !== label) {
        this.$store.ui.aiModeLabel = label;
      }
      return label;
    },

    get authModeLabel() {
      const s = this.settingsList.find(x => x.key === 'api_auth_mode');
      return s?.value || 'open';
    },

    get adminToken() {
      // Prefer isAuthenticated so cookie-only sessions still unlock Control Room.
      return this.$store.ui.isAuthenticated || this.$store.ui.adminToken;
    },

    secretSettings() {
      // Product-relevant secrets (CMC removed). Extra on-chain keys optional.
      const keys = [
        'secret_ollama_api_key',
        'secret_openrouter_api_key',
        'secret_tavily_api_key',
        'secret_exa_api_key',
        'secret_moralis_api_key',
        'secret_alchemy_api_key',
        'secret_flipside_api_key',
        'secret_thegraph_api_key',
        'secret_etherscan_api_key',
        'webhook_signing_secret',
        'fred_api_key',
        'coinglass_api_key',
      ];
      return keys
        .map(k => this.settingsList.find(s => s.key === k))
        .filter(Boolean);
    },

    splitProviderModel(val) {
      const s = String(val || '').trim();
      const i = s.indexOf(':');
      if (i <= 0) return { provider: 'ollama_cloud', model: s };
      return { provider: s.slice(0, i), model: s.slice(i + 1) };
    },

    modelSettingValue(key) {
      const s = this.settingsList.find(x => x.key === key);
      return s?.value || '';
    },

    _parseModelCatalogResponse(payload) {
      // New shape: { models: [], error: string|null }; legacy: bare array
      if (Array.isArray(payload)) {
        return { models: payload, error: null };
      }
      if (payload && typeof payload === 'object') {
        return {
          models: Array.isArray(payload.models) ? payload.models : [],
          error: payload.error || null,
        };
      }
      return { models: [], error: 'invalid_response' };
    },

    _catalogErrorMessage(err) {
      if (!err) return '';
      if (err === 'no_api_key') return 'API key not configured';
      if (String(err).startsWith('provider_http_')) return `Provider HTTP ${String(err).slice('provider_http_'.length)}`;
      if (String(err).startsWith('provider_error:')) return `Provider error (${String(err).slice('provider_error:'.length)})`;
      return String(err);
    },

    async loadModelCatalogs() {
      if (!this.adminToken) return;
      this.modelCatalogLoading = true;
      this.modelCatalogError = '';
      try {
        const [o, r] = await Promise.all([
          this._adminFetch('/api/ai/providers/ollama_cloud/models', { cache: 'no-store' }),
          this._adminFetch('/api/ai/providers/openrouter/models', { cache: 'no-store' }),
        ]);
        const ollamaRaw = o.ok ? await o.json() : { models: [], error: o.status === 401 ? 'auth' : 'fetch_failed' };
        const openrouterRaw = r.ok ? await r.json() : { models: [], error: r.status === 401 ? 'auth' : 'fetch_failed' };
        const ollama = this._parseModelCatalogResponse(ollamaRaw);
        const openrouter = this._parseModelCatalogResponse(openrouterRaw);
        this.modelCatalog = {
          ollama_cloud: ollama.models,
          openrouter: openrouter.models,
        };
        const parts = [];
        if (ollama.error) parts.push(`Ollama: ${this._catalogErrorMessage(ollama.error)}`);
        if (openrouter.error) parts.push(`OpenRouter: ${this._catalogErrorMessage(openrouter.error)}`);
        if (!o.ok && !r.ok) parts.push('Could not load models — sign in and set API keys');
        this.modelCatalogError = parts.join(' · ');
      } catch (e) {
        this.modelCatalogError = e.message || 'Model catalog failed';
      } finally {
        this.modelCatalogLoading = false;
      }
    },

    async saveFeatureModel(key, provider, modelId) {
      const model = (modelId || '').trim();
      const prov = (provider || 'ollama_cloud').trim();
      if (!model) {
        this.showToast('Model id required', 'error');
        return;
      }
      const value = `${prov}:${model}`;
      try {
        await this.toggleSetting(key, value);
        this.showToast(`${key} → ${value}`, 'success');
        await this.loadSettings();
      } catch (e) {
        this.showToast(e.message, 'error');
      }
    },

    onControlSubTab(id) {
      this.controlSubTab = id;
      if (id === 'overview') {
        this.loadOpsStatus();
        this.loadWebSearchStatus();
        this.loadAiHealth();
      }
      if (id === 'security') this.loadApiKeys();
      if (id === 'alerts') this.loadWebhookEndpoints();
      if (id === 'data') this.loadAssetCatalog();
      if (id === 'ai') {
        this.loadSettings();
        this.loadModelCatalogs();
        this.loadAiProviders();
        this.loadAiHealth();
      }
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
      // Sequential PUTs under admin rate limit (30/min); tiny gap avoids burst edge cases
      const entries = Object.entries(this.wizardFeatures || {});
      let failed = 0;
      for (const [key, val] of entries) {
        const s = this.settingsList.find(x => x.key === key);
        if (!s) continue;
        try {
          await this.toggleSetting(key, val);
        } catch (e) {
          failed += 1;
          this.showToast(`${key}: ${e.message}`, 'error');
        }
        await new Promise(res => setTimeout(res, 50));
      }
      try { localStorage.setItem('helix_setup_done', '1'); } catch {}
      this.setupDone = true;
      this.wizardStep = 3;
      this.showToast(
        failed ? `Quick Setup done with ${failed} error(s)` : 'Quick Setup complete',
        failed ? 'warning' : 'success',
      );
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
      this.$store.ui.showToast(message, type);
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
          // Touch getter so nav badge ($store.ui.aiModeLabel) updates
          void this.aiModeLabel;
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
      const j = await r.json().catch(() => ({}));
      const s = this.settingsList.find(x => x.key === key);
      if (s) {
        // Secrets: never keep plaintext in Alpine state after save
        s.value = s.type === 'secret' ? (j.value || 'configured') : (j.value !== undefined ? j.value : value);
      }
      if (key === 'ai_mode') void this.aiModeLabel;
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
        const imported = j.imported ?? 0;
        const skipped = j.skipped ?? 0;
        const errN = Array.isArray(j.errors) ? j.errors.length : 0;
        let msg = `Imported ${imported}`;
        if (skipped) msg += `, skipped ${skipped} (incl. masked secrets)`;
        if (errN) msg += `, ${errN} error(s)`;
        this.showToast(msg, errN ? 'warning' : 'success');
        await this.loadSettings();
      } catch (e) {
        this.showToast(e.message, 'error');
      } finally {
        if (event?.target) event.target.value = '';
      }
    },
  };
}
