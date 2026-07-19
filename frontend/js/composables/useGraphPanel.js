import { formatUsd, formatWhen } from '../utils.js';

const LABEL_COLORS = [
  '#3b82f6', '#34d399', '#fbbf24', '#f87171', '#a78bfa', '#2dd4bf',
];

const CATEGORIES = [
  { name: 'Seed', itemStyle: { color: '#3b82f6', borderColor: '#1d4ed8', borderWidth: 3 } },
  { name: 'Peel Hop', itemStyle: { color: '#34d399', borderColor: '#059669', borderWidth: 2 } },
  { name: 'Cluster', itemStyle: { color: '#fbbf24', borderColor: '#d97706', borderWidth: 1 } },
  { name: 'Bridge', itemStyle: { color: '#a78bfa', borderColor: '#7c3aed', borderWidth: 1 } },
  { name: 'Blacklist', itemStyle: { color: '#f87171', borderColor: '#dc2626', borderWidth: 2 } },
  { name: 'OSINT', itemStyle: { color: '#2dd4bf', borderColor: '#0d9488', borderWidth: 1 } },
];

function _shortAddr(addr) {
  if (!addr || addr.length < 10) return addr || '?';
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

function _buildGraphData(report) {
  if (!report) return { nodes: [], edges: [], categories: CATEGORIES };

  const nodes = [];
  const edges = [];
  const nodeMap = new Map();
  const seedAddr = report.seed_address;

  function addNode(id, name, category, extra = {}) {
    if (nodeMap.has(id)) return nodeMap.get(id);
    const node = {
      id,
      name: name || _shortAddr(id),
      category,
      value: id,
      symbolSize: category === 0 ? 40 : category === 4 ? 28 : 24,
      itemStyle: { ...CATEGORIES[category].itemStyle, ...(extra.itemStyle || {}) },
      emphasis: { scale: 1.4 },
      _raw: extra,
    };
    nodeMap.set(id, node);
    nodes.push(node);
    return node;
  }

  addNode(seedAddr, `${_shortAddr(seedAddr)} (seed)`, 0, {
    symbolSize: 48,
    label: { show: true, fontSize: 11, fontWeight: 700 },
  });

  for (const hop of (report.peel_hops || [])) {
    const hopAddr = hop.address || hop.to_address || hop.from_address;
    if (!hopAddr) continue;
    const hopNode = addNode(hopAddr, null, 1, { hop });
    edges.push({
      source: seedAddr,
      target: hopAddr,
      value: hop.value_usd || hop.value || 0,
      lineStyle: { color: '#34d399', width: Math.max(1, Math.min(8, (hop.value_usd || 0) / 100000)) },
      label: { show: true, formatter: hop.value_usd ? formatUsd(hop.value_usd) : '', fontSize: 9 },
    });
  }

  const clusterAddrs = report.cluster?.addresses || report.cluster?.members || [];
  for (const addr of (typeof clusterAddrs[0] === 'string' ? clusterAddrs : clusterAddrs.map(a => a.address || a).filter(Boolean))) {
    if (addr === seedAddr || nodeMap.has(addr)) continue;
    addNode(addr, null, 2);
    edges.push({
      source: seedAddr,
      target: addr,
      lineStyle: { color: '#fbbf24', width: 1, type: 'dashed' },
      label: { show: false },
    });
  }

  for (const hop of (report.bridge_hops || [])) {
    const src = hop.from_address || hop.source_address;
    const tgt = hop.to_address || hop.dest_address;
    if (!src || !tgt) continue;
    addNode(src, null, 3, { hop });
    addNode(tgt, null, 3, { hop });
    edges.push({
      source: src,
      target: tgt,
      value: hop.value_usd || hop.value || 0,
      lineStyle: { color: '#a78bfa', width: 2 },
      label: { show: true, formatter: `bridge ${hop.chain || ''}`, fontSize: 8 },
    });
  }

  for (const hit of (report.blacklist_hits || [])) {
    const addr = hit.address || hit.frozen_address;
    if (!addr) continue;
    addNode(addr, null, 4, { hit });
    edges.push({
      source: seedAddr,
      target: addr,
      lineStyle: { color: '#f87171', width: 2, type: 'dotted' },
      label: { show: false },
    });
  }

  for (const art of (report.osint_articles || [])) {
    const artId = `osint-${art.id || art.url || Math.random().toString(36).slice(2, 8)}`;
    addNode(artId, art.source || 'OSINT', 5, { article: art, symbolSize: 16 });
    const addr = art.addresses?.[0] || art.related_address;
    if (addr && nodeMap.has(addr)) {
      edges.push({
        source: addr,
        target: artId,
        lineStyle: { color: '#2dd4bf', width: 1, type: 'dashed' },
      });
    }
  }

  return { nodes, edges, categories: CATEGORIES };
}

function _nodeTooltipHtml(nodeData, report) {
  const raw = nodeData._raw || {};
  const category = nodeData.category;
  const id = nodeData.id;
  let html = `<strong>${_shortAddr(id)}</strong>`;

  if (category === 0) {
    html += `<br/>Seed address`;
    html += `<br/>Chain: ${report.chain || '?'}`;
    html += `<br/>Asset: ${report.asset_symbol || '?'}`;
    html += `<br/>Risk: ${report.risk_level || '?'}`;
    if (report.total_value_usd != null) html += `<br/>Total traced: ${formatUsd(report.total_value_usd)}`;
  }
  if (raw.hop) {
    const h = raw.hop;
    html += `<br/>Value: ${h.value_usd ? formatUsd(h.value_usd) : h.value || '?'}`;
    html += `<br/>Chain: ${h.chain || '?'}`;
    if (h.tx_hash) html += `<br/>Tx: ${_shortAddr(h.tx_hash)}`;
    if (h.timestamp) html += `<br/>${formatWhen(h.timestamp)}`;
  }
  if (category === 2) {
    html += `<br/>Clustered address`;
    if (report.cluster?.cluster_id) html += `<br/>Cluster: ${report.cluster.cluster_id}`;
  }
  if (raw.hit) {
    const hit = raw.hit;
    html += `<br/><span style="color:#f87171;font-weight:700">BLACKLIST HIT</span>`;
    html += `<br/>Asset: ${hit.asset_symbol || '?'}`;
    if (hit.frozen_balance_usd) html += `<br/>Frozen: ${formatUsd(hit.frozen_balance_usd)}`;
    if (hit.event_type) html += `<br/>Type: ${hit.event_type}`;
    if (hit.intelligence_note) html += `<br/>Note: ${hit.intelligence_note}`;
  }
  if (raw.article) {
    const art = raw.article;
    html += `<br/>Source: ${art.source || '?'}`;
    if (art.title) html += `<br/>${art.title}`;
    if (art.url) html += `<br/><a href="${art.url}" target="_blank" style="color:#60a5fa">Read →</a>`;
  }
  return html;
}

export function renderInvestigationGraph(report, containerId = 'graph-investigation') {
  const dom = document.getElementById(containerId);
  if (!dom) return null;

  let chart;
  try {
    chart = echarts.getInstanceByDom(dom);
    if (chart) chart.dispose();
  } catch (e) {}
  chart = echarts.init(dom, null, { renderer: 'canvas' });

  const graphData = _buildGraphData(report);
  if (!graphData.nodes.length) {
    chart.setOption({
      title: { text: 'No graph data available', left: 'center', top: 'center', textStyle: { color: '#9aa8c4', fontSize: 14 } },
    });
    return chart;
  }

  const seedAddr = report.seed_address;
  const option = {
    title: {
      text: `Investigation: ${_shortAddr(seedAddr)}`,
      subtext: `${report.asset_symbol || ''} · ${report.chain || ''} · risk: ${report.risk_level || '?'}`,
      left: 'center',
      top: 4,
      textStyle: { color: '#e8edf7', fontSize: 14, fontWeight: 600 },
      subtextStyle: { color: '#9aa8c4', fontSize: 11 },
    },
    tooltip: {
      trigger: 'item',
      formatter: (p) => {
        if (p.dataType === 'node') return _nodeTooltipHtml(p.data, report);
        if (p.dataType === 'edge') return `Value: ${p.data.value ? formatUsd(p.data.value) : '?'}`;
        return p.name;
      },
    },
    legend: [{
      data: CATEGORIES.map(c => c.name),
      top: 50,
      textStyle: { color: '#9aa8c4', fontSize: 11 },
    }],
    animationDuration: 800,
    animationEasingUpdate: 'cubicOut',
    series: [{
      type: 'graph',
      layout: 'force',
      force: { repulsion: 500, edgeLength: [80, 200], gravity: 0.1, friction: 0.1, layoutAnimation: false },
      roam: true,
      draggable: true,
      data: graphData.nodes,
      edges: graphData.edges,
      categories: graphData.categories,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 10],
      lineStyle: { color: 'source', curveness: 0.3, opacity: 0.7 },
      label: { show: true, position: 'bottom', color: '#9aa8c4', fontSize: 9 },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 3 },
      },
      blur: { opacity: 0.2 },
      edgeLabel: { fontSize: 8, color: '#6b7a99' },
    }],
  };

  chart.setOption(option);
  chart.on('click', (params) => {
    if (params.dataType === 'node' && params.data) {
      window.dispatchEvent(new CustomEvent('graph-node-click', { detail: { node: params.data, report } }));
    }
  });

  return chart;
}

export function exportGraphPNG(chart, filename = 'helix-investigation-graph.png') {
  if (!chart) return;
  const url = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#121826' });
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
}

export function destroyGraph(chart) {
  if (chart) {
    try { chart.dispose(); } catch (e) {}
  }
}

function _collectTimeline(report) {
  const events = [];
  for (const hop of (report.peel_hops || [])) {
    if (hop.timestamp || hop.block_time) {
      events.push({
        time: new Date(hop.timestamp || hop.block_time).getTime(),
        label: 'Peel Hop',
        value: hop.value_usd || hop.value || 0,
        detail: `${_shortAddr(hop.address || hop.to_address || '')} · ${formatUsd(hop.value_usd || hop.value || 0)}`,
        category: 0,
      });
    }
  }
  for (const hit of (report.blacklist_hits || [])) {
    if (hit.timestamp) {
      events.push({
        time: new Date(hit.timestamp).getTime(),
        label: 'Blacklist',
        value: hit.frozen_balance_usd || 0,
        detail: `${hit.asset_symbol || ''} · ${formatUsd(hit.frozen_balance_usd || 0)}`,
        category: 1,
      });
    }
  }
  for (const art of (report.osint_articles || [])) {
    if (art.published_at) {
      events.push({
        time: new Date(art.published_at).getTime(),
        label: 'OSINT',
        value: 0,
        detail: `${art.source || ''}: ${(art.title || '').slice(0, 50)}`,
        category: 2,
      });
    }
  }
  events.sort((a, b) => a.time - b.time);
  return events;
}

export function renderInvestigationSankey(report, containerId = 'graph-sankey') {
  const dom = document.getElementById(containerId);
  if (!dom) return null;
  let chart;
  try { chart = echarts.getInstanceByDom(dom); if (chart) chart.dispose(); } catch (e) {}
  chart = echarts.init(dom, null, { renderer: 'canvas' });

  const seedAddr = report.seed_address;
  const nodes = [];
  const links = [];
  const nodeSet = new Set();

  function addSankeyNode(id, label) {
    if (nodeSet.has(id)) return;
    nodeSet.add(id);
    nodes.push({ name: id, label: { show: true, formatter: _shortAddr(id), fontSize: 10 } });
  }

  addSankeyNode(seedAddr, 'Seed');
  for (const hop of (report.peel_hops || [])) {
    const addr = hop.address || hop.to_address;
    if (!addr) continue;
    addSankeyNode(addr);
    links.push({ source: seedAddr, target: addr, value: Math.round((hop.value_usd || hop.value || 1) / 100) || 1 });
  }
  for (const hop of (report.bridge_hops || [])) {
    const src = hop.from_address || hop.source_address;
    const tgt = hop.to_address || hop.dest_address;
    if (!src || !tgt) continue;
    addSankeyNode(src);
    addSankeyNode(tgt);
    links.push({ source: src, target: tgt, value: Math.round((hop.value_usd || hop.value || 1) / 100) || 1 });
  }

  if (nodes.length < 2) {
    chart.setOption({ title: { text: 'Not enough flow data for Sankey', left: 'center', top: 'center', textStyle: { color: '#9aa8c4', fontSize: 14 } } });
    return chart;
  }

  chart.setOption({
    title: { text: 'Fund Flow (Sankey)', left: 'center', top: 4, textStyle: { color: '#e8edf7', fontSize: 14, fontWeight: 600 } },
    tooltip: { trigger: 'item', formatter: (p) => `${_shortAddr(p.name)}<br/>Value: ${formatUsd(p.value * 100)}` },
    series: [{
      type: 'sankey',
      layout: 'none',
      emphasis: { focus: 'adjacency' },
      nodeAlign: 'left',
      nodeWidth: 16,
      nodeGap: 10,
      lineStyle: { color: 'gradient', curveness: 0.5 },
      data: nodes,
      links,
    }],
  });

  return chart;
}

export function renderInvestigationTimeline(report, containerId = 'graph-timeline') {
  const dom = document.getElementById(containerId);
  if (!dom) return null;
  let chart;
  try { chart = echarts.getInstanceByDom(dom); if (chart) chart.dispose(); } catch (e) {}
  chart = echarts.init(dom, null, { renderer: 'canvas' });

  const events = _collectTimeline(report);
  if (!events.length) {
    chart.setOption({ title: { text: 'No timeline events', left: 'center', top: 'center', textStyle: { color: '#9aa8c4', fontSize: 14 } } });
    return chart;
  }

  const colors = ['#34d399', '#f87171', '#2dd4bf'];
  const scatterData = events.map((e, i) => ({
    value: [e.time, i, e.value],
    name: e.detail,
    itemStyle: { color: colors[e.category] },
    symbolSize: Math.max(8, Math.min(24, e.value / 10000)),
  }));

  chart.setOption({
    title: { text: 'Event Timeline', left: 'center', top: 4, textStyle: { color: '#e8edf7', fontSize: 14, fontWeight: 600 } },
    tooltip: { trigger: 'item', formatter: (p) => `${formatWhen(p.value[0])}<br/>${p.name}` },
    grid: { left: 60, right: 20, top: 50, bottom: 40 },
    xAxis: {
      type: 'time',
      axisLabel: { color: '#9aa8c4', fontSize: 10 },
      axisLine: { lineStyle: { color: getComputedStyle(document.documentElement).getPropertyValue('--line').trim() || '#273247' } },
      splitLine: { lineStyle: { color: getComputedStyle(document.documentElement).getPropertyValue('--line').trim() || '#273247', opacity: 0.35 } },
    },
    yAxis: {
      type: 'category',
      data: events.map(() => ''),
      axisLabel: { show: false },
      axisLine: { show: false },
      splitLine: { show: false },
    },
    series: [{
      type: 'scatter',
      data: scatterData,
      label: { show: true, formatter: (p) => p.name, position: 'right', color: '#9aa8c4', fontSize: 9 },
      emphasis: { scale: 1.5 },
    }],
  });

  return chart;
}

export function renderClusterBubbles(report, containerId = 'graph-cluster') {
  const dom = document.getElementById(containerId);
  if (!dom) return null;
  let chart;
  try { chart = echarts.getInstanceByDom(dom); if (chart) chart.dispose(); } catch (e) {}
  chart = echarts.init(dom, null, { renderer: 'canvas' });

  const clusterAddrs = report.cluster?.addresses || report.cluster?.members || [];
  const addrs = typeof clusterAddrs[0] === 'string' ? clusterAddrs : clusterAddrs.map(a => a.address || a).filter(Boolean);
  const blacklistAddrs = new Set((report.blacklist_hits || []).map(h => h.address || h.frozen_address).filter(Boolean));

  const data = [];
  const known = new Set();
  for (const addr of addrs) {
    if (known.has(addr)) continue;
    known.add(addr);
    data.push({
      name: addr,
      value: blacklistAddrs.has(addr) ? 30 : 15,
      itemStyle: { color: blacklistAddrs.has(addr) ? '#f87171' : '#fbbf24' },
      label: { show: true, formatter: _shortAddr(addr), fontSize: 9, color: '#e8edf7' },
    });
  }

  if (!data.length) {
    chart.setOption({ title: { text: 'No cluster data', left: 'center', top: 'center', textStyle: { color: '#9aa8c4', fontSize: 14 } } });
    return chart;
  }

  chart.setOption({
    title: {
      text: 'Cluster Members',
      subtext: `${data.length} addresses · red = blacklist hit`,
      left: 'center', top: 4,
      textStyle: { color: '#e8edf7', fontSize: 14, fontWeight: 600 },
      subtextStyle: { color: '#9aa8c4', fontSize: 11 },
    },
    tooltip: { trigger: 'item', formatter: (p) => `${p.name}<br/>${p.value > 20 ? 'Blacklist hit' : 'Clustered'}` },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      data,
      edges: [],
      force: { repulsion: 200, edgeLength: 0, gravity: 0.3, layoutAnimation: false },
      emphasis: { scale: 1.3, focus: 'adjacency' },
      label: { show: true, position: 'bottom', color: '#9aa8c4', fontSize: 9 },
      lineStyle: { opacity: 0 },
    }],
  });

  return chart;
}
