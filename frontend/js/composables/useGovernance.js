export function useGovernance() {
  return {
    settingsList: [],
    filteredSettings: [],
    settingsGroups: [],
    settingsSearch: '',
    settingsGroupFilter: '',
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
        // Build query parameters
        const params = new URLSearchParams();
        if (this.settingsSearch) params.append('search', this.settingsSearch);
        if (this.settingsGroupFilter) params.append('group', this.settingsGroupFilter);
        
        const r = await fetch(`/api/settings?${params.toString()}`, { 
          cache: 'no-store', 
          headers: this._adminHeaders() 
        });
        if (r.ok) { 
          this.settingsList = await r.json();
          this.filteredSettings = this.settingsList;
          
          // Extract unique groups
          this.settingsGroups = [...new Set(this.settingsList.map(s => s.group).filter(Boolean))].sort();
          
          return true;
        }
        this.settingsList = [];
        this.filteredSettings = [];
        return false;
      } catch (e) { 
        this.settingsList = [];
        this.filteredSettings = [];
        return false;
      }
    },

    async filterSettings() {
      // Debounce by using a small delay
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
        const r = await fetch('/api/settings/export/json', {
          headers: this._adminHeaders()
        });
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
          alert('Export failed: ' + (await r.text()));
        }
      } catch (e) {
        alert('Export failed: ' + e.message);
      }
    },

    async importSettings(event) {
      const file = event.target.files[0];
      if (!file) return;
      
      try {
        const formData = new FormData();
        formData.append('file', file);
        
        const r = await fetch('/api/settings/import/json', {
          method: 'POST',
          headers: this._adminHeaders(),
          body: formData
        });
        
        if (r.ok) {
          const result = await r.json();
          alert(`Import successful: ${result.imported} settings imported, ${result.skipped} skipped.`);
          // Refresh settings
          await this.loadSettings();
        } else {
          alert('Import failed: ' + (await r.text()));
        }
      } catch (e) {
        alert('Import failed: ' + e.message);
      }
    },

    triggerImport() {
      // Trigger the file input click
      document.querySelector('input[type="file"]').click();
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
