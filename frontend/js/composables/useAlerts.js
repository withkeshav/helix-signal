export function useAlerts() {
  return {
    alerts: [],
    rules: [],
    allRules: [],
    historyEvents: [],
    loading: false,
    savingRules: false,
    editorOpen: false,
    error: '',
    saveMessage: '',
    assetFilter: '',
    severityFilter: '',

    async init() {
      this._bindAuth();
      await this._loadAll();
    },

    _bindAuth() {
      this.$watch('$store.ui.adminToken', () => this._loadAll());
    },

    _adminFetch(url, opts = {}) {
      return this.$store.ui.adminFetch(url, opts);
    },

    async _loadAll() {
      this.loading = true;
      this.error = '';
      const failures = [];
      try {
        const params = new URLSearchParams({ limit: '100' });
        if (this.assetFilter) params.set('asset', this.assetFilter.toUpperCase());
        if (this.severityFilter) params.set('severity', this.severityFilter.toLowerCase());
        const [alertsRes, rulesRes, allRulesRes, eventsRes] = await Promise.all([
          this._adminFetch(`/api/alerts?${params.toString()}`, { cache: 'no-store' }),
          this._adminFetch('/api/alerts/config', { cache: 'no-store' }),
          this._adminFetch('/api/alerts/config?include_disabled=true', { cache: 'no-store' }),
          fetch('/api/events?limit=50', { cache: 'no-store' }),
        ]);
        if (alertsRes.ok) {
          const j = await alertsRes.json();
          this.alerts = j.events || [];
        } else {
          failures.push(`alerts (${alertsRes.status})`);
          if (alertsRes.status === 401 || alertsRes.status === 403) {
            this.error = 'Sign in via Settings to view fired alerts.';
          }
        }
        if (rulesRes.ok) {
          this.rules = await rulesRes.json();
        } else {
          failures.push(`rules (${rulesRes.status})`);
        }
        if (allRulesRes.ok) {
          this.allRules = await allRulesRes.json();
        }
        if (eventsRes.ok) {
          const ej = await eventsRes.json();
          this.historyEvents = (ej.events || []).filter(e => e.severity !== 'debug').slice(0, 20);
        }
        if (failures.length && !this.error) {
          const hasServer = failures.some(f => /\b5\d\d\b/.test(f));
          this.error = hasServer
            ? `Server error loading alerts data — retry later. (${failures.join(', ')})`
            : `Failed to load: ${failures.join(', ')}`;
        }
      } catch (e) {
        this.error = `Failed to load alerts data: ${e.message}`;
      } finally {
        this.loading = false;
      }
    },

    openRuleEditor() {
      if (!this.$store.ui.adminToken) {
        this.error = 'Sign in via Settings to edit alert rules.';
        return;
      }
      this.editorOpen = true;
      this.saveMessage = '';
    },

    toggleRuleEnabled(idx) {
      if (!this.allRules[idx]) return;
      this.allRules[idx].enabled = !this.allRules[idx].enabled;
    },

    ruleThreshold(rule) {
      const m = (rule.condition || '').match(/>\s*([\d.]+)/);
      return m ? m[1] : '';
    },

    setRuleThreshold(rule, val) {
      const prefix = (rule.condition || '').split('>')[0].trim();
      if (prefix && val !== '') {
        rule.condition = `${prefix} > ${val}`;
      }
    },

    async saveRules() {
      this.savingRules = true;
      this.saveMessage = '';
      this.error = '';
      try {
        const r = await this._adminFetch('/api/alerts/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ rules: this.allRules }),
        });
        if (r.ok) {
          this.saveMessage = 'Rules saved.';
          this.editorOpen = false;
          await this._loadAll();
        } else {
          const t = await r.text();
          this.error = `Save failed: ${t}`;
        }
      } catch (e) {
        this.error = `Save failed: ${e.message}`;
      } finally {
        this.savingRules = false;
      }
    },

    goSettings() {
      this.$store.ui.setTab('settings');
    },

    async filterAlerts() {
      await this._loadAll();
    },

    severityBadge(sev) {
      const s = (sev || '').toLowerCase();
      if (s === 'critical') return 'badge-critical';
      if (s === 'warning') return 'badge-warning';
      return 'badge-info';
    },

    formatWhen(ts) {
      if (!ts) return '-';
      const d = new Date(ts);
      const now = new Date();
      const diffMs = now - d;
      const mins = Math.floor(diffMs / 60000);
      if (mins < 1) return 'just now';
      if (mins < 60) return `${mins}m ago`;
      const hrs = Math.floor(mins / 60);
      if (hrs < 24) return `${hrs}h ago`;
      const days = Math.floor(hrs / 24);
      return `${days}d ago`;
    },
  };
}
