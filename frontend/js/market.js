import { gaugeArc, gaugeColor } from './utils.js';

export function helixMarket() {
  return {
    asset: 'USDT',
    timeRange: '7d',
    enabledAssets: ['USDT', 'USDC', 'DAI', 'PYUSD'],
    chains: [],
    signal: {},
    depeg: {},
    concentration: {},
    crossSource: {},
    supplyFeed: {},
    attSignal: {},
    totalSupply: null,
    supplyChange: null,
    anomalyEvents: {},
    _trendCache: { signal: [], peg: [], supply: [] },

    get gaugeArc() { return gaugeArc(this.signal.score); },
    get gaugeColor() { return gaugeColor(this.signal.band); },

    sparkline(key) {
      const pts = this._trendCache[key || 'signal'];
      if (!pts || pts.length < 2) return '0,10 60,10';
      const max = Math.max(...pts), min = Math.min(...pts), range = max - min || 1;
      const w = 60, h = 20;
      const step = w / (pts.length - 1);
      return pts.map((v, i) => `${(i * step).toFixed(1)},${(h - ((v - min) / range) * (h - 4) - 2).toFixed(1)}`).join(' ');
    },

    async loadAnomalies() {
      try { const r = await fetch(`/api/anomaly/detect?asset=${this.asset}`, { cache: 'no-store' }); if (r.ok) this.anomalyEvents = await r.json(); } catch (e) { this.anomalyEvents = {}; }
    },

    async loadPredictive() {
      try { const r = await fetch(`/api/predictive?asset=${this.asset}`, { cache: 'no-store' }); if (r.ok) { const j = await r.json(); return j; } } catch (e) {}
      return null;
    },

    async loadTicker() {
      try {
        const r = await fetch(`/api/events?asset=${this.asset}&limit=12`, { cache: 'no-store' });
        if (!r.ok) return [];
        const j = await r.json();
        const evs = (j.events || []).filter(e => e.severity !== 'debug');
        return evs.length ? evs.concat(evs).map(e => `${(e.severity || 'info').toUpperCase()} · ${e.title} · ${this.formatWhen(e.timestamp)}`) : [];
      } catch (e) { return []; }
    },

    async loadSupplyTrend() {
      try {
        const r = await fetch(`/api/trends?asset=${this.asset}&window=30d`, { cache: 'no-store' });
        if (!r.ok) return null;
        const j = await r.json();
        return j;
      } catch (e) { return null; }
    },
  };
}
