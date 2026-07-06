import { formatUsd, formatDate } from './utils.js';

export function _disposeChart(c) {
  if (!c) return;
  if (typeof c.dispose === 'function') {
    if (typeof c.isDisposed !== 'function' || !c.isDisposed()) c.dispose();
  }
}

export function destroyCharts() {
  if (!this._charts) return;
  for (const [, c] of this._charts) _disposeChart(c);
  this._charts.clear();
}

export function destroyForecastCharts() {
  if (!this._echarts) return;
  for (const [, c] of this._echarts) _disposeChart(c);
  this._echarts.clear();
}

export function _disposeAllCharts() {
  this.destroyCharts();
  if (typeof this.destroyForecastCharts === 'function') this.destroyForecastCharts();
  if (window._helixResizeHandler) {
    window.removeEventListener('resize', window._helixResizeHandler);
    window._helixResizeHandler = null;
  }
}

export function _setupResizeHandler() {
  if (window._helixResizeHandler) return;
  window._helixResizeHandler = () => {
    try {
      for (const m of [this._charts, this._echarts]) {
        if (!m) continue;
        for (const [, c] of m) {
          try {
            if (typeof c.isDisposed === 'function' && !c.isDisposed()) c.resize();
          } catch (e) { /* chart resize guard */ }
        }
      }
    } catch (e) { /* resize handler guard */ }
  };
  window.addEventListener('resize', window._helixResizeHandler);
}

const _cssVar = (name, fallback) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

export function renderCharts(data) {
  if (!this._charts) this._charts = new Map();
  this.destroyCharts();
  const primary = _cssVar('--spark', '#60a5fa');
  const chains = data.chains || [];
  if (chains.length) {
    const sorted = [...chains].sort((a, b) => Number(b.chain_share_pct || 0) - Number(a.chain_share_pct || 0)).slice(0, 12);
    const labels = sorted.map(c => c.chain_name);
    const vals = sorted.map(c => c.chain_share_pct || 0);
    const supplyVals = sorted.map(c => c.supply_current || 0);
    _makeBar.call(this, 'chart-distribution', labels, vals, primary, '%');
    _makeBar.call(this, 'chart-supply-bar', labels, supplyVals, primary, '$');
  }
  this.loadTrendChart();
}

export function loadTrendChart() {
  const _asset = this.asset;
  const primary = _cssVar('--spark', '#60a5fa');
  const muted = _cssVar('--muted', '#9aa8c4');
  const tr = this.timeRange || '7d';
  fetch(`/api/trends?asset=${this.asset}&window=${tr}`, { cache: 'no-store' })
    .then(r => r.ok ? r.json() : null)
    .then(t => {
      if (this.asset !== _asset) return;
      if (!t || !t.points || !t.points.length) return;
      if (t.points && t.points.length >= 2 && this.$store) {
        const sig = t.points.map(p => p.signal_score);
        const peg = t.points.map(p => p.price);
        const sup = t.points.map(p => p.total_supply);
        if (typeof this._computeSpark === 'function') {
          this.$store.dashboard.signalSpark = this._computeSpark(sig);
          this.$store.dashboard.pegSpark = this._computeSpark(peg);
          this.$store.dashboard.supplySpark = this._computeSpark(sup);
        }
      }
      const el = document.getElementById('chart-trend-signal');
      if (!el) return;
      if (this._echarts?.has('chart-trend-signal')) this._disposeChart(this._echarts.get('chart-trend-signal'));
      const pts = t.points.map(p => [new Date(p.timestamp).getTime(), p.signal_score != null ? Number(p.signal_score) : null]);
      const chart = echarts.init(el);
      if (!this._echarts) this._echarts = new Map();
      this._echarts.set('chart-trend-signal', chart);
      chart.setOption({
        grid: { left: 50, right: 16, top: 8, bottom: 28 },
        xAxis: { type: 'time', axisLabel: { color: muted, fontSize: 10 }, axisLine: { lineStyle: { color: 'rgba(128,128,128,0.2)' } }, splitLine: { show: false } },
        yAxis: { min: 0, max: 100, axisLabel: { color: muted, fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(128,128,128,0.1)' } } },
        series: [{
          type: 'line', data: pts, smooth: true, symbol: 'none',
          lineStyle: { width: 2, color: primary },
          areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(59,130,246,0.2)' }, { offset: 1, color: 'rgba(59,130,246,0.02)' }] } },
        }],
      });
    })
    .catch(() => {});
}

export function _makeBar(elId, labels, values, color, prefix) {
  if (!this._charts) this._charts = new Map();
  if (this._charts.has(elId)) this._disposeChart(this._charts.get(elId));
  const el = document.getElementById(elId);
  if (!el) return;
  const muted = _cssVar('--muted', '#9aa8c4');
  const chart = echarts.init(el);
  this._charts.set(elId, chart);
  chart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: p => `${p[0].name}<br/>${prefix}${Number(p[0].value).toLocaleString()}` },
    grid: { left: 120, right: 20, top: 8, bottom: 8 },
    xAxis: { type: 'value', axisLabel: { color: muted, fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(128,128,128,0.1)' } } },
    yAxis: { type: 'category', data: labels, axisLabel: { color: muted, fontSize: 10 }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: 'bar', data: values, itemStyle: { color, borderRadius: [0, 4, 4, 0] }, barMaxWidth: 16 }],
  });
}

export function renderSentimentChart(series) {
  if (!series || !series.length) return;
  const el = document.getElementById('chart-sentiment');
  if (!el) return;
  if (this._echarts?.has('chart-sentiment')) this._disposeChart(this._echarts.get('chart-sentiment'));
  const primary = _cssVar('--spark', '#60a5fa');
  const muted = _cssVar('--muted', '#9aa8c4');
  const chart = echarts.init(el);
  if (!this._echarts) this._echarts = new Map();
  this._echarts.set('chart-sentiment', chart);
  chart.setOption({
    grid: { left: 50, right: 16, top: 8, bottom: 28 },
    xAxis: { type: 'category', data: series.map(s => s.date), axisLabel: { color: muted, fontSize: 10 }, axisLine: { lineStyle: { color: 'rgba(128,128,128,0.2)' } } },
    yAxis: { min: -1, max: 1, axisLabel: { color: muted, fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(128,128,128,0.1)' } } },
    series: [{ type: 'line', data: series.map(s => s.avg_sentiment), smooth: true, symbol: 'none', lineStyle: { width: 2, color: primary }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(59,130,246,0.15)' }, { offset: 1, color: 'rgba(59,130,246,0.02)' }] } } }],
  });
}

export function renderForecastCharts() {
  if (typeof echarts === 'undefined') {
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js';
    s.onload = () => this._renderForecastChartsImpl();
    document.head.appendChild(s);
    return;
  }
  this._renderForecastChartsImpl();
}

export function _renderForecastChartsImpl() {
  const elPeg = document.getElementById('chart-peg-forecast');
  const elSupply = document.getElementById('chart-supply-forecast');
  if (!elPeg || !elSupply) return;
  const textColor = _cssVar('--text', '#e8edf7');
  const lineColor = _cssVar('--line', '#273247');
  const baseConfig = {
    tooltip: { trigger: 'axis' }, grid: { left: 50, right: 16, top: 20, bottom: 36 },
    xAxis: { type: 'time', axisLine: { lineStyle: { color: lineColor } }, axisLabel: { color: textColor } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: lineColor, opacity: 0.2 } }, axisLabel: { color: textColor } },
    legend: { bottom: 0, textStyle: { color: textColor, fontSize: 11 } },
  };
  const data = this._forecastData || {};
  const pegForecast = (data.forecast_points?.peg) || [];
  const pegHistorical = (data.historical?.peg) || [];
  const supplyForecast = (data.forecast_points?.supply) || [];
  const supplyHistorical = (data.historical?.supply) || [];
  _renderForecastCanvas.call(this, elPeg, 'Peg Forecast', pegHistorical, pegForecast, baseConfig, textColor, lineColor);
  _renderForecastCanvas.call(this, elSupply, 'Supply Forecast', supplyHistorical, supplyForecast, baseConfig, textColor, lineColor);
}

export function _renderForecastCanvas(el, title, historical, forecast, baseConfig, textColor, lineColor) {
  if (this._echarts?.has(el.id)) { this._disposeChart(this._echarts.get(el.id)); this._echarts?.delete(el.id); }
  const chart = echarts.init(el);
  if (this._echarts) this._echarts.set(el.id, chart);
  const isPeg = /peg/i.test(title);
  const muted = _cssVar('--muted', '#9aa8c4');
  const yAxis = isPeg
    ? {
        type: 'value',
        min: 0.85,
        max: 1.15,
        splitLine: { lineStyle: { color: lineColor, opacity: 0.2 } },
        axisLabel: { color: muted, fontSize: 10, formatter: v => Number(v).toFixed(4) },
      }
    : {
        type: 'value',
        splitLine: { lineStyle: { color: lineColor, opacity: 0.2 } },
        axisLabel: { color: muted, fontSize: 10, formatter: v => formatUsd(v) },
      };
  const series = forecast && forecast.length
    ? [
        { name: 'q10 base', type: 'line', data: forecast.map(p => [p.timestamp, p.q10 ?? p.q50 * 0.997]), lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 }, stack: 'confidence', areaStyle: { color: 'rgba(59,130,246,0.06)' }, symbol: 'none' },
        { name: '90% Band', type: 'line', data: forecast.map(p => [p.timestamp, Math.max(0, (p.q90 ?? p.q50) - p.q10)]), lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 }, stack: 'confidence', areaStyle: { color: 'rgba(59,130,246,0.08)' }, symbol: 'none' },
        { name: 'Median', type: 'line', data: forecast.map(p => [p.timestamp, p.q50]), lineStyle: { width: 2, color: '#3b82f6' }, symbol: 'none', z: 10 },
        { name: 'Historical', type: 'line', data: historical.map(p => [p.timestamp, p.value]), lineStyle: { width: 1.5, color: textColor }, symbolSize: 2, z: 10 },
      ]
    : [{ name: 'No forecast data', type: 'line', data: historical.map(p => [p.timestamp, p.value]), lineStyle: { width: 1.5, color: textColor }, symbolSize: 2, z: 10 }];
  chart.setOption({
    ...baseConfig,
    yAxis,
    title: { text: title, left: 'center', top: 0, textStyle: { color: textColor, fontSize: 13, fontWeight: 500 } },
    grid: { left: 50, right: 16, top: 36, bottom: 40 },
    series,
  });
}

export async function renderSupplyChart() {
  const tr = this.timeRange || '30d';
  const d = await fetch(`/api/trends?asset=${this.asset}&window=${tr}`, { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null);
  if (!d || !d.points || !d.points.length) return;
  const el = document.getElementById('chart-supply-trend');
  if (!el) return;
  if (this._echarts?.has('chart-supply-trend')) this._disposeChart(this._echarts.get('chart-supply-trend'));
  const pts = d.points.filter(p => p.total_supply != null).map(p => [new Date(p.timestamp).getTime(), Number(p.total_supply)]);
  const primary = _cssVar('--spark', '#60a5fa');
  const muted = _cssVar('--muted', '#9aa8c4');
  const chart = echarts.init(el);
  if (!this._echarts) this._echarts = new Map();
  this._echarts.set('chart-supply-trend', chart);
  chart.setOption({
    grid: { left: 60, right: 16, top: 8, bottom: 28 },
    xAxis: { type: 'time', axisLabel: { color: muted, fontSize: 10, formatter: v => formatDate(v, 'axis') }, axisLine: { lineStyle: { color: 'rgba(128,128,128,0.2)' } }, splitLine: { show: false } },
    yAxis: { type: 'value', axisLabel: { color: muted, fontSize: 10, formatter: v => formatUsd(v) }, splitLine: { lineStyle: { color: 'rgba(128,128,128,0.1)' } } },
    series: [{ type: 'line', data: pts, smooth: true, symbol: 'none', lineStyle: { width: 2, color: primary }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(59,130,246,0.2)' }, { offset: 1, color: 'rgba(59,130,246,0.02)' }] } } }],
  });
}

export function resizeAllHelixCharts() {
  requestAnimationFrame(() => {
    try {
      for (const id of document.querySelectorAll('[id^="chart-"]')) {
        const inst = echarts.getInstanceByDom(id);
        if (inst && !inst.isDisposed()) inst.resize();
      }
    } catch (e) { /* resize guard */ }
  });
}

export function renderRiskTerminalChart(predictive) {
  const el = document.getElementById('chart-risk-terminal');
  if (!el || typeof echarts === 'undefined') return;
  const probs = predictive?.depeg_probability || {};
  const horizons = [
    ['1h', probs.horizon_1h],
    ['6h', probs.horizon_6h],
    ['24h', probs.horizon_24h],
  ].filter(([, v]) => v != null);
  if (!horizons.length) return;
  const muted = _cssVar('--muted', '#9aa8c4');
  const primary = _cssVar('--spark', '#60a5fa');
  const warn = _cssVar('--warn', '#f59e0b');
  const chart = echarts.getInstanceByDom(el) || echarts.init(el);
  chart.setOption({
    grid: { left: 36, right: 8, top: 8, bottom: 24 },
    xAxis: {
      type: 'category',
      data: horizons.map(([h]) => h),
      axisLabel: { color: muted, fontSize: 10 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: { color: muted, fontSize: 10, formatter: '{value}%' },
      splitLine: { lineStyle: { color: 'rgba(128,128,128,0.1)' } },
    },
    series: [{
      type: 'bar',
      data: horizons.map(([, v]) => Math.min(100, Number(v) * 100)),
      itemStyle: {
        color: (p) => (p.value > 50 ? warn : primary),
        borderRadius: [4, 4, 0, 0],
      },
      barMaxWidth: 28,
    }],
  }, true);
}

export function renderContagionGraph(rotation) {
  const el = document.getElementById('chart-contagion');
  if (!el || typeof echarts === 'undefined') return;
  const pairs = rotation?.pairs || [];
  if (!pairs.length) return;
  const nodes = new Map();
  const links = [];
  const collateral = { 'DAI': 'USDC', 'FRAX': 'USDC', 'PYUSD': 'USDC' };
  for (const p of pairs) {
    nodes.set(p.asset_a, { name: p.asset_a, symbolSize: 36 });
    nodes.set(p.asset_b, { name: p.asset_b, symbolSize: 36 });
    links.push({
      source: p.asset_a,
      target: p.asset_b,
      value: Math.abs(p.correlation_7d || 0),
      lineStyle: {
        width: 1 + Math.abs(p.correlation_7d || 0) * 4,
        color: (p.correlation_7d || 0) > 0 ? '#22c55e' : '#ef4444',
      },
      label: { show: true, formatter: `r=${(p.correlation_7d || 0).toFixed(2)}` },
    });
    if (collateral[p.asset_a] === p.asset_b || collateral[p.asset_b] === p.asset_a) {
      const a = collateral[p.asset_a] ? p.asset_a : p.asset_b;
      const b = collateral[p.asset_a] ? p.asset_b : p.asset_a;
      links.push({
        source: a,
        target: b,
        value: 0.9,
        lineStyle: { type: 'dashed', color: '#f59e0b', width: 2 },
        label: { show: true, formatter: 'collateral' },
      });
    }
  }
  const textColor = _cssVar('--text', '#e8edf7');
  const chart = echarts.getInstanceByDom(el) || echarts.init(el);
  chart.setOption({
    tooltip: {},
    series: [{
      type: 'graph',
      layout: 'circular',
      roam: true,
      label: { show: true, color: textColor, fontSize: 11 },
      data: [...nodes.values()],
      links,
      lineStyle: { curveness: 0.2, opacity: 0.85 },
    }],
  }, true);
}

export function reserveGrade(att) {
  if (!att) return { grade: 'N/A', score: 0 };
  if (att.attestation_status === 'n/a') return { grade: 'C', score: 50, note: 'On-chain only' };
  const age = att.attestation_age_days;
  if (age == null) return { grade: 'D', score: 35, note: 'No report date' };
  if (age < 45) return { grade: 'A', score: 95, note: 'Fresh attestation' };
  if (age < 90) return { grade: 'B', score: 80, note: 'Recent report' };
  if (age < 180) return { grade: 'C', score: 60, note: 'Aging report' };
  return { grade: 'D', score: 35, note: 'Stale report' };
}

export function destroySmidgeChart() {
  if (!this._smidgeChart) return;
  _disposeChart(this._smidgeChart);
  this._smidgeChart = null;
}

export function renderSmidgeRadar(smidge) {
  if (!smidge?.available || typeof echarts === 'undefined') return;
  const el = document.getElementById('chart-smidge-radar');
  if (!el) return;
  destroySmidgeChart.call(this);
  const dims = smidge.dimensions || {};
  const order = ['S', 'M', 'I', 'D', 'G', 'E'];
  const indicators = order.map(k => ({ name: k, max: 100 }));
  const values = order.map(k => dims[k] ?? 0);
  const textColor = _cssVar('--text', '#e8edf7');
  const chart = echarts.init(el);
  this._smidgeChart = chart;
  chart.setOption({
    radar: {
      indicator: indicators,
      axisName: { color: textColor, fontSize: 12 },
      splitLine: { lineStyle: { color: 'rgba(128,128,128,0.2)' } },
    },
    series: [{
      type: 'radar',
      data: [{ value: values, name: smidge.asset_symbol, areaStyle: { color: 'rgba(59,130,246,0.15)' }, lineStyle: { color: '#3b82f6' } }],
    }],
  });
}
