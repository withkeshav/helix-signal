export function helixGovernance() {
  return {
    adminToken: sessionStorage.getItem('helix_admin_token') || '',
    settingsList: [],

    saveAdminToken() {
      sessionStorage.setItem('helix_admin_token', this.adminToken || '');
    },

    _adminHeaders() {
      return this.adminToken ? { 'X-Admin-Token': this.adminToken } : {};
    },

    async loadSettings() {
      try {
        const r = await fetch('/api/settings', { cache: 'no-store', headers: this._adminHeaders() });
        if (r.ok) { this.settingsList = await r.json(); return true; }
        this.settingsList = [];
        return false;
      } catch (e) { this.settingsList = []; return false; }
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
          if (item) item.value = value;
        }
      } catch (e) {}
    },
  };
}
