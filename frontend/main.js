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

const charts = new Map();
let isLoading = false;
let lastData = null;
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
setInterval(() => loadDashboard({ manual: false }), 60000);
