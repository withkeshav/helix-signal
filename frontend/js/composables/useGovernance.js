export function useGovernance() {
  return {
    // --- State from original ---
    settingsList: [],
    filteredSettings: [],
    settingsGroups: [],
    settingsSearch: '',
    settingsGroupFilter: '',
    settingsError: '',
    aiBudget: { daily_budget: 0, tokens_used_today: 0, tokens_remaining: 0, pct_used: 0 },
    aiBudgetLoaded: false,
    secretValues: {},
    availableModels: {}, // Store available models for each provider

    // --- A1: Playbook state ---
    playbookLoading: null,
    playbooks: [],
    showCreatePlaybookModal: false,
    showEditPlaybookModal: false,
    newPlaybook: { name: '', label: '', description: '', settings: {} },
    editPlaybookData: { id: null, name: '', label: '', description: '', settings: {} },
    playbookSettingsEdit: {},

    // --- A2: Audit log state ---
    auditLog: [],
    auditFilter: '',
    auditSortField: 'created_at',
    auditSortAsc: false,
    auditHistory: [],
    auditHistoryModal: false,
    auditHistoryKey: '',
    auditHistoryLoading: false,
    auditPollTimer: null,

    // --- A3: Per-feature budget state ---
    featureBudgets: [
      { name: 'risk_explain', label: 'Risk Explain', share: 30, tokens: 0, sliderVal: 30 },
      { name: 'market_narrative', label: 'Market Narrative', share: 25, tokens: 0, sliderVal: 25 },
      { name: 'insight_summary', label: 'Insight Summary', share: 25, tokens: 0, sliderVal: 25 },
      { name: 'anomaly_detection', label: 'Anomaly Detection', share: 20, tokens: 0, sliderVal: 20 },
    ],
    totalBudgetSlider: 50000,

    // --- A4: Provider priority DnD state ---
    providers: [],
    dragIndex: null,
    dragOverIndex: null,

    // --- A5: Safe defaults state ---
    showConfirmDefaults: false,

    // --- Toast system ---
    toastMessage: '',
    toastType: '',
    toastVisible: false,
    toastTimer: null,
    
    // --- User management ---
    users: [],
    usersLoading: false,
    usersError: null,
    showAddUserModal: false,
    showEditUserModal: false,
    showDeleteUserModal: false,
    selectedUserId: null,
    newUser: { username: '', email: '', password: '', is_admin: false, role: 'user' },
    editUserForm: { username: '', email: '', is_active: true, is_admin: false, role: 'user' },

    settingsView: (typeof localStorage !== 'undefined' && localStorage.getItem('helix_settings_view')) || 'simple',
    setupDone: typeof localStorage !== 'undefined' && localStorage.getItem('helix_setup_done') === '1',
    wizardStep: 1,
    wizardAiMode: 'ai_lite',
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
    aiFeatureMap: [
      {
        ui: 'Risk explanation',
        tab: 'Signal → Risk Terminal',
        endpoint: 'GET /api/ai/explain',
        toggle: 'feature_ai_explain',
        kind: 'LLM',
        effectTab: 'signal',
        effectSelector: '#chart-risk-terminal',
        configureSelector: '#settings-feature_ai_explain',
      },
      {
        ui: 'Market overview',
        tab: 'Signal → Overview',
        endpoint: 'GET /api/ai/market-overview',
        toggle: 'feature_ai_summary',
        kind: 'LLM',
        effectTab: 'signal',
        effectAiSubTab: 'overview',
        effectSelector: '#signal-ai-overview',
        configureSelector: '#settings-feature_ai_summary',
      },
      {
        ui: 'Market narrative',
        tab: 'Signal → Narrative',
        endpoint: 'GET /api/ai/narrative',
        toggle: 'feature_ai_narrative',
        kind: 'LLM',
        effectTab: 'signal',
        effectAiSubTab: 'narrative',
        effectSelector: '#signal-ai-narrative',
        configureSelector: '#settings-feature_ai_narrative',
      },
      {
        ui: 'Insights',
        tab: 'Signal → Insights',
        endpoint: 'GET /api/ai/insights',
        toggle: 'feature_ai_insights',
        kind: 'LLM',
        effectTab: 'signal',
        effectAiSubTab: 'insights',
        effectSelector: '#signal-ai-insights',
        configureSelector: '#settings-feature_ai_insights',
      },
      {
        ui: 'OSINT sentiment',
        tab: 'Intel',
        endpoint: 'background',
        toggle: 'feature_nlp_sentiment',
        kind: 'LLM',
        effectTab: 'intel',
        effectSelector: '#chart-sentiment',
        configureSelector: '#settings-feature_nlp_sentiment',
      },
      {
        ui: 'Predictive regime',
        tab: 'Signal → Risk Terminal',
        endpoint: 'GET /api/predictive',
        toggle: '—',
        kind: 'Statistical',
        effectTab: 'signal',
        effectSelector: '#chart-risk-terminal',
      },
      {
        ui: 'DEWS score',
        tab: 'Signal',
        endpoint: 'GET /api/dews',
        toggle: '—',
        kind: 'Statistical',
        effectTab: 'signal',
        effectSelector: '#chart-risk-terminal',
      },
    ],

    _toBool(v) {
      return v === true || v === 'true' || v === 1 || v === '1';
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
        // Wait for `useMarket` x-if mount so it can update aiSubTab.
        await new Promise(r => setTimeout(r, 60));
        window.dispatchEvent(new CustomEvent('ai-subtab-set', { detail: { subtab: row.effectAiSubTab } }));
      }

      await this._scrollToSelector(row.effectSelector);
    },

    async navigateAiConfigure(row) {
      if (!row?.configureSelector) return;
      if (this.$store.ui.tab !== 'settings') this.$store.ui.setTab('settings');
      this.settingsView = 'advanced';
      await this._scrollToSelector(row.configureSelector);
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

    setSettingsView(view) {
      this.settingsView = view;
      try { localStorage.setItem('helix_settings_view', view); } catch {}
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

    async wizardApplyAiMode() {
      const pb = this.wizardPlaybook || (this.wizardAiMode === 'ai_full' ? 'quality' : this.wizardAiMode === 'ai_lite' ? 'balanced' : 'max_free');
      await this.applyPlaybook(pb);
      // Determinism: checkbox state should reflect server state after playbook apply.
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

    goToSettingsSection() {
      this.$store.ui.setTab('settings');
    },

    get adminToken() {
      return this.$store.ui.adminToken;
    },

    assetCatalog: [],
    assetCatalogLoading: false,
    providerTestLoading: false,
    providerTestResult: '',

    async loadAssetCatalog() {
      if (!this.adminToken) return;
      this.assetCatalogLoading = true;
      try {
        const r = await this._adminFetch('/api/assets/catalog', { cache: 'no-store' });
        if (r.ok) this.assetCatalog = await r.json();
      } catch {
        this.assetCatalog = [];
      } finally {
        this.assetCatalogLoading = false;
      }
    },

    async toggleAssetEnabled(row) {
      if (!row?.symbol) return;
      const next = !row.enabled;
      try {
        const r = await this._adminFetch(`/api/assets/${row.symbol}/enabled`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: next }),
        });
        if (r.ok) {
          await this.loadAssetCatalog();
          const ar = await fetch('/api/assets', { cache: 'no-store' });
          if (ar.ok) {
            const list = await ar.json();
            const symbols = (list || []).map(a => a.symbol).filter(Boolean);
            if (symbols.length) {
              this.$root.enabledAssets = symbols;
              this.$store.ui.enabledAssets = symbols;
            }
          }
          this.showToast(`Asset ${row.symbol} ${next ? 'enabled' : 'disabled'}`, 'success');
        } else {
          this.showToast('Failed to update asset', 'error');
        }
      } catch (e) {
        this.showToast(e.message, 'error');
      }
    },

    async runProviderTest() {
      this.providerTestLoading = true;
      this.providerTestResult = '';
      try {
        const r = await this._adminFetch('/api/ai/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        const j = await r.json();
        if (j.ok) {
          this.providerTestResult = `OK ${j.provider}/${j.model} (${j.latency_ms}ms)`;
        } else {
          this.providerTestResult = j.reason || 'Test failed';
        }
      } catch (e) {
        this.providerTestResult = e.message;
      } finally {
        this.providerTestLoading = false;
      }
    },

    get hasSecretSettings() {
      return this.filteredSettings.some(s => s.key.startsWith('secret_'));
    },
    get hasProviderSettings() {
      return this.filteredSettings.some(s => s.key.startsWith('provider_'));
    },
    get hasFeatureSettings() {
      return this.filteredSettings.some(s => s.key.startsWith('feature_'));
    },
    get hasRefreshSettings() {
      return this.filteredSettings.some(s => s.key.startsWith('refresh_'));
    },
    get hasAiSettings() {
      return this.filteredSettings.some(s => s.key.startsWith('ai_') || s.key === 'enable_anomaly_detection');
    },

    async submitAdminLogin() {
      const ok = await this.$store.ui.login();
      if (ok) {
        await this.loadSettings();
        await this.loadAiBudget();
      }
    },

    _adminHeaders() {
      return this.$store.ui.adminHeaders();
    },

    _adminFetch(url, opts = {}) {
      return this.$store.ui.adminFetch(url, opts);
    },

    // --- Init: keyboard shortcuts + polling ---
    init() {
      this._bindKeyboard();
      this._bindAdminLoginForm();
      this.$watch('$store.ui.tab', tab => {
        if (tab === 'settings') this.$nextTick(() => this._bindAdminLoginForm());
      });
      if (this.adminToken) this.startAuditPolling();
      this.initProviders();
      // Load available models
      this.loadAvailableModels();
      // Load users if multi-user feature is enabled
      if (this.settingsList.find(s => s.key === 'feature_multi_user')?.value) {
        this.loadUsers();
      }
      // Load playbooks
      this.loadPlaybooks();
      // Auto-reload settings + AI budget when admin token is saved (e.g. after login)
      this.$watch('$store.ui.adminToken', val => { if (val) { this.loadSettings(); this.loadAiBudget(); this.loadAssetCatalog(); } });
      if (this.adminToken) {
        this.loadSettings();
        this.loadAiBudget();
        this.loadAssetCatalog();
      }
    },

    destroy() {
      this.stopAuditPolling();
      if (this.toastTimer) clearTimeout(this.toastTimer);
    },

    // --- Toast ---
    showToast(msg, type) {
      this.toastMessage = msg;
      this.toastType = type || 'success';
      this.toastVisible = true;
      if (this.toastTimer) clearTimeout(this.toastTimer);
      this.toastTimer = setTimeout(() => { this.toastVisible = false; }, 4000);
    },

    hideToast() {
      this.toastVisible = false;
      if (this.toastTimer) clearTimeout(this.toastTimer);
    },

    // --- A7: Keyboard shortcuts ---
    _bindAdminLoginForm() {
      this.$nextTick(() => {
        const form = this.$root.querySelector('#admin-login-form');
        if (!form || form.dataset.loginBound) return;
        form.dataset.loginBound = '1';
        form.addEventListener('submit', (e) => {
          e.preventDefault();
          this.submitAdminLogin();
        });
      });
    },

    _bindKeyboard() {
      document.addEventListener('keydown', (e) => {
        if (this.$root && this.$root.style.display === 'none') return;
        const isMod = e.ctrlKey || e.metaKey;
        if (isMod && e.key === 's') {
          e.preventDefault();
          this.$dispatch('settings-save');
        }
        if (e.key === 'Escape') {
          this.auditHistoryModal = false;
          this.showConfirmDefaults = false;
        }
        if (e.key === 'p' && !e.ctrlKey && !e.metaKey && !e.altKey) {
          const active = document.activeElement;
          if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.tagName === 'SELECT')) return;
          e.preventDefault();
          const btn = this.$root.querySelector('.playbook-btn');
          if (btn) btn.focus();
        }
      });
    },

    // ===================================================================
    // A1: Playbook presets
    // ===================================================================
    async applyPlaybook(name) {
      this.playbookLoading = name;
      try {
        const r = await this._adminFetch(`/api/ai/playbook/${name}`, {
          method: 'POST',
          headers: this._adminHeaders(),
        });
        if (r.ok) {
          const data = await r.json();
          const count = data.changes?.length || 0;
          this.showToast(`Playbook "${name}" applied — ${count} settings updated`, 'success');
          await this.loadSettings();
          await this.loadAiBudget();
          this.loadFeatureBudgets();
        } else {
          const err = await r.text();
          this.showToast(`Failed to apply playbook: ${err}`, 'error');
        }
      } catch (e) {
        this.showToast(`Error: ${e.message}`, 'error');
      } finally {
        this.playbookLoading = null;
      }
    },

    async loadPlaybooks() {
      try {
        const r = await this._adminFetch('/api/playbooks', { headers: this._adminHeaders() });
        if (r.ok) {
          this.playbooks = await r.json();
        }
      } catch (e) {
        this.playbooks = [];
      }
    },

    async createPlaybook() {
      const name = this.newPlaybook.name.trim().toLowerCase().replace(/\s+/g, '_');
      if (!name) { this.showToast('Name is required', 'error'); return; }
      const settings = {};
      for (const [key, val] of Object.entries(this.playbookSettingsEdit)) {
        if (val !== '' && val !== null && val !== undefined) {
          settings[key] = val;
        }
      }
      if (!Object.keys(settings).length) { this.showToast('Select at least one setting', 'error'); return; }
      try {
        const r = await this._adminFetch('/api/playbooks', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...this._adminHeaders() },
          body: JSON.stringify({
            name,
            label: this.newPlaybook.label || this.newPlaybook.name,
            description: this.newPlaybook.description,
            settings,
          }),
        });
        if (r.ok) {
          this.showCreatePlaybookModal = false;
          this.newPlaybook = { name: '', label: '', description: '', settings: {} };
          this.playbookSettingsEdit = {};
          await this.loadPlaybooks();
          this.showToast('Playbook created', 'success');
        } else {
          const err = await r.text();
          this.showToast('Failed: ' + err, 'error');
        }
      } catch (e) {
        this.showToast('Error: ' + e.message, 'error');
      }
    },

    openEditPlaybook(pb) {
      this.editPlaybookData = {
        id: pb.id,
        name: pb.name,
        label: pb.label,
        description: pb.description,
        settings: { ...pb.settings },
      };
      this.playbookSettingsEdit = { ...pb.settings };
      for (const s of this.settingsList) {
        if (!(s.key in this.playbookSettingsEdit)) {
          this.playbookSettingsEdit[s.key] = '';
        }
      }
      this.showEditPlaybookModal = true;
    },

    async updatePlaybook() {
      const settings = {};
      for (const [key, val] of Object.entries(this.playbookSettingsEdit)) {
        if (val !== '' && val !== null && val !== undefined) {
          settings[key] = val;
        }
      }
      if (!Object.keys(settings).length) { this.showToast('Select at least one setting', 'error'); return; }
      try {
        const r = await this._adminFetch(`/api/playbooks/${this.editPlaybookData.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', ...this._adminHeaders() },
          body: JSON.stringify({
            label: this.editPlaybookData.label,
            description: this.editPlaybookData.description,
            settings,
          }),
        });
        if (r.ok) {
          this.showEditPlaybookModal = false;
          await this.loadPlaybooks();
          this.showToast('Playbook updated', 'success');
        } else {
          const err = await r.text();
          this.showToast('Failed: ' + err, 'error');
        }
      } catch (e) {
        this.showToast('Error: ' + e.message, 'error');
      }
    },

    openDeletePlaybook(pb) {
      if (!confirm(`Delete playbook "${pb.label}"? This cannot be undone.`)) return;
      this.deletePlaybook(pb.id);
    },

    async deletePlaybook(id) {
      try {
        const r = await this._adminFetch(`/api/playbooks/${id}`, {
          method: 'DELETE',
          headers: this._adminHeaders(),
        });
        if (r.ok) {
          await this.loadPlaybooks();
          this.showToast('Playbook deleted', 'success');
        } else {
          this.showToast('Failed to delete', 'error');
        }
      } catch (e) {
        this.showToast('Error: ' + e.message, 'error');
      }
    },

    initPlaybookSettingsEdit() {
      this.playbookSettingsEdit = {};
      for (const s of this.settingsList) {
        this.playbookSettingsEdit[s.key] = '';
      }
    },

    async applyCustomPlaybook(pb) {
      await this.applyPlaybook(pb.name);
    },

    // ===================================================================
    // A2: Audit log
    // ===================================================================
    startAuditPolling() {
      this.stopAuditPolling();
      this.auditPollTimer = setInterval(() => {
        if (document.hidden) return;
        this.loadAuditLog();
      }, 30000);
    },

    stopAuditPolling() {
      if (this.auditPollTimer) { clearInterval(this.auditPollTimer); this.auditPollTimer = null; }
    },

    async loadAuditLog() {
      try {
        const params = new URLSearchParams();
        params.set('limit', '100');
        if (this.auditFilter) params.set('setting_key', this.auditFilter);
        const r = await this._adminFetch(`/api/settings/audit?${params.toString()}`, {
          headers: this._adminHeaders(),
        });
        if (r.ok) {
          this.auditLog = await r.json();
          this.sortAuditLog();
        } else if (r.status === 401 || r.status === 403) {
          this.stopAuditPolling();
        }
      } catch (e) {}
    },

    toggleAuditSort(field) {
      if (this.auditSortField === field) {
        this.auditSortAsc = !this.auditSortAsc;
      } else {
        this.auditSortField = field;
        this.auditSortAsc = false;
      }
      this.sortAuditLog();
    },

    sortAuditLog() {
      const f = this.auditSortField;
      const asc = this.auditSortAsc;
      this.auditLog.sort((a, b) => {
        const va = a[f] ?? '';
        const vb = b[f] ?? '';
        const cmp = typeof va === 'string' ? va.localeCompare(vb) : (va > vb ? 1 : -1);
        return asc ? cmp : -cmp;
      });
    },

    async openAuditHistory(key) {
      this.auditHistoryKey = key;
      this.auditHistoryLoading = true;
      this.auditHistoryModal = true;
      try {
        const r = await this._adminFetch(`/api/settings/audit/history/${encodeURIComponent(key)}`, {
          headers: this._adminHeaders(),
        });
        if (r.ok) this.auditHistory = await r.json();
        else this.auditHistory = [];
      } catch (e) {
        this.auditHistory = [];
      } finally {
        this.auditHistoryLoading = false;
      }
    },

    closeAuditHistory() {
      this.auditHistoryModal = false;
      this.auditHistory = [];
      this.auditHistoryKey = '';
    },

    // ===================================================================
    // A3: Per-feature budget sliders
    // ===================================================================
    loadFeatureBudgets() {
      const total = this.aiBudget.daily_budget || 50000;
      this.totalBudgetSlider = total;
      for (const fb of this.featureBudgets) {
        fb.tokens = Math.round(total * fb.share / 100);
        fb.sliderVal = fb.share;
      }
    },

    updateFeatureBudget(fb, val) {
      const v = parseInt(val, 10) || 0;
      fb.sliderVal = Math.max(0, Math.min(100, v));
    },

    recalculateFeatureBudgets() {
      let totalPct = 0;
      for (const fb of this.featureBudgets) totalPct += fb.sliderVal;
      if (totalPct === 0) {
        for (const fb of this.featureBudgets) fb.sliderVal = 25;
        totalPct = 100;
      }
      const scale = totalPct > 0 ? 100 / totalPct : 1;
      for (const fb of this.featureBudgets) {
        fb.share = Math.round(fb.sliderVal * scale);
        fb.tokens = Math.round(this.totalBudgetSlider * fb.share / 100);
      }
    },

    async saveTotalBudget() {
      await this.toggleSetting('ai_daily_token_budget', this.totalBudgetSlider);
      this.recalculateFeatureBudgets();
      this.showToast('Budget updated', 'success');
    },

    // ===================================================================
    // A4: Provider priority drag-and-drop
    // ===================================================================
    initProviders() {
      const priorityStr = this.settingsList.find(s => s.key === 'ai_provider_priority')?.value;
      if (!priorityStr) return;
      try {
        const names = JSON.parse(typeof priorityStr === 'string' ? priorityStr : '[]');
        const PROVIDER_META = {
          groq: { label: 'Groq', cost: '$0.05/M', rpm: 30, model: 'llama-3.1-8b-instant' },
          ollama_cloud: { label: 'Ollama Cloud', cost: '$0.15/M', rpm: 60, model: 'ministral-3:8b-cloud' },
          openrouter_free: { label: 'OpenRouter Free', cost: 'Free', rpm: 20, model: 'openrouter/free' },
          openrouter_paid: { label: 'OpenRouter Paid', cost: '$0.60/M', rpm: 100, model: 'openai/gpt-4o-mini' },
        };
        this.providers = names.map((n, i) => ({
          name: n,
          ...(PROVIDER_META[n] || { label: n, cost: '?', rpm: '?', model: '?' }),
          index: i,
        }));
      } catch (e) {
        this.providers = [];
      }
    },

    handleDragStart(index) {
      this.dragIndex = index;
    },

    handleDragOver(index) {
      if (this.dragIndex === null || this.dragIndex === index) return;
      this.dragOverIndex = index;
      const items = [...this.providers];
      const [moved] = items.splice(this.dragIndex, 1);
      items.splice(index, 0, moved);
      this.providers = items.map((p, i) => ({ ...p, index: i }));
      this.dragIndex = index;
    },

    handleDragEnd() {
      this.dragIndex = null;
      this.dragOverIndex = null;
      this.saveProviderPriority();
    },

    async saveProviderPriority() {
      const names = this.providers.map(p => p.name);
      try {
        const r = await this._adminFetch('/api/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', ...this._adminHeaders() },
          body: JSON.stringify({ key: 'ai_provider_priority', value: JSON.stringify(names) }),
        });
        if (r.ok) {
          this.showToast('Provider priority updated', 'success');
        } else {
          this.showToast('Failed to save priority', 'error');
        }
      } catch (e) {
        this.showToast(`Error: ${e.message}`, 'error');
      }
    },

    // ===================================================================
    // A5: Apply Safe Defaults
    // ===================================================================
    openConfirmDefaults() {
      this.showConfirmDefaults = true;
    },

    closeConfirmDefaults() {
      this.showConfirmDefaults = false;
    },

    async applySafeDefaults() {
      this.showConfirmDefaults = false;
      let updated = 0;
      const errors = [];
      for (const s of this.settingsList) {
        if (s.always_active) continue;
        if (s.key === 'ai_daily_token_budget') continue;
        if (s.default === undefined) continue;
        try {
          const r = await this._adminFetch('/api/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', ...this._adminHeaders() },
            body: JSON.stringify({ key: s.key, value: s.default }),
          });
          if (r.ok) updated++;
          else errors.push(s.key);
        } catch (e) {
          errors.push(s.key);
        }
      }
      if (errors.length) {
        this.showToast(`Defaults applied: ${updated} ok, ${errors.length} failed`, 'error');
      } else {
        this.showToast(`All ${updated} settings reset to defaults`, 'success');
      }
      await this.loadSettings();
      await this.loadAiBudget();
      this.loadFeatureBudgets();
      this.initProviders();
    },

    // ===================================================================
    // A6: Setting helpers (display indicators)
    // ===================================================================
    isGrayedOut(s) {
      if (!s.depends_on) return false;
      const dep = this.settingsList.find(d => d.key === s.depends_on);
      return dep ? !dep.value : false;
    },

    // ===================================================================
    // Existing methods (unchanged from original, extended)
    // ===================================================================
    async loadSettings() {
      try {
        this.settingsError = '';
        const params = new URLSearchParams();
        if (this.settingsSearch) params.append('search', this.settingsSearch);
        if (this.settingsGroupFilter) params.append('group', this.settingsGroupFilter);
        const r = await this._adminFetch(`/api/settings?${params.toString()}`, { cache: 'no-store', headers: this._adminHeaders() });
        if (r.ok) {
          const data = await r.json();
          this.settingsList = data;
          this.filteredSettings = data;
          this.settingsGroups = [...new Set(data.map(s => s.group).filter(Boolean))].sort();
          const modeRow = data.find(s => s.key === 'ai_mode');
          const mode = modeRow?.value || 'ai_off';
          this.$store.ui.aiModeLabel = mode === 'ai_full' ? 'Full' : mode === 'ai_lite' ? 'Lite' : 'Off';
          this.loadFeatureBudgets();
          this.initProviders();
          // Load available models for model settings
          await this.loadAvailableModels();
          // Load users if multi-user feature is enabled
          if (this.settingsList.find(s => s.key === 'feature_multi_user')?.value) {
            this.loadUsers();
          }
          // Load playbooks after settings are loaded
          this.loadPlaybooks();
          return true;
        }
        this.settingsList = [];
        this.filteredSettings = [];
        this.settingsError = r.status === 401 || r.status === 403
          ? 'Session expired — please sign in'
          : `Settings failed (${r.status})`;
        return false;
      } catch (e) {
        this.settingsList = [];
        this.filteredSettings = [];
        this.settingsError = `Settings failed: ${e.message}`;
        return false;
      }
    },

    async loadAvailableModels() {
      try {
        // Initialize availableModels structure
        this.availableModels = {};
        
        // Fetch available providers
        const providersResponse = await this._adminFetch('/api/ai/providers', { headers: this._adminHeaders() });
        if (providersResponse.ok) {
          const providers = await providersResponse.json();
          
          // Fetch models for each provider
          for (const provider of providers) {
            try {
              const modelsResponse = await this._adminFetch(`/api/ai/providers/${provider.id}/models`, { headers: this._adminHeaders() });
              if (modelsResponse.ok) {
                const models = await modelsResponse.json();
                // Store models by provider ID
                this.availableModels[provider.id] = models;
              }
            } catch (e) {
              console.warn(`Failed to fetch models for provider ${provider.id}:`, e);
            }
          }
        }
      } catch (e) {
        console.warn('Failed to load available models:', e);
      }
    },

    async filterSettings() {
      await new Promise(resolve => setTimeout(resolve, 100));
      await this.loadSettings();
    },

    clearFilters() {
      this.settingsSearch = '';
      this.settingsGroupFilter = '';
      this.loadSettings();
    },

    async exportSettings() {
      try {
        const r = await this._adminFetch('/api/settings/export/json', { headers: this._adminHeaders() });
        if (r.ok) {
          const data = await r.json();
          const blob = new Blob([data.content], { type: 'application/json' });
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = data.filename || 'helix-settings-export.json';
          document.body.appendChild(a);
          a.click();
          window.URL.revokeObjectURL(url);
          document.body.removeChild(a);
        } else {
          this.showToast('Export failed: ' + (await r.text()), 'error');
        }
      } catch (e) {
        this.showToast('Export failed: ' + e.message, 'error');
      }
    },

    async importSettings(event) {
      const file = event.target.files[0];
      if (!file) return;
      try {
        const formData = new FormData();
        formData.append('file', file);
        const r = await this._adminFetch('/api/settings/import/json', {
          method: 'POST',
          headers: this._adminHeaders(),
          body: formData,
        });
        if (r.ok) {
          const result = await r.json();
          this.showToast(`Import: ${result.imported} imported, ${result.skipped} skipped`, 'success');
          await this.loadSettings();
        } else {
          this.showToast('Import failed: ' + (await r.text()), 'error');
        }
      } catch (e) {
        this.showToast('Import failed: ' + e.message, 'error');
      }
    },

    triggerImport() {
      document.querySelector('input[type="file"]').click();
    },

    async loadAiBudget() {
      try {
        const r = await this._adminFetch('/api/ai/budget', { cache: 'no-store', headers: this._adminHeaders() });
        if (r.ok) {
          this.aiBudget = await r.json();
          this.aiBudgetLoaded = true;
          this.loadFeatureBudgets();
        }
      } catch (e) {}
    },

    async toggleSetting(key, value) {
      try {
        const r = await this._adminFetch('/api/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', ...this._adminHeaders() },
          body: JSON.stringify({ key, value }),
        });
        if (r.ok) {
          const item = this.settingsList.find(s => s.key === key);
          if (item) item.value = item.type === 'secret' ? true : value;
          this.showToast(`Setting "${key}" updated`, 'success');
        } else {
          const err = await r.text();
          this.showToast(`Update failed: ${err}`, 'error');
        }
      } catch (e) {
        this.showToast(`Error: ${e.message}`, 'error');
      }
    },

    async saveSecret(key) {
      const val = this.secretValues[key];
      if (!val) return;
      await this.toggleSetting(key, val);
      this.secretValues[key] = '';
    },
    
    // ===================================================================
    // User Management Functions
    // ===================================================================
    
    async loadUsers() {
      this.usersLoading = true;
      this.usersError = null;
      try {
        const r = await this._adminFetch('/api/users', { headers: this._adminHeaders() });
        if (r.ok) {
          this.users = await r.json();
        } else {
          this.usersError = 'Failed to load users';
        }
      } catch (e) {
        this.usersError = e.message;
      } finally {
        this.usersLoading = false;
      }
    },
    
    async addUser() {
      try {
        const r = await this._adminFetch('/api/users', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...this._adminHeaders() },
          body: JSON.stringify(this.newUser)
        });
        if (r.ok) {
          this.showAddUserModal = false;
          this.newUser = { username: '', email: '', password: '', is_admin: false, role: 'user' };
          await this.loadUsers();
          this.showToast('User added successfully', 'success');
        } else {
          const err = await r.text();
          this.showToast('Error: ' + err, 'error');
        }
      } catch (e) {
        this.showToast('Error: ' + e.message, 'error');
      }
    },
    
    async editUser(user) {
      this.selectedUserId = user.id;
      this.editUserForm = {
        username: user.username,
        email: user.email,
        is_active: user.is_active,
        is_admin: user.is_admin,
        role: user.role
      };
      this.showEditUserModal = true;
    },
    
    async updateUser() {
      try {
        const r = await this._adminFetch(`/api/users/${this.selectedUserId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', ...this._adminHeaders() },
          body: JSON.stringify(this.editUserForm)
        });
        if (r.ok) {
          this.showEditUserModal = false;
          await this.loadUsers();
          this.showToast('User updated successfully', 'success');
        } else {
          const err = await r.text();
          this.showToast('Error: ' + err, 'error');
        }
      } catch (e) {
        this.showToast('Error: ' + e.message, 'error');
      }
    },
    
    async deleteUser(userId) {
      if (!confirm('Are you sure you want to delete this user? This cannot be undone.')) {
        return;
      }
      
      try {
        const r = await this._adminFetch(`/api/users/${userId}`, {
          method: 'DELETE',
          headers: this._adminHeaders()
        });
        if (r.ok) {
          await this.loadUsers();
          this.showToast('User deleted successfully', 'success');
        } else {
          const err = await r.text();
          this.showToast('Error: ' + err, 'error');
        }
      } catch (e) {
        this.showToast('Error: ' + e.message, 'error');
      }
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
  };
}
