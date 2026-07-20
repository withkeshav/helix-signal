import { formatWhen, formatUsd } from '../utils.js';
import { STABLECOIN_TAXONOMY, getTypeBadge } from '../taxonomy.js';
import { renderInvestigationGraph, renderInvestigationSankey, renderInvestigationTimeline, renderClusterBubbles, exportGraphPNG, destroyGraph } from './useGraphPanel.js';

function _shortAddr(addr) {
  if (!addr || addr.length < 10) return addr || '?';
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

export function useForensics() {
  return {
    // Blacklist stats
    blacklistStats: null,
    loadingStats: false,
    errorStats: '',

    // Blacklist events
    blacklistEvents: [],
    loadingEvents: false,
    errorEvents: '',
    eventsAssetFilter: '',
    eventsOffset: 0,
    eventsLimit: 20,

    // Investigation
    investigateAddress: '',
    investigateChain: 'ethereum',
    investigateAsset: 'USDT',
    investigationResult: null,
    investigating: false,
    investigateError: '',

    // Graph visualization
    graphChart: null,
    graphSubTab: 'graph',
    graphCharts: { sankey: null, timeline: null, cluster: null },
    selectedNode: null,
    showDetailPanel: false,
    graphExporting: false,
    _graphNodeClickHandler: null,

    // Taxonomy
    taxonomySymbols: Object.keys(STABLECOIN_TAXONOMY).sort(),

    formatWhen,
    formatUsd,
    getTypeBadge,
    _shortAddr,

    _adminFetch(url, opts = {}) {
      return this.$store.ui.adminFetch(url, opts);
    },

    _onGraphNodeClick(e) {
      const detail = e.detail;
      if (detail && detail.node) {
        this.selectedNode = detail.node;
        this.showDetailPanel = true;
      }
    },

    closeDetail() {
      this.showDetailPanel = false;
      this.selectedNode = null;
    },

    exportGraph() {
      this.graphExporting = true;
      try {
        exportGraphPNG(this.graphChart);
      } catch (e) {}
      setTimeout(() => { this.graphExporting = false; }, 500);
    },

    selectedNodeCategoryName() {
      if (!this.selectedNode) return '';
      const cat = this.selectedNode.category;
      return ['Seed', 'Peel Hop', 'Cluster', 'Bridge', 'Blacklist', 'OSINT'][cat] || '';
    },

    selectedNodeDetails() {
      if (!this.selectedNode || !this.investigationResult) return [];
      const raw = this.selectedNode._raw || {};
      const lines = [];
      if (raw.hop) {
        const h = raw.hop;
        if (h.value_usd) lines.push(['Value', formatUsd(h.value_usd)]);
        else if (h.value) lines.push(['Value', h.value]);
        if (h.chain) lines.push(['Chain', h.chain]);
        if (h.tx_hash) lines.push(['Tx Hash', _shortAddr(h.tx_hash)]);
        if (h.timestamp) lines.push(['Time', formatWhen(h.timestamp)]);
      }
      if (raw.hit) {
        const hit = raw.hit;
        lines.push(['Event', 'Blacklist Hit']);
        if (hit.asset_symbol) lines.push(['Asset', hit.asset_symbol]);
        if (hit.frozen_balance_usd) lines.push(['Frozen', formatUsd(hit.frozen_balance_usd)]);
        if (hit.event_type) lines.push(['Type', hit.event_type]);
        if (hit.intelligence_note) lines.push(['Note', hit.intelligence_note]);
      }
      if (raw.article) {
        const art = raw.article;
        lines.push(['Source', art.source || '?']);
        if (art.title) lines.push(['Title', art.title.slice(0, 80)]);
        if (art.published_at) lines.push(['Published', formatWhen(art.published_at)]);
      }
      if (this.selectedNode.category === 0) {
        const r = this.investigationResult;
        lines.push(['Chain', r.chain || '?']);
        lines.push(['Asset', r.asset_symbol || '?']);
        lines.push(['Risk', r.risk_level || '?']);
        if (r.total_value_usd != null) lines.push(['Total Traced', formatUsd(r.total_value_usd)]);
        if (r.peel_hops?.length) lines.push(['Peel Hops', String(r.peel_hops.length)]);
        if (r.cluster?.cluster_id) lines.push(['Cluster ID', r.cluster.cluster_id]);
      }
      if (this.selectedNode.category === 2 && this.investigationResult.cluster?.cluster_id) {
        lines.push(['Cluster ID', this.investigationResult.cluster.cluster_id]);
      }
      return lines;
    },

    async loadBlacklistStats() {
      this.loadingStats = true;
      this.errorStats = '';
      try {
        const r = await fetch('/api/v1/blacklist/stats', { cache: 'no-store' });
        if (!r.ok) { this.errorStats = `HTTP ${r.status}`; return; }
        this.blacklistStats = await r.json();
      } catch (e) {
        this.errorStats = e.message;
        this.blacklistStats = null;
      } finally {
        this.loadingStats = false;
      }
    },

    async loadBlacklistEvents() {
      this.loadingEvents = true;
      this.errorEvents = '';
      try {
        let url = `/api/v1/blacklist/events?limit=${this.eventsLimit}&offset=${this.eventsOffset}`;
        if (this.eventsAssetFilter) url += `&asset=${this.eventsAssetFilter}`;
        const r = await fetch(url, { cache: 'no-store', headers: { ...(this.$store?.ui?.adminHeaders?.() || {}) } });
        if (!r.ok) { this.errorEvents = `HTTP ${r.status}`; return; }
        this.blacklistEvents = await r.json();
      } catch (e) {
        this.errorEvents = e.message;
        this.blacklistEvents = [];
      } finally {
        this.loadingEvents = false;
      }
    },

    filterEvents() {
      this.eventsOffset = 0;
      this.loadBlacklistEvents();
    },

    nextEventsPage() {
      this.eventsOffset += this.eventsLimit;
      this.loadBlacklistEvents();
    },

    prevEventsPage() {
      if (this.eventsOffset > 0) {
        this.eventsOffset = Math.max(0, this.eventsOffset - this.eventsLimit);
        this.loadBlacklistEvents();
      }
    },

    switchGraphSubTab(tab) {
      this.graphSubTab = tab;
      this.showDetailPanel = false;
      this.selectedNode = null;
      this.$nextTick(() => this._renderActiveSubTab());
    },

    _renderActiveSubTab() {
      if (!this.investigationResult) return;
      const r = this.investigationResult;
      switch (this.graphSubTab) {
        case 'graph':
          destroyGraph(this.graphChart);
          this.graphChart = renderInvestigationGraph(r);
          break;
        case 'sankey':
          destroyGraph(this.graphCharts.sankey);
          this.graphCharts.sankey = renderInvestigationSankey(r);
          break;
        case 'timeline':
          destroyGraph(this.graphCharts.timeline);
          this.graphCharts.timeline = renderInvestigationTimeline(r);
          break;
        case 'cluster':
          destroyGraph(this.graphCharts.cluster);
          this.graphCharts.cluster = renderClusterBubbles(r);
          break;
      }
    },

    async investigate() {
      if (!this.investigateAddress) { this.investigateError = 'Enter an address'; return; }
      this.investigating = true;
      this.investigateError = '';
      this.investigationResult = null;
      this.showDetailPanel = false;
      this.selectedNode = null;
      this.graphSubTab = 'graph';
      try {
        const r = await this._adminFetch('/api/v1/investigate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            address: this.investigateAddress,
            chain: this.investigateChain,
            asset: this.investigateAsset,
          }),
        });
        if (!r.ok) { this.investigateError = `HTTP ${r.status}`; return; }
        this.investigationResult = await r.json();
        this.$nextTick(() => this._renderActiveSubTab());
      } catch (e) {
        this.investigateError = e.message;
      } finally {
        this.investigating = false;
      }
    },

    _resizeAllCharts() {
      const all = [this.graphChart, ...Object.values(this.graphCharts)];
      for (const c of all) {
        if (c && typeof c.resize === 'function') { try { c.resize(); } catch (e) {} }
      }
    },

    init() {
      this.loadBlacklistStats();
      this.loadBlacklistEvents();
      this._consumePendingInvestigate();

      this._graphNodeClickHandler = (e) => this._onGraphNodeClick(e);
      window.addEventListener('graph-node-click', this._graphNodeClickHandler);

      this.$watch('$store.ui.tab', (tab) => {
        if (tab === 'forensics') {
          this.loadBlacklistStats();
          this.loadBlacklistEvents();
          this._consumePendingInvestigate();
          this.$nextTick(() => {
            if (this.investigationResult && !this.graphChart && this.graphSubTab === 'graph') {
              this._renderActiveSubTab();
            }
            this._resizeAllCharts();
          });
        }
      });

      // Refresh blacklist KPIs on global 60s tick while on Forensics
      this.$watch('$store.ui.refreshTick', () => {
        if (this.$store.ui.tab === 'forensics') {
          this.loadBlacklistStats();
          this.loadBlacklistEvents();
        }
      });

      this.$watch('$store.ui.pendingInvestigateAddress', (addr) => {
        if (addr) this._consumePendingInvestigate();
      });
    },

    _consumePendingInvestigate() {
      const addr = (this.$store?.ui?.pendingInvestigateAddress || '').trim();
      if (!addr) return;
      this.investigateAddress = addr;
      this.$store.ui.pendingInvestigateAddress = '';
      this.$nextTick(() => {
        if (typeof this.investigate === 'function') this.investigate();
      });
    },

    _destroyAllCharts() {
      destroyGraph(this.graphChart);
      this.graphChart = null;
      for (const k of Object.keys(this.graphCharts)) {
        destroyGraph(this.graphCharts[k]);
        this.graphCharts[k] = null;
      }
    },

    destroy() {
      if (this._graphNodeClickHandler) {
        window.removeEventListener('graph-node-click', this._graphNodeClickHandler);
      }
      this._destroyAllCharts();
    },
  };
}
