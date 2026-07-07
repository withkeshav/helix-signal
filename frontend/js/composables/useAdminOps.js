export function useAdminOps() {
  return {
    adminDrawerVisible: false,
    diagnostics: null,
    backfillAsset: '',
    backfillDays: 7,
    backfillResult: null,
    backfillLoading: false,
    adminOpsError: '',
    schedulerRunning: null,

    init() {
    },

    async openAdminDrawer() {
      this.adminDrawerVisible = true;
      await this.loadDiagnostics();
    },

    async loadDiagnostics() {
      this.adminOpsError = '';
      const headers = { ...(this.$store?.ui?.adminHeaders?.() || {}) };
      try {
        const res = await fetch('/api/admin/diagnostics', { headers, cache: 'no-store' });
        if (res.ok) {
          this.diagnostics = await res.json();
          this.schedulerRunning = this.diagnostics?.health?.scheduler_running ?? null;
        } else if (res.status === 401 || res.status === 403) {
          this.adminOpsError = 'Admin token required for diagnostics.';
        } else {
          this.adminOpsError = `Diagnostics failed (${res.status})`;
        }
      } catch (e) {
        this.adminOpsError = `Diagnostics failed: ${e.message}`;
      }
    },

    async runBackfill() {
      if (!this.backfillAsset) {
        this.adminOpsError = 'Asset is required for backfill.';
        return;
      }
      this.backfillLoading = true;
      this.adminOpsError = '';
      const headers = { ...(this.$store?.ui?.adminHeaders?.() || {}) };
      try {
        const res = await fetch(`/api/admin/backfill?asset=${this.backfillAsset.toUpperCase()}&days=${this.backfillDays}`, { method: 'POST', headers });
        if (res.ok) {
          this.backfillResult = await res.json();
        } else if (res.status === 401 || res.status === 403) {
          this.adminOpsError = 'Admin token required for backfill.';
        } else {
          this.adminOpsError = `Backfill failed (${res.status})`;
        }
      } catch (e) {
        this.adminOpsError = `Backfill failed: ${e.message}`;
      } finally {
        this.backfillLoading = false;
      }
    },

    async downloadDiagnosticsJson() {
      if (!this.diagnostics) return;
      const blob = new Blob([JSON.stringify(this.diagnostics, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `helix-diagnostics-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    },

    async exportEventsCsv() {
      const headers = { ...(this.$store?.ui?.adminHeaders?.() || {}) };
      try {
        const res = await fetch('/api/events/export?limit=500&format=csv', { headers });
        if (res.ok) {
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = 'events_export.csv';
          a.click();
          URL.revokeObjectURL(url);
        } else {
          this.adminOpsError = `Events export failed (${res.status})`;
        }
      } catch (e) {
        this.adminOpsError = `Events export failed: ${e.message}`;
      }
    },

    fmtUsd(v) {
      if (v == null) return '-';
      if (Math.abs(v) >= 1e9) return '$' + (v / 1e9).toFixed(2) + 'B';
      if (Math.abs(v) >= 1e6) return '$' + (v / 1e6).toFixed(2) + 'M';
      return '$' + v.toLocaleString();
    },
  };
}