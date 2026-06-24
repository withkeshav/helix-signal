import { formatUsd, formatDate } from './utils.js';

export function _disposeChart(c) {
  if (!c) return;
  if (typeof c.dispose === 'function') {
    if (typeof c.isDisposed !== 'function' || !c.isDisposed()) c.dispose();
  } else if (typeof c.destroy === 'function') {
    c.destroy();
  }
}

export function destroyCharts() {
  if (!this._charts) return;
  for (const [, c] of this._charts) this._disposeChart(c);
  this._charts.clear();
}

export function destroyForecastCharts() {
  if (!this._echarts) return;
  for (const [, c] of this._echarts) this._disposeChart(c);
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
      if (this._charts) {
        for (const [id, c] of this._charts) {
          try {
            const el = document.getElementById(id);
            if (el && el.ownerDocument && typeof c.resize === 'function') c.resize();
          } catch (e) { /* chart resize guard */ }
        }
      }
      if (this._echarts) {
        for (const [, c] of this._echarts) {
          try {
            if (typeof c.isDisposed === 'function' && !c.isDisposed()) c.resize();
          } catch (e) { /* echarts resize guard */ }
        }
      }
    } catch (e) { /* resize handler guard */ }
  };
  window.addEventListener('resize', window._helixResizeHandler);
}

export function renderCharts(data) {
  if (!this._charts) this._charts = new Map();
  this.destroyCharts();
  if (typeof Chart === 'undefined') return;
  const primary = getComputedStyle(document.documentElement).getPropertyValue('--spark').trim() || '#60a5fa';
  const chains = data.chains || [];
  if (chains.length) {
    const sorted = [...chains].sort((a, b) => Number(b.chain_share_pct || 0) - Number(a.chain_share_pct || 0)).slice(0, 12);
    const labels = sorted.map(c => c.chain_name);
    const vals = sorted.map(c => c.chain_share_pct || 0);
    const supplyVals = sorted.map(c => c.supply_current || 0);
    this._makeBar('chart-distribution', labels, vals, primary);
    this._makeBar('chart-supply-bar', labels, supplyVals, primary);
  }
  this.loadTrendChart();
}

export function loadTrendChart() {
  const _asset = this.asset;
  try {
    const muted = getComputedStyle(document.documentElement).getPropertyValue('--muted').trim() || '#9aa8c4';
    const primary = getComputedStyle(document.documentElement).getPropertyValue('--spark').trim() || '#60a5fa';
    const tr = this.timeRange || '7d';
    fetch(`/api/trends?asset=${this.asset}&window=${tr}`, { cache: 'no-store' })
      .then(r => r.ok ? r.json() : null)
      .then(t => {
        if (this.asset !== _asset) return;
        if (!t || !t.points || !t.points.length || typeof Chart === 'undefined') return;
        const el = document.getElementById('chart-trend-signal');
        if (!el) return;
        if (this._charts.has('chart-trend-signal')) this._disposeChart(this._charts.get('chart-trend-signal'));
        if (typeof Chart.getChart === 'function') Chart.getChart('chart-trend-signal')?.destroy();
        const pts = t.points.map(p => ({ x: new Date(p.timestamp).getTime(), y: p.signal_score != null ? Number(p.signal_score) : null }));
        this._charts.set('chart-trend-signal', new Chart(el.getContext('2d'), {
          type: 'line',
          data: { datasets: [{ data: pts, borderColor: primary, backgroundColor: 'rgba(59,130,246,0.08)', fill: true, tension: 0.25, pointRadius: 0, borderWidth: 2 }] },
          options: {
            responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } },
            scales: {
              x: {
                type: 'linear',
                ticks: {
                  color: muted,
                  maxTicksLimit: 8,
                  callback: (v) => formatDate(v, 'axis'),
                },
                grid: { color: 'rgba(128,128,128,0.1)' },
              },
              y: { min: 0, max: 100, ticks: { color: muted }, grid: { color: 'rgba(128,128,128,0.1)' } },
            },
          },
        }));
      })
      .catch(() => {});
  } catch (e) {}
}

export function _makeBar(canvasId, labels, values, color) {
  if (!this._charts) this._charts = new Map();
  if (this._charts.has(canvasId)) this._disposeChart(this._charts.get(canvasId));
  const el = document.getElementById(canvasId);
  if (!el || typeof Chart === 'undefined') return;
  if (typeof Chart.getChart === 'function') Chart.getChart(canvasId)?.destroy();
  const muted = getComputedStyle(document.documentElement).getPropertyValue('--muted').trim() || '#9aa8c4';
  this._charts.set(canvasId, new Chart(el.getContext('2d'), {
    type: 'bar', data: { labels, datasets: [{ label: '', data: values, backgroundColor: color, borderRadius: 4 }] },
    options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: muted }, grid: { color: 'rgba(128,128,128,0.1)' } }, y: { ticks: { color: muted }, grid: { color: 'rgba(128,128,128,0.1)' } } } },
  }));
}

export function renderSentimentChart(series) {
  if (!series || !series.length || typeof Chart === 'undefined') return;
  if (this._charts.has('chart-sentiment')) this._disposeChart(this._charts.get('chart-sentiment'));
  if (typeof Chart.getChart === 'function') Chart.getChart('chart-sentiment')?.destroy();
  const el = document.getElementById('chart-sentiment');
  if (!el) return;
  const primary = getComputedStyle(document.documentElement).getPropertyValue('--spark').trim() || '#60a5fa';
  this._charts.set('chart-sentiment', new Chart(el.getContext('2d'), {
    type: 'line',
    data: { labels: series.map(s => s.date), datasets: [{ label: 'Avg Sentiment', data: series.map(s => s.avg_sentiment), borderColor: primary, fill: false, tension: 0.25 }] },
    options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } }, scales: { y: { min: -1, max: 1 } } },
  }));
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
  const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#e8edf7';
  const lineColor = getComputedStyle(document.documentElement).getPropertyValue('--line').trim() || '#273247';
  const baseConfig = {
    tooltip: { trigger: 'axis' }, grid: { left: 50, right: 16, top: 20, bottom: 36 },
    xAxis: { type: 'time', axisLine: { lineStyle: { color: lineColor } }, axisLabel: { color: textColor } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: lineColor, opacity: 0.2 } }, axisLabel: { color: textColor } },
    legend: { bottom: 0, textStyle: { color: textColor, fontSize: 11 } },
    animation: false,
  };
  const data = this._forecastData || {};
  const pegForecast = (data.forecast_points?.peg) || [];
  const pegHistorical = (data.historical?.peg) || [];
  const supplyForecast = (data.forecast_points?.supply) || [];
  const supplyHistorical = (data.historical?.supply) || [];
  this._renderForecastCanvas(elPeg, 'Peg Forecast', pegHistorical, pegForecast, baseConfig, textColor, lineColor);
  this._renderForecastCanvas(elSupply, 'Supply Forecast', supplyHistorical, supplyForecast, baseConfig, textColor, lineColor);
}

export function _renderForecastCanvas(el, title, historical, forecast, baseConfig, textColor, lineColor) {
  if (this._echarts?.has(el.id)) { this._disposeChart(this._echarts.get(el.id)); this._echarts?.delete(el.id); }
  const chart = echarts.init(el);
  if (this._echarts) this._echarts.set(el.id, chart);
  const series = forecast && forecast.length
    ? [
        { name: 'q10 base', type: 'line', data: forecast.map(p => [p.timestamp, p.q10 ?? p.q50 * 0.997]), lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 }, stack: 'confidence', areaStyle: { color: 'rgba(59,130,246,0.06)' }, symbol: 'none' },
        { name: '90% Band', type: 'line', data: forecast.map(p => [p.timestamp, Math.max(0, (p.q90 ?? p.q50) - p.q10)]), lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 }, stack: 'confidence', areaStyle: { color: 'rgba(59,130,246,0.08)' }, symbol: 'none' },
        { name: 'Median', type: 'line', data: forecast.map(p => [p.timestamp, p.q50]), lineStyle: { width: 2, color: '#3b82f6' }, symbol: 'none', z: 10 },
        { name: 'Historical', type: 'line', data: historical.map(p => [p.timestamp, p.value]), lineStyle: { width: 1.5, color: textColor }, symbolSize: 2, z: 10 },
      ]
    : [{ name: 'No forecast data', type: 'line', data: historical.map(p => [p.timestamp, p.value]), lineStyle: { width: 1.5, color: textColor }, symbolSize: 2, z: 10 }];
  chart.setOption({ ...baseConfig,
    title: { text: title, left: 'center', top: 0, textStyle: { color: textColor, fontSize: 13, fontWeight: 500 } },
    grid: { left: 50, right: 16, top: 36, bottom: 40 },
    series,
  });
}

export async function renderSupplyChart() {
  const tr = this.timeRange || '30d';
  const d = await fetch(`/api/trends?asset=${this.asset}&window=${tr}`, { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null);
  if (!d || !d.points || !d.points.length || typeof Chart === 'undefined') return;
  const el = document.getElementById('chart-supply-trend');
  if (!el) return;
  if (this._charts.has('chart-supply-trend')) this._disposeChart(this._charts.get('chart-supply-trend'));
  if (typeof Chart.getChart === 'function') Chart.getChart('chart-supply-trend')?.destroy();
  const pts = d.points.filter(p => p.total_supply != null).map(p => ({ x: new Date(p.timestamp).getTime(), y: Number(p.total_supply) }));
  const primary = getComputedStyle(document.documentElement).getPropertyValue('--spark').trim() || '#60a5fa';
  this._charts.set('chart-supply-trend', new Chart(el.getContext('2d'), {
    type: 'line',
    data: { datasets: [{ data: pts, borderColor: primary, backgroundColor: 'rgba(59,130,246,0.08)', fill: true, tension: 0.25, pointRadius: 0, borderWidth: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } }, scales: { x: { type: 'linear', ticks: { maxTicksLimit: 8, callback: v => formatDate(v, 'axis') }, grid: { display: false } }, y: { ticks: { callback: v => formatUsd(v) } } } },
  }));
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
  const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#e8edf7';
  const chart = echarts.init(el);
  this._smidgeChart = chart;
  chart.setOption({
    animation: false,
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
