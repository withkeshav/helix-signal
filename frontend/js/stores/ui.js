const ADMIN_TOKEN_KEY = 'helix_admin_token';

function _loadStoredAdminToken() {
  try {
    return localStorage.getItem(ADMIN_TOKEN_KEY) || sessionStorage.getItem(ADMIN_TOKEN_KEY) || '';
  } catch {
    return sessionStorage.getItem(ADMIN_TOKEN_KEY) || '';
  }
}

function _persistAdminToken(token) {
  const value = token || '';
  try {
    if (value) {
      localStorage.setItem(ADMIN_TOKEN_KEY, value);
      sessionStorage.setItem(ADMIN_TOKEN_KEY, value);
    } else {
      localStorage.removeItem(ADMIN_TOKEN_KEY);
      sessionStorage.removeItem(ADMIN_TOKEN_KEY);
    }
  } catch {
    if (value) sessionStorage.setItem(ADMIN_TOKEN_KEY, value);
    else sessionStorage.removeItem(ADMIN_TOKEN_KEY);
  }
}

function _dispatchAuthChanged(authenticated) {
  window.dispatchEvent(new CustomEvent('auth-changed', { detail: { authenticated: !!authenticated } }));
}

export function registerUiStore(Alpine) {
  Alpine.store('ui', {
    tab: 'signal',
    theme: 'light',
    searchQuery: '',
    searchResults: [],
    adminToken: _loadStoredAdminToken(),
    loginUsername: '',
    loginPassword: '',
    authError: '',
    enabledAssets: [],
    aiModeLabel: 'Off',
    dataHealthLabel: '—',
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

    adminHeaders() {
      return this.adminToken ? { 'X-Admin-Token': this.adminToken } : {};
    },

    async adminFetch(url, opts = {}) {
      const token = this.adminToken;
      const headers = { ...(opts.headers || {}), ...this.adminHeaders() };
      const sentToken = !!token;  // capture at request time, not response time
      const response = await fetch(url, { ...opts, headers, credentials: 'include' });
      // Only clear the token if this request included it (token was invalid/expired).
      // Don't clear on 401 from requests that had no token (e.g. pre-login composable fetches
      // whose 401 response arrives after login sets the token — race condition).
      if ((response.status === 401 || response.status === 403) && sentToken) {
        this.adminToken = '';
        _persistAdminToken('');
        this.authError = 'Session expired — sign in via Settings';
        _dispatchAuthChanged(false);
        this.showToast(this.authError, 'warning', 6000);
      }
      return response;
    },

    _onStorageAuthSync(e) {
      if (e.key !== ADMIN_TOKEN_KEY) return;
      const next = e.newValue || '';
      if (next === this.adminToken) return;
      this.adminToken = next;
      this.authError = '';
      _dispatchAuthChanged(!!next);
    },

    initAuthSync() {
      window.addEventListener('storage', (e) => this._onStorageAuthSync(e));
    },

    async restoreSession() {
      try {
        const r = await fetch('/api/auth/me', { credentials: 'include', headers: this.adminHeaders(), cache: 'no-store' });
        if (r.ok) {
          this.authError = '';
          _dispatchAuthChanged(true);
          return true;
        }
      } catch {}
      return false;
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
          credentials: 'include',
        });
        if (!r.ok) {
          this.authError = 'Invalid credentials';
          return false;
        }
        const data = await r.json();
        this.adminToken = data.access_token || '';
        _persistAdminToken(this.adminToken);
        this.loginPassword = '';
        this.authError = '';
        _dispatchAuthChanged(true);
        return true;
      } catch {
        this.authError = 'Login failed — check network';
        return false;
      }
    },

    async logout() {
      try {
        await fetch('/api/auth/logout', {
          method: 'POST',
          credentials: 'include',
          headers: this.adminHeaders(),
        });
      } catch {}
      this.adminToken = '';
      this.loginUsername = '';
      this.loginPassword = '';
      this.authError = '';
      _persistAdminToken('');
      _dispatchAuthChanged(false);
    },
  });
}
