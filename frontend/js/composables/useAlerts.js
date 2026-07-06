export function useAlerts() {
  return {
    alerts: [],
    rules: [],
    loading: false,
    error: '',
    assetFilter: '',
    severityFilter: '',
    adminToken: '',

    async init() {
      try { this.adminToken = localStorage.getItem('helix_admin_token') || ''; } catch { /* ignore */ }
      await this._loadAll();
    },

    async _loadAll() {
      this.loading = true;
      this.error = '';
      const headers = this.adminToken ? { 'X-Admin-Token': this.adminToken } : {};
      const failures = [];
      try {
        const params = new URLSearchParams({ limit: '100' });
        if (this.assetFilter) params.set('asset', this.assetFilter.toUpperCase());
        if (this.severityFilter) params.set('severity', this.severityFilter.toLowerCase());
        const [alertsRes, rulesRes] = await Promise.all([
          fetch(`/api/alerts?${params.toString()}`, { headers, cache: 'no-store' }),
          fetch('/api/alerts/config', { headers, cache: 'no-store' }),
        ]);
        if (alertsRes.ok) {
          const j = await alertsRes.json();
          this.alerts = j.events || [];
        } else {
          failures.push(`alerts (${alertsRes.status})`);
          if (alertsRes.status === 401 || alertsRes.status === 403) {
            this.error = 'Admin token required to view fired alerts.';
          }
        }
        if (rulesRes.ok) {
          this.rules = await rulesRes.json();
        } else {
          failures.push(`rules (${rulesRes.status})`);
        }
        if (failures.length && !this.error) {
          this.error = `Failed to load: ${failures.join(', ')}`;
        }
      } catch (e) {
        this.error = `Failed to load alerts data: ${e.message}`;
      } finally {
        this.loading = false;
      }
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