/** Slim Settings / governance Alpine component (Phase 2).
 *
 * Operator CRUD (settings keys, users, playbooks, audit) lives in SQLAdmin at /admin.
 * This composable keeps: login shell, Quick Setup wizard, Test AI / provider chain,
 * playbook apply, asset catalog, thin import/export, Open Admin Panel.
 */
export function useGovernance() {
  return {
    settingsList: [],
    settingsError: '',

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
        }
      } catch (e) {
        this.settingsError = e.message || 'Login failed';
      }
    },

    _bindAdminLoginForm() {
      /* no-op: form uses @submit.prevent */
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
          await this.loadAiBudget();
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
