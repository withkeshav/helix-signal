export function useTags() {
  return {
    tags: [],
    tagSearchAddress: '',
    tagForm: { address: '', chain: '', label: '', category: 'suspicious', confidence: 0.8 },
    tagFormVisible: false,
    tagError: '',
    tagLoading: false,
    adminToken: '',

    init() {
      try { this.adminToken = localStorage.getItem('helix_admin_token') || ''; } catch { /* ignore */ }
    },

    async lookupTags() {
      const addr = (this.tagSearchAddress || '').trim();
      if (!addr) { this.tags = []; return; }
      this.tagLoading = true;
      this.tagError = '';
      try {
        const url = `/api/v1/tags/${encodeURIComponent(addr)}`;
        const res = await fetch(url, { cache: 'no-store' });
        if (res.ok) {
          this.tags = await res.json();
        } else if (res.status === 404) {
          this.tags = [];
        } else {
          this.tagError = `Lookup failed (${res.status})`;
        }
      } catch (e) {
        this.tagError = `Lookup failed: ${e.message}`;
      } finally {
        this.tagLoading = false;
      }
    },

    async createTag() {
      if (!this.tagForm.address || !this.tagForm.label) {
        this.tagError = 'Address and label are required';
        return;
      }
      this.tagError = '';
      const headers = { 'Content-Type': 'application/json' };
      if (this.adminToken) headers['X-Admin-Token'] = this.adminToken;
      try {
        const res = await fetch('/api/v1/tags', {
          method: 'POST',
          headers,
          body: JSON.stringify(this.tagForm),
        });
        if (res.ok) {
          this.tagForm = { address: '', chain: '', label: '', category: 'suspicious', confidence: 0.8 };
          this.tagFormVisible = false;
          if (this.tagSearchAddress) await this.lookupTags();
        } else if (res.status === 401 || res.status === 403) {
          this.tagError = 'Admin token required to create tags.';
        } else {
          this.tagError = `Create failed (${res.status})`;
        }
      } catch (e) {
        this.tagError = `Create failed: ${e.message}`;
      }
    },

    async deleteTag(tagId) {
      this.tagError = '';
      const headers = {};
      if (this.adminToken) headers['X-Admin-Token'] = this.adminToken;
      try {
        const res = await fetch(`/api/v1/tags/${tagId}`, { method: 'DELETE', headers });
        if (res.ok) {
          this.tags = this.tags.filter(t => t.id !== tagId);
        } else if (res.status === 401 || res.status === 403) {
          this.tagError = 'Admin token required to delete tags.';
        } else {
          this.tagError = `Delete failed (${res.status})`;
        }
      } catch (e) {
        this.tagError = `Delete failed: ${e.message}`;
      }
    },

    async exportTagsCsv() {
      const headers = {};
      if (this.adminToken) headers['X-Admin-Token'] = this.adminToken;
      try {
        const res = await fetch('/api/v1/tags/export', { headers });
        if (res.ok) {
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = 'address_tags.csv';
          a.click();
          URL.revokeObjectURL(url);
        } else if (res.status === 401 || res.status === 403) {
          this.tagError = 'Admin token required to export tags.';
        } else {
          this.tagError = `Export failed (${res.status})`;
        }
      } catch (e) {
        this.tagError = `Export failed: ${e.message}`;
      }
    },
  };
}