export function useGovernance() {
  return {
    settingsList: [],
    aiBudget: { daily_budget: 0, tokens_used_today: 0, tokens_remaining: 0, pct_used: 0 },
    aiBudgetLoaded: false,
    secretValues: {},

    get adminToken() {
      return this.$store.ui.adminToken;
    },

    saveAdminToken() {
      this.$store.ui.saveAdminToken();
    },

    _adminHeaders() {
      return this.$store.ui.adminHeaders();
    },

    async loadSettings() {
      try {
        const r = await fetch('/api/settings', { cache: 'no-store', headers: this._adminHeaders() });
        if (r.ok) { this.settingsList = await r.json(); return true; }
        this.settingsList = [];
        return false;
      } catch (e) { this.settingsList = []; return false; }
    },

    async loadAiBudget() {
      try {
        const r = await fetch('/api/ai/budget', { cache: 'no-store' });
        if (r.ok) { this.aiBudget = await r.json(); this.aiBudgetLoaded = true; }
      } catch (e) {}
    },

    async toggleSetting(key, value) {
      try {
        const r = await fetch('/api/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', ...this._adminHeaders() },
          body: JSON.stringify({ key, value }),
        });
        if (r.ok) {
          const item = this.settingsList.find(s => s.key === key);
          if (item) item.value = item.type === 'secret' ? true : value;
        }
      } catch (e) {}
    },

    async saveSecret(key) {
      const val = this.secretValues[key];
      if (!val) return;
      await this.toggleSetting(key, val);
      this.secretValues[key] = '';
    },
  };
}
