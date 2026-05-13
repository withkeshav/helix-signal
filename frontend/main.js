const API_ROOT = "http://localhost:8000";
const API_URL = `${API_ROOT}/api/dashboard`;
const REFRESH_URL = `${API_ROOT}/api/refresh`;
const stateEl = document.getElementById("app-state");
const rowsEl = document.getElementById("chain-rows");
const sourceFooterEl = document.getElementById("source-footer");
const refreshBtn = document.getElementById("refresh-btn");
const themeBtn = document.getElementById("theme-btn");
const freshnessPill = document.getElementById("freshness-pill");
const updatedPill = document.getElementById("updated-pill");
const staleWarningEl = document.getElementById("stale-warning");
const titleEl = document.getElementById("dashboard-title");
const subtitleEl = document.getElementById("dashboard-subtitle");
const supplyColHeaderEl = document.getElementById("supply-col-header");
const assetSelectorEl = document.getElementById("asset-selector");
const chainCountPillEl = document.getElementById("chain-count-pill");
const kpiSectionEl = document.getElementById("kpi-section");
const signalSummaryEl = document.getElementById("signal-summary");
const signalMethodEl = document.getElementById("signal-method");
const depegPanelEl = document.getElementById("depeg-panel");
const depegNoteEl = document.getElementById("depeg-note");
const concentrationPanelEl = document.getElementById("concentration-panel");
const trendLowDataEl = document.getElementById("trend-low-data");
const trendWindowPillsEl = document.getElementById("trend-window-pills");
const trendCoverageEl = document.getElementById("trend-coverage");
const trendAxisCaptionEl = document.getElementById("trend-axis-caption");
const eventFeedListEl = document.getElementById("event-feed-list");
const eventShowSystemEl = document.getElementById("event-show-system");

const charts = new Map();
let isLoading = false;
let lastData = null;
let trendWindow = "7d";
let lastTrendBundle = null;
let lastRawEvents = [];
let currentTheme = "auto";
let selectedAsset = "USDT";
let enabledAssets = [];

function formatUsd(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "N/A";
  }
  const num = Number(value);
  if (Math.abs(num) >= 1e9) return `$${(num / 1e9).toFixed(2)}B`;
  if (Math.abs(num) >= 1e6) return `$${(num / 1e6).toFixed(2)}M`;
  return `$${num.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function formatUsdFull(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "N/A";
  }
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatAgeSeconds(sec) {
  if (sec === null || sec === undefined || !Number.isFinite(Number(sec))) return "N/A";
  const s = Number(sec);
  if (s < 120) return `${Math.round(s)}s`;
  if (s < 7200) return `${Math.round(s / 60)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

function calcPercent(current, previous) {
  if (!previous || previous === 0) return null;
  return ((current - previous) / previous) * 100;
}

function deltaClass(changePct) {
  if (changePct === null) return "delta-flat";
  if (changePct > 0) return "delta-up";
  if (changePct < 0) return "delta-down";
  return "delta-flat";
}

function signalBadge(changePct) {
  if (changePct === null) return "";
  if (changePct > 1) return '<span class="signal-badge badge-growth">Growth</span>';
  if (changePct < -1) return '<span class="signal-badge badge-contraction">Contraction</span>';
  return "";
}

function pegStatus(price) {
  if (typeof price !== "number") return { label: "Unavailable", className: "peg-watch" };
  const deviation = Math.abs(price - 1);
  if (deviation <= 0.001) return { label: `Healthy (${price.toFixed(4)})`, className: "peg-ok" };
  if (deviation <= 0.005) return { label: `Watch (${price.toFixed(4)})`, className: "peg-watch" };
  return { label: `Alert (${price.toFixed(4)})`, className: "peg-alert" };
}

function bandClass(band) {
  if (band === "Risk") return "band-risk";
  if (band === "Watch") return "band-watch";
  return "band-normal";
}

function resolveCurrentTheme() {
  if (currentTheme === "auto") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return currentTheme;
}

function applyTheme(theme) {
  currentTheme = theme;
  localStorage.setItem("helix-theme", theme);
  const effectiveTheme = resolveCurrentTheme();
  document.documentElement.setAttribute("data-theme", effectiveTheme);
  themeBtn.textContent = `Theme: ${theme[0].toUpperCase()}${theme.slice(1)}`;
}

function cycleTheme() {
  const order = ["auto", "light", "dark"];
  const idx = order.indexOf(currentTheme);
  applyTheme(order[(idx + 1) % order.length]);
  if (lastData) {
    renderRows(lastData.chains || []);
    renderCharts(lastData);
  }
  if (lastTrendBundle && lastTrendBundle.points && lastTrendBundle.summary) {
    destroyTrendCharts();
    renderTrendCharts(lastTrendBundle.points, lastTrendBundle.summary);
  }
}

function initTheme() {
  const saved = localStorage.getItem("helix-theme");
  const initial = saved === "light" || saved === "dark" || saved === "auto" ? saved : "auto";
  applyTheme(initial);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (currentTheme === "auto") {
      applyTheme("auto");
      if (lastData) {
        renderRows(lastData.chains || []);
        renderCharts(lastData);
      }
      if (lastTrendBundle && lastTrendBundle.points && lastTrendBundle.summary) {
        destroyTrendCharts();
        renderTrendCharts(lastTrendBundle.points, lastTrendBundle.summary);
      }
    }
  });
}

function chartPrimaryColor() {
  return getComputedStyle(document.documentElement).getPropertyValue("--spark").trim() || "#60a5fa";
}

function chartMutedColor() {
  return getComputedStyle(document.documentElement).getPropertyValue("--muted").trim() || "#9aa8c4";
}

function renderSparkline(canvasId, points) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || typeof Chart === "undefined") return;
  const existing = charts.get(canvasId);
  if (existing) existing.destroy();

  const cleanPoints = points.map((v) => (typeof v === "number" ? v : null));
  const chart = new Chart(canvas.getContext("2d"), {
    type: "line",
    data: {
      labels: ["7d", "24h", "Now"],
      datasets: [
        {
          data: cleanPoints,
          borderColor: chartPrimaryColor(),
          pointRadius: 0,
          borderWidth: 2,
          tension: 0.35,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: {
        x: { display: false },
        y: { display: false },
      },
    },
  });
  charts.set(canvasId, chart);
}

function renderRows(chains) {
  rowsEl.innerHTML = "";
  const sorted = [...chains].sort(
    (a, b) => Number((b.supply_current ?? b.usdt_supply) || 0) - Number((a.supply_current ?? a.usdt_supply) || 0)
  );
  for (const chain of sorted) {
    const currentSupply = chain.supply_current ?? chain.usdt_supply;
    const prevDay = chain.supply_prev_day ?? chain.usdt_supply_prev_day;
    const prevWeek = chain.supply_prev_week ?? chain.usdt_supply_prev_week;
    const change24h = calcPercent(currentSupply, prevDay);
    const sparkId = `spark-${chain.chain_name.replace(/\s+/g, "-").toLowerCase()}`;
    const peg = pegStatus(chain.price);
    const share =
      chain.chain_share_pct !== null && chain.chain_share_pct !== undefined
        ? `${Number(chain.chain_share_pct).toFixed(2)}%`
        : "N/A";
    const tvl = chain.chain_tvl ?? chain.tvl;
    const mom = chain.supply_momentum || {};
    const cs = chain.chain_signal || {};
    const dc = chain.data_confidence || {};
    const signalBand = cs.band || "Normal";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${chain.chain_name}</td>
      <td class="num" title="$${formatUsdFull(currentSupply)}">${formatUsd(currentSupply)}</td>
      <td class="num">${share}</td>
      <td class="num" title="DefiLlama stablecoinchains: chain-level aggregate, not this asset only.">${formatUsd(tvl)}</td>
      <td class="num ${deltaClass(change24h)}">${change24h === null ? "N/A" : `${change24h.toFixed(2)}%`}${signalBadge(change24h)}</td>
      <td class="${peg.className}">${peg.label}</td>
      <td>${mom.day_label || "Unknown"}</td>
      <td><span class="mini-badge ${bandClass(signalBand)}">${cs.score ?? "--"} ${signalBand}</span></td>
      <td>${dc.label || "Unknown"} (${dc.score ?? "--"})</td>
      <td class="num"><div class="sparkline"><canvas id="${sparkId}"></canvas></div></td>
    `;
    rowsEl.appendChild(tr);
    renderSparkline(sparkId, [prevWeek, prevDay, currentSupply]);
  }
  chainCountPillEl.textContent = `Chains: ${sorted.length}`;
}

function renderAssetMeta(data) {
  const symbol = data.asset?.symbol || "USDT";
  const name = data.asset?.name || symbol;
  titleEl.textContent = `Helix ${symbol} Signal Terminal`;
  subtitleEl.textContent = `Transparent chain-level ${name} telemetry with Helix Signal Score.`;
  supplyColHeaderEl.textContent = `${symbol} Supply`;
}

function renderAssetSelector(assets) {
  enabledAssets = assets;
  assetSelectorEl.innerHTML = "";
  for (const asset of assets) {
    const opt = document.createElement("option");
    opt.value = asset.symbol;
    opt.textContent = `${asset.symbol} (${asset.name || asset.symbol})`;
    if (asset.symbol === selectedAsset) {
      opt.selected = true;
    }
    assetSelectorEl.appendChild(opt);
  }
}

function renderSourceFooter(data) {
  const source = (data.sources || []).find((s) => s.source_name === "defillama");
  if (!source) {
    sourceFooterEl.innerHTML = '<span class="pill">Source Health: Unknown</span>';
    return;
  }
  const status = source.status || "unknown";
  const successAt = source.last_successful_fetch ? new Date(source.last_successful_fetch).toLocaleString() : "N/A";
  sourceFooterEl.innerHTML = `
    <span class="pill">Source Health: ${status.toUpperCase()}</span>
    <span class="pill">Last Success: ${successAt}</span>
    <span class="pill">Error: ${source.last_error || "None"}</span>
  `;
}

function renderKpis(data) {
  if (!kpiSectionEl) return;
  const fr = data.freshness || {};
  const sig = data.asset_signal || {};
  const dep = data.depeg_index || {};
  const total = data.total_supply_current;
  const d24 = data.total_supply_change_24h_pct;
  const cards = [
    {
      label: "Total supply (sum of chains)",
      value: formatUsd(total),
      sub: total ? `Across ${(data.chains || []).length} configured chains` : "Awaiting chain supply values",
    },
    {
      label: "24h supply change (aggregate)",
      value: d24 === null || d24 === undefined ? "N/A" : `${d24 >= 0 ? "+" : ""}${Number(d24).toFixed(3)}%`,
      sub: "Compared to sum of prior-day baselines",
    },
    {
      label: "Helix Signal Score",
      value: `${sig.score ?? "--"}/100`,
      subHtml: `<span class="${bandClass(sig.band)}">${sig.band || ""}</span> composite (see methodology)`,
    },
    {
      label: "Depeg Index",
      value: `${dep.score ?? "--"}/100`,
      sub: dep.peg_status ? `Peg: ${dep.peg_status}` : "",
    },
    {
      label: "Freshness (server)",
      value: fr.status || "Unknown",
      sub: `Age ${formatAgeSeconds(fr.age_seconds)} · basis ${fr.basis || ""}${fr.reason ? ` · ${fr.reason}` : ""}`,
    },
  ];
  kpiSectionEl.innerHTML = cards
    .map(
      (c) => `
    <div class="kpi-card">
      <div class="kpi-label">${c.label}</div>
      <div class="kpi-value">${c.value}</div>
      <div class="kpi-sub">${c.subHtml ? c.subHtml : c.sub}</div>
    </div>
  `
    )
    .join("");
}

function renderInsightPanels(data) {
  const sig = data.asset_signal || {};
  const comp = sig.components || {};
  if (signalSummaryEl) {
    signalSummaryEl.innerHTML = `Composite <strong>${sig.score ?? "--"}/100</strong> (<span class="${bandClass(sig.band)}">${sig.band || ""}</span>). Higher scores suggest more monitoring attention across peg, momentum, concentration, and data confidence.`;
  }
  if (signalMethodEl) {
    const rows = [
      ["peg_pressure", "Peg pressure"],
      ["supply_momentum", "Supply momentum"],
      ["chain_concentration", "Chain concentration"],
      ["data_confidence", "Data confidence"],
    ];
    signalMethodEl.innerHTML = rows
      .map(([key, title]) => {
        const block = comp[key] || {};
        const w = block.weight != null ? Math.round(Number(block.weight) * 100) : null;
        const sc = block.score != null ? block.score : "--";
        return `<li><strong>${title}</strong>: score <code>${sc}</code>${w != null ? `, weight <code>${w}%</code>` : ""}</li>`;
      })
      .join("");
  }

  const dep = data.depeg_index || {};
  if (depegPanelEl) {
    depegPanelEl.innerHTML = `
      <div><strong>Index</strong><br/>${dep.score ?? "--"}/100</div>
      <div><strong>Price</strong><br/>${dep.current_price != null ? Number(dep.current_price).toFixed(6) : "N/A"}</div>
      <div><strong>Deviation</strong><br/>${
        dep.deviation_pct != null ? `${Number(dep.deviation_pct).toFixed(4)}%` : "N/A"
      }</div>
      <div><strong>Peg label</strong><br/>${dep.peg_status || "N/A"}</div>
    `;
  }
  if (depegNoteEl) {
    depegNoteEl.textContent = dep.note || "";
  }

  const cc = data.chain_concentration || {};
  if (concentrationPanelEl) {
    concentrationPanelEl.innerHTML = `
      <div><strong>Top chain</strong><br/>${cc.top_chain || "N/A"}</div>
      <div><strong>Top share</strong><br/>${cc.top_chain_share_pct != null ? `${cc.top_chain_share_pct}%` : "N/A"}</div>
      <div><strong>HHI</strong><br/>${cc.hhi != null ? cc.hhi : "N/A"}</div>
      <div><strong>Band</strong><br/><span class="${bandClass(cc.label)}">${cc.label || ""}</span></div>
    `;
  }
}

function renderCharts(data) {
  if (typeof Chart === "undefined") return;

  const shareId = "share-chart";
  const compId = "components-chart";
  const existingShare = charts.get(shareId);
  if (existingShare) existingShare.destroy();
  const existingComp = charts.get(compId);
  if (existingComp) existingComp.destroy();

  const chains = [...(data.chains || [])].sort(
    (a, b) => Number(b.chain_share_pct || 0) - Number(a.chain_share_pct || 0)
  );
  const top = chains.slice(0, 12);
  const shareCanvas = document.getElementById(shareId);
  if (shareCanvas && top.length) {
    const chart = new Chart(shareCanvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: top.map((c) => c.chain_name),
        datasets: [
          {
            label: "Share %",
            data: top.map((c) => Number(c.chain_share_pct) || 0),
            backgroundColor: chartPrimaryColor(),
            borderRadius: 4,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { beginAtZero: true, ticks: { color: chartMutedColor() } },
          y: { ticks: { color: chartMutedColor() } },
        },
      },
    });
    charts.set(shareId, chart);
  }

  const compCanvas = document.getElementById(compId);
  const sig = data.asset_signal || {};
  const c = sig.components || {};
  const labels = ["Peg pressure", "Supply momentum", "Concentration", "Data confidence"];
  const values = [
    c.peg_pressure?.score,
    c.supply_momentum?.score,
    c.chain_concentration?.score,
    c.data_confidence?.score,
  ].map((v) => (typeof v === "number" ? v : 0));

  if (compCanvas) {
    const chart = new Chart(compCanvas.getContext("2d"), {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Subscore",
            data: values,
            backgroundColor: chartPrimaryColor(),
            borderRadius: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, max: 100, ticks: { color: chartMutedColor() } },
          x: { ticks: { color: chartMutedColor() } },
        },
      },
    });
    charts.set(compId, chart);
  }
}

function renderFreshness(data) {
  const fr = data.freshness;
  if (!fr) {
    freshnessPill.className = "pill freshness-stale";
    freshnessPill.textContent = "Freshness: Unknown";
    updatedPill.textContent = "Data basis: Unknown";
    staleWarningEl.textContent = "Dashboard payload missing server freshness block.";
    staleWarningEl.classList.add("visible");
    return;
  }

  const status = fr.status || "Stale";
  const cls =
    status === "Fresh" ? "freshness-fresh" : status === "Aging" ? "freshness-aging" : "freshness-stale";
  freshnessPill.className = `pill ${cls}`;
  freshnessPill.textContent = `Freshness: ${status}`;

  const basis = fr.basis_timestamp ? new Date(fr.basis_timestamp).toLocaleString() : "Unknown";
  updatedPill.textContent = `Data basis: ${basis} (${fr.basis || "unknown"})`;

  if (status === "Stale") {
    rowsEl.classList.add("stale");
    staleWarningEl.textContent =
      "Data is stale or source reported an error. Metrics may not reflect current market conditions.";
    staleWarningEl.classList.add("visible");
  } else {
    rowsEl.classList.remove("stale");
    staleWarningEl.textContent = "";
    staleWarningEl.classList.remove("visible");
  }
}

const TREND_CHART_IDS = ["trend-chart-signal", "trend-chart-depeg", "trend-chart-supply", "trend-chart-concentration"];

function formatDurationFromMinutes(m) {
  if (m == null || m === undefined || !Number.isFinite(Number(m))) return "N/A";
  const n = Number(m);
  if (n < 120) return `${Math.round(n)} min`;
  const h = Math.floor(n / 60);
  const r = Math.round(n % 60);
  return r ? `${h}h ${r}m` : `${h}h`;
}

function destroyTrendCharts() {
  for (const id of TREND_CHART_IDS) {
    const c = charts.get(id);
    if (c) c.destroy();
    charts.delete(id);
  }
}

function trendChartOptions({ yMax, yMin, xMinMs, xMaxMs, isSupply }) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    parsing: false,
    plugins: { legend: { display: false } },
    scales: {
      x: {
        type: "linear",
        min: xMinMs,
        max: xMaxMs,
        ticks: {
          color: chartMutedColor(),
          maxTicksLimit: 8,
          callback(v) {
            return new Date(v).toLocaleString(undefined, {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            });
          },
        },
        grid: { color: "rgba(128,128,128,0.12)" },
      },
      y: {
        min: yMin != null ? yMin : undefined,
        beginAtZero: !isSupply,
        suggestedMax: yMax != null && !isSupply ? yMax : undefined,
        ticks: { color: chartMutedColor() },
        grid: { color: "rgba(128,128,128,0.12)" },
      },
    },
  };
}

function renderTrendCoverage(summary) {
  if (!trendCoverageEl) return;
  if (!summary) {
    trendCoverageEl.textContent = "";
    return;
  }
  const w = summary.selected_window || trendWindow;
  const spanH = summary.window_span_hours != null ? summary.window_span_hours : "";
  const avail = formatDurationFromMinutes(summary.available_duration_minutes);
  const pts = summary.point_count != null ? summary.point_count : 0;
  const latest =
    summary.latest_timestamp != null ? new Date(summary.latest_timestamp).toLocaleString() : "N/A";
  trendCoverageEl.textContent = `Selected window: ${w} (${spanH}h axis span) · Available history: ${avail} · Points: ${pts} · Latest: ${latest}`;
}

function renderTrendAxisCaption(summary) {
  if (!trendAxisCaptionEl || !summary) return;
  const minL = summary.chart_axis_min_utc ? new Date(summary.chart_axis_min_utc).toLocaleString() : "";
  const maxL = summary.chart_axis_max_utc ? new Date(summary.chart_axis_max_utc).toLocaleString() : "";
  trendAxisCaptionEl.textContent = `X-axis: full selected window (${minL} to ${maxL}). Plotted points only cover the available history shown above.`;
}

function updateTrendLowDataBanner(points, summary) {
  if (!trendLowDataEl) return;
  const low = Boolean(summary?.low_data) || (points && points.length < 2);
  if (!low) {
    trendLowDataEl.classList.remove("visible");
    return;
  }
  trendLowDataEl.classList.add("visible");
  let msg = summary?.low_data_reason || "";
  if ((!points || points.length < 2) && !msg) {
    msg =
      "Need at least two snapshots in this window before trend lines are meaningful. History collection started recently.";
  }
  trendLowDataEl.textContent = msg || "Limited trend data in the selected window.";
}

function renderTrendCharts(points, summary) {
  if (!trendLowDataEl) return;
  if (!summary || summary.chart_axis_min_utc == null || summary.chart_axis_max_utc == null) {
    destroyTrendCharts();
    if (trendCoverageEl) trendCoverageEl.textContent = "";
    if (trendAxisCaptionEl) trendAxisCaptionEl.textContent = "";
    updateTrendLowDataBanner(points || [], summary || {});
    return;
  }

  const xMin = new Date(summary.chart_axis_min_utc).getTime();
  const xMax = new Date(summary.chart_axis_max_utc).getTime();
  const pts = points || [];

  destroyTrendCharts();
  updateTrendLowDataBanner(pts, summary);
  renderTrendCoverage(summary);
  renderTrendAxisCaption(summary);

  if (typeof Chart === "undefined" || pts.length === 0) return;

  const mk = (id, dataKey, yCap, isSupply) => {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    const existing = charts.get(id);
    if (existing) existing.destroy();
    const data = pts.map((p) => ({
      x: new Date(p.timestamp).getTime(),
      y: p[dataKey] == null ? null : Number(p[dataKey]),
    }));
    const ys = data.map((o) => o.y).filter((v) => typeof v === "number" && !Number.isNaN(v));
    let yMin = undefined;
    if (isSupply && ys.length) {
      yMin = Math.min(...ys) * 0.9995;
    }
    const chart = new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        datasets: [
          {
            data,
            borderColor: chartPrimaryColor(),
            backgroundColor: "rgba(59, 130, 246, 0.08)",
            fill: isSupply,
            tension: 0.25,
            pointRadius: pts.length <= 3 ? 3 : 0,
            borderWidth: 2,
          },
        ],
      },
      options: trendChartOptions({
        yMax: yCap,
        yMin,
        xMinMs: xMin,
        xMaxMs: xMax,
        isSupply,
      }),
    });
    charts.set(id, chart);
  };

  mk("trend-chart-signal", "signal_score", 100, false);
  mk("trend-chart-depeg", "depeg_index", 100, false);
  mk("trend-chart-supply", "total_supply", null, true);
  mk("trend-chart-concentration", "concentration_score", 100, false);
}

function formatEventWhen(iso) {
  const d = new Date(iso);
  const sec = (Date.now() - d.getTime()) / 1000;
  if (sec < 90) return "just now";
  if (sec < 3600) return `${Math.round(sec / 60)} min ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)} h ago`;
  return d.toLocaleString();
}

function severityClass(sev, { system = false } = {}) {
  if (system) return "sev-system";
  if (sev === "critical") return "sev-critical";
  if (sev === "warning") return "sev-warning";
  return "sev-info";
}

function isSystemEvent(e) {
  const sym = String(e.asset_symbol || "").toUpperCase();
  const typ = String(e.event_type || "");
  const sev = String(e.severity || "").toLowerCase();
  return sym === "ALL" || typ === "source_recovered" || sev === "system";
}

function eventCardHtml(ev, { system = false } = {}) {
  const cls = system ? "event-card event-card--system" : "event-card";
  const ctx =
    ev.asset_symbol === "ALL"
      ? "System"
      : `${ev.asset_symbol}${ev.chain_key ? ` · ${ev.chain_key}` : ""}`;
  const summaryText = system
    ? "DefiLlama ingest succeeded again after a prior error. Use for diagnostics only."
    : ev.summary;
  const titleText = system ? "Source pipeline recovered" : ev.title;
  return `
      <article class="${cls}">
        <div class="event-card-top">
          <div class="event-title">${titleText}</div>
          <span class="${severityClass(ev.severity, { system })}">${system ? "system" : ev.severity}</span>
        </div>
        <div class="event-meta">${formatEventWhen(ev.timestamp)} · ${ctx}</div>
        <p class="event-summary">${summaryText}</p>
      </article>`;
}

function renderEventFeed(events) {
  if (!eventFeedListEl) return;
  const list = Array.isArray(events) ? events : [];
  const systemEvents = list.filter(isSystemEvent);
  const assetEvents = list.filter((e) => !isSystemEvent(e) && e.asset_symbol === selectedAsset);
  const showSystem = Boolean(eventShowSystemEl && eventShowSystemEl.checked);

  if (assetEvents.length > 0) {
    let html = assetEvents.map((e) => eventCardHtml(e, { system: false })).join("");
    if (showSystem && systemEvents.length > 0) {
      html += `<p class="kpi-sub" style="margin:12px 0 6px">System events</p>`;
      html += systemEvents.map((e) => eventCardHtml(e, { system: true })).join("");
    }
    eventFeedListEl.innerHTML = html;
    return;
  }

  if (showSystem && systemEvents.length > 0) {
    eventFeedListEl.innerHTML =
      `<p class="kpi-sub" style="margin:0 0 8px">System events</p>` +
      systemEvents.map((e) => eventCardHtml(e, { system: true })).join("");
    return;
  }

  eventFeedListEl.innerHTML =
    '<p class="kpi-sub" style="margin:0">No major signal events yet. Events will appear when score, peg pressure, supply, concentration, or confidence changes materially.</p>';
}

async function loadTrendsAndEvents() {
  if (!trendLowDataEl || !eventFeedListEl) return;
  try {
    const tr = await fetch(
      `${API_ROOT}/api/trends?asset=${encodeURIComponent(selectedAsset)}&window=${encodeURIComponent(trendWindow)}`,
      { cache: "no-store" }
    );
    const ev = await fetch(
      `${API_ROOT}/api/events?asset=${encodeURIComponent(selectedAsset)}&limit=50`,
      { cache: "no-store" }
    );
    if (tr.ok) {
      const tjson = await tr.json();
      lastTrendBundle = {
        points: tjson.points || [],
        summary: tjson.summary || null,
        window: tjson.window || trendWindow,
      };
      renderTrendCharts(lastTrendBundle.points, lastTrendBundle.summary);
    } else {
      lastTrendBundle = null;
      destroyTrendCharts();
      if (trendCoverageEl) trendCoverageEl.textContent = "";
      if (trendAxisCaptionEl) trendAxisCaptionEl.textContent = "";
      updateTrendLowDataBanner([], {
        low_data: true,
        low_data_reason: "Could not load trends from the API.",
      });
    }
    if (ev.ok) {
      const ejson = await ev.json();
      lastRawEvents = ejson.events || [];
      renderEventFeed(lastRawEvents);
    } else {
      lastRawEvents = [];
      renderEventFeed([]);
    }
  } catch {
    lastTrendBundle = null;
    destroyTrendCharts();
    if (trendCoverageEl) trendCoverageEl.textContent = "";
    if (trendAxisCaptionEl) trendAxisCaptionEl.textContent = "";
    updateTrendLowDataBanner([], { low_data: true, low_data_reason: "Could not load trends (network error)." });
  }
}

function syncTrendWindowPills() {
  if (!trendWindowPillsEl) return;
  trendWindowPillsEl.querySelectorAll(".window-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.window === trendWindow);
  });
}

function initTrendWindowControls() {
  if (!trendWindowPillsEl) return;
  syncTrendWindowPills();
  trendWindowPillsEl.addEventListener("click", (e) => {
    const btn = e.target.closest(".window-btn");
    if (!btn || !btn.dataset.window) return;
    trendWindow = btn.dataset.window;
    syncTrendWindowPills();
    loadTrendsAndEvents();
  });
  if (eventShowSystemEl) {
    eventShowSystemEl.addEventListener("change", () => {
      renderEventFeed(lastRawEvents);
    });
  }
}

async function loadDashboard({ manual = false } = {}) {
  if (isLoading) return;
  isLoading = true;
  refreshBtn.disabled = true;
  refreshBtn.textContent = manual ? "Refreshing..." : "Refresh";
  stateEl.textContent = manual ? "Refreshing dashboard data..." : "Loading dashboard data...";
  stateEl.classList.remove("error");
  try {
    if (manual) {
      const rr = await fetch(REFRESH_URL, { method: "POST", cache: "no-store" });
      if (!rr.ok) {
        const detail = await rr.text();
        throw new Error(`Backend refresh failed (${rr.status}): ${detail || rr.statusText}`);
      }
    }
    const response = await fetch(`${API_URL}?asset=${encodeURIComponent(selectedAsset)}`, {
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    lastData = data;
    renderAssetMeta(data);
    renderKpis(data);
    renderInsightPanels(data);
    renderCharts(data);
    renderRows(data.chains || []);
    renderSourceFooter(data);
    renderFreshness(data);
    await loadTrendsAndEvents();
    stateEl.textContent = manual ? "Refresh completed." : "Live snapshot loaded.";
  } catch (error) {
    stateEl.textContent = `Error loading dashboard: ${error.message}`;
    stateEl.classList.add("error");
    if (!lastData) {
      rowsEl.innerHTML = "";
    }
    staleWarningEl.textContent = "Using last known dashboard snapshot due to refresh failure.";
    staleWarningEl.classList.add("visible");
    if (!lastData && selectedAsset !== "USDT") {
      stateEl.textContent = `Unable to load ${selectedAsset}. Falling back to USDT.`;
      selectedAsset = "USDT";
      localStorage.setItem("helix-asset", selectedAsset);
      assetSelectorEl.value = selectedAsset;
    }
  } finally {
    isLoading = false;
    refreshBtn.disabled = false;
    refreshBtn.textContent = "Refresh";
  }
}

async function loadAssets() {
  const response = await fetch(`${API_ROOT}/api/assets`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Assets endpoint failed: HTTP ${response.status}`);
  }
  const assets = await response.json();
  if (!Array.isArray(assets) || assets.length === 0) {
    throw new Error("No enabled assets returned by API");
  }
  const assetSymbols = assets.map((asset) => asset.symbol);
  const defaultAsset = assets.find((asset) => asset.default)?.symbol || assets[0].symbol;
  const saved = localStorage.getItem("helix-asset");
  selectedAsset = assetSymbols.includes(saved) ? saved : defaultAsset;
  localStorage.setItem("helix-asset", selectedAsset);
  renderAssetSelector(assets);
}

initTheme();
themeBtn.addEventListener("click", cycleTheme);
refreshBtn.addEventListener("click", () => loadDashboard({ manual: true }));
assetSelectorEl.addEventListener("change", () => {
  selectedAsset = assetSelectorEl.value;
  localStorage.setItem("helix-asset", selectedAsset);
  loadDashboard({ manual: false });
});

loadAssets()
  .then(() => loadDashboard())
  .catch((error) => {
    stateEl.textContent = `Error loading assets: ${error.message}`;
    stateEl.classList.add("error");
  });
initTrendWindowControls();
setInterval(() => loadDashboard({ manual: false }), 60000);
