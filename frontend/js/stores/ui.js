/**
 * UI store — theme, tabs, toasts, and single-operator admin session.
 *
 * Auth model (single admin, not multi-user product):
 * - One admin row is seeded via HELIX_ADMIN_USERNAME/PASSWORD (seed_admin / deploy).
 * - POST /api/auth/login → HMAC session token in JSON + httpOnly helix_session cookie.
 * - Browser keeps a mirror in localStorage (X-Admin-Token) for non-cookie clients.
 * - isAuthenticated is the UI gate; restoreSession() re-hydrates from cookie and/or token.
 * - Multi-user CRUD exists only behind feature_multi_user (off by default) — not the product path.
 */

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
    theme: 'dark',
    refreshTick: 0,
    fetchInFlight: 0,
    searchQuery: '',
    searchResults: [],
    /** Mirror of session token for X-Admin-Token header (same value as helix_session cookie body). */
    adminToken: _loadStoredAdminToken(),
    /** True when operator session is valid (cookie and/or token). Prefer this over raw adminToken for UI. */
    isAuthenticated: !!_loadStoredAdminToken(),
    adminUsername: '',
    loginUsername: '',
    loginPassword: '',
    authError: '',
    enabledAssets: [],
    aiModeLabel: 'Off',
    dataHealthLabel: '—',
    /** Bridge: Settings sub-tab to open after navigating to Settings (avoids Alpine _x_dataStack). */
    controlSubTabRequest: '',
    /** Bridge: address to investigate after navigating to Forensics. */
    pendingInvestigateAddress: '',
    refreshing: false,
    toastMessage: '',
    toastType: 'info',
    toastVisible: false,
    toastTimer: null,
    modalVisible: false,
    modalTitle: '',
    modalBody: '',

    beginFetch() {
      this.fetchInFlight += 1;
      this.refreshing = this.fetchInFlight > 0;
    },

    endFetch() {
      this.fetchInFlight = Math.max(0, this.fetchInFlight - 1);
      this.refreshing = this.fetchInFlight > 0;
    },

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
      // helixApp watches $store.ui.tab — no _x_dataStack required
      window.dispatchEvent(new CustomEvent('ui-tab-set', { detail: { tab: t } }));
    },

    requestSettingsSubTab(sub) {
      this.controlSubTabRequest = sub || 'overview';
    },

    requestInvestigate(addr) {
      this.pendingInvestigateAddress = (addr || '').trim();
    },

    _setAuthenticated(ok, { token, username } = {}) {
      this.isAuthenticated = !!ok;
      if (username != null) this.adminUsername = username || '';
      if (token != null) {
        this.adminToken = token || '';
        _persistAdminToken(this.adminToken);
      }
      if (!ok) {
        this.adminToken = '';
        this.adminUsername = '';
        _persistAdminToken('');
      }
      _dispatchAuthChanged(!!ok);
    },

    adminHeaders() {
      return this.adminToken ? { 'X-Admin-Token': this.adminToken } : {};
    },

    async adminFetch(url, opts = {}) {
      const token = this.adminToken;
      const headers = { ...(opts.headers || {}), ...this.adminHeaders() };
      const sentToken = !!token;
      const wasAuthed = this.isAuthenticated;
      const response = await fetch(url, { ...opts, headers, credentials: 'include' });
      // Clear session only when we believed we were authed and server rejected us.
      // Cookie-only sessions may omit X-Admin-Token; still clear on 401/403 if isAuthenticated.
      if ((response.status === 401 || response.status === 403) && (sentToken || wasAuthed)) {
        this._setAuthenticated(false);
        this.authError = 'Session expired — sign in via Settings';
        this.showToast(this.authError, 'warning', 6000);
      }
      return response;
    },

    _onStorageAuthSync(e) {
      if (e.key !== ADMIN_TOKEN_KEY) return;
      const next = e.newValue || '';
      if (next === this.adminToken) return;
      this.adminToken = next;
      this.isAuthenticated = !!next;
      this.authError = '';
      if (!next) this.adminUsername = '';
      _dispatchAuthChanged(!!next);
    },

    initAuthSync() {
      window.addEventListener('storage', (e) => this._onStorageAuthSync(e));
    },

    async restoreSession() {
      try {
        const r = await fetch('/api/auth/me', {
          credentials: 'include',
          headers: this.adminHeaders(),
          cache: 'no-store',
        });
        if (r.ok) {
          const data = await r.json().catch(() => ({}));
          this.authError = '';
          // Keep existing token mirror if present; cookie may be enough for API.
          this.isAuthenticated = true;
          this.adminUsername = data.username || this.adminUsername || '';
          _dispatchAuthChanged(true);
          return true;
        }
        // Invalid stale mirror — clear
        if (this.adminToken) {
          this._setAuthenticated(false);
        }
      } catch {
        /* network — leave local mirror; next adminFetch will revalidate */
      }
      return false;
    },

    async login() {
      this.authError = '';
      let username = this.loginUsername;
      let password = this.loginPassword;
      if (!username || !password) {
        const root = document.getElementById('tab-settings');
        username = username || root?.querySelector('input[placeholder="Username"]')?.value
          || root?.querySelector('input[autocomplete="username"]')?.value || '';
        password = password || root?.querySelector('input[placeholder="Password"]')?.value
          || root?.querySelector('input[autocomplete="current-password"]')?.value || '';
      }
      if (!username || !password) {
        this.authError = 'Enter username and password';
        return false;
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
          this.authError = r.status === 503
            ? 'Server auth not configured (SESSION_SIGNING_KEY)'
            : 'Invalid credentials';
          return false;
        }
        const data = await r.json();
        this.loginPassword = '';
        this.authError = '';
        this._setAuthenticated(true, {
          token: data.access_token || '',
          username: data.username || username,
        });
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
      } catch {
        /* still clear local state */
      }
      this.loginUsername = '';
      this.loginPassword = '';
      this.authError = '';
      this._setAuthenticated(false);
    },
  });
}
