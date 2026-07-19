/** Operator event labeling (WO-DA-5). */

export function useEventLabels() {
  return {
    async loadLabels(eventType, eventId) {
      try {
        const r = await fetch(`/api/events/${eventType}/${encodeURIComponent(eventId)}/labels`, {
          cache: 'no-store',
        });
        if (!r.ok) return [];
        return await r.json();
      } catch {
        return [];
      }
    },

    async applyLabel(eventType, eventId, label, note = '') {
      const headers = { 'Content-Type': 'application/json', ...this.$store.ui.adminHeaders() };
      if (!headers['X-Admin-Token'] && !document.cookie.includes('helix_session')) {
        this.$store.ui.showToast('Sign in via Settings to label events', 'warning');
        return null;
      }
      const r = await fetch(`/api/events/${eventType}/${encodeURIComponent(eventId)}/labels`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ label, tags: [], note }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) {
        this.$store.ui.showToast(j.detail || 'Label failed', 'error');
        return null;
      }
      this.$store.ui.showToast(`Marked as ${label}`, 'success');
      return j;
    },

    latestLabel(labels) {
      if (!labels?.length) return null;
      return labels[labels.length - 1].label;
    },
  };
}

export function anomalyEventId(asset, metric, timestamp) {
  return `${asset}:${metric}:${timestamp}`;
}
