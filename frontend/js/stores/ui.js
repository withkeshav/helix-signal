export function registerUiStore(Alpine) {
  Alpine.store('ui', {
    tab: 'overview',
    theme: 'light',
    searchQuery: '',
    searchResults: [],
    adminToken: sessionStorage.getItem('helix_admin_token') || '',
    evidenceOpen: false,
    enabledAssets: [],
    refreshing: false,

    setTheme(t) {
      this.theme = t;
      document.documentElement.setAttribute('data-theme', t);
    },

    setTab(t) {
      this.tab = t;
      location.hash = t;
    },

    saveAdminToken() {
      sessionStorage.setItem('helix_admin_token', this.adminToken || '');
    },

    adminHeaders() {
      return this.adminToken ? { 'X-Admin-Token': this.adminToken } : {};
    },
  });
}
