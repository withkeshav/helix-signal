export function registerUiStore(Alpine) {
  Alpine.store('ui', {
    tab: 'signal',
    theme: 'light',
    searchQuery: '',
    searchResults: [],
    adminToken: sessionStorage.getItem('helix_admin_token') || '',
    loginUsername: '',
    loginPassword: '',
    authError: '',
    enabledAssets: [],
    refreshing: false,
    toastMessage: '',
    toastType: 'info',
    toastVisible: false,
    toastTimer: null,
    modalVisible: false,
    modalTitle: '',
    modalBody: '',

    showToast(message, type = 'info', duration = 4000) {
      this.toastMessage = message;
      this.toastType = type;
      this.toastVisible = true;
      clearTimeout(this.toastTimer);
      this.toastTimer = setTimeout(() => { this.toastVisible = false; }, duration);
    },

    hideToast() {
      this.toastVisible = false;
      clearTimeout(this.toastTimer);
    },

    showModal(title, bodyHtml) {
      this.modalTitle = title;
      this.modalBody = bodyHtml;
      this.modalVisible = true;
    },

    closeModal() {
      this.modalVisible = false;
      this.modalTitle = '';
      this.modalBody = '';
    },

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

    async login() {
      this.authError = '';
      let username = this.loginUsername;
      let password = this.loginPassword;
      if (!username || !password) {
        const root = document.getElementById('tab-settings');
        username = username || root?.querySelector('input[placeholder="Username"]')?.value || '';
        password = password || root?.querySelector('input[placeholder="Password"]')?.value || '';
      }
      const body = new URLSearchParams({ username, password });
      try {
        const r = await fetch('/api/auth/login', {
          method: 'POST',
          body,
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        });
        if (!r.ok) {
          this.authError = 'Invalid credentials';
          return false;
        }
        const data = await r.json();
        this.adminToken = data.access_token || '';
        sessionStorage.setItem('helix_admin_token', this.adminToken);
        this.loginPassword = '';
        return true;
      } catch {
        this.authError = 'Login failed — check network';
        return false;
      }
    },

    logout() {
      this.adminToken = '';
      this.loginUsername = '';
      this.loginPassword = '';
      this.authError = '';
      sessionStorage.removeItem('helix_admin_token');
    },
  });
}
