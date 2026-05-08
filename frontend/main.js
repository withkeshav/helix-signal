const API_URL = "http://localhost:8000/api/dashboard";
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
      }
    }
  });
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
          borderColor: getComputedStyle(document.documentElement).getPropertyValue("--spark").trim() || "#60a5fa",
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
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${chain.chain_name}</td>
      <td class="num" title="$${formatUsdFull(currentSupply)}">${formatUsd(currentSupply)}</td>
      <td class="num ${deltaClass(change24h)}">${change24h === null ? "N/A" : `${change24h.toFixed(2)}%`}${signalBadge(change24h)}</td>
      <td class="${peg.className}">${peg.label}</td>
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
  subtitleEl.textContent = `Transparent chain-level ${name} telemetry.`;
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

function computeFreshness(data) {
  const source = (data.sources || []).find((s) => s.source_name === "defillama");
  if (!source) {
    return { label: "Stale", className: "freshness-stale", message: "Source data is unavailable." };
  }
  if (source.status === "error") {
    return { label: "Stale", className: "freshness-stale", message: "DefiLlama source is reporting an error." };
  }
  const latestChainTs = (data.chains || [])
    .map((c) => c.fetched_at)
    .filter(Boolean)
    .map((v) => new Date(v).getTime())
    .filter((v) => Number.isFinite(v));
  const sourceTs = source.last_successful_fetch ? new Date(source.last_successful_fetch).getTime() : NaN;
  const newestTs = Math.max(sourceTs || 0, ...(latestChainTs.length ? latestChainTs : [0]));
  const ts = newestTs > 0 ? new Date(newestTs).toISOString() : null;
  if (!ts) {
    return { label: "Stale", className: "freshness-stale", message: "No successful source update timestamp found." };
  }
  const refreshSeconds = Number(data.refresh_interval_seconds || 300);
  const freshThresholdMins = Math.max(15, (refreshSeconds * 3) / 60);
  const agingThresholdMins = Math.max(60, (refreshSeconds * 12) / 60);
  const ageMinutes = (Date.now() - new Date(ts).getTime()) / 60000;
  if (ageMinutes <= freshThresholdMins) return { label: "Fresh", className: "freshness-fresh", message: "", lastSuccess: ts };
  if (ageMinutes <= agingThresholdMins) {
    return { label: "Aging", className: "freshness-aging", message: "Data is aging. Consider refreshing soon." };
  }
  return { label: "Stale", className: "freshness-stale", message: "Data is stale and may not reflect current market conditions." };
}

function renderFreshness(data) {
  const freshness = computeFreshness(data);
  freshnessPill.className = `pill ${freshness.className}`;
  freshnessPill.textContent = `Freshness: ${freshness.label}`;
  const source = (data.sources || []).find((s) => s.source_name === "defillama");
  const lastSuccess = source?.last_successful_fetch || data.generated_at;
  updatedPill.textContent = `Last Successful Fetch: ${lastSuccess ? new Date(lastSuccess).toLocaleString() : "Unknown"}`;

  if (freshness.label === "Stale") {
    rowsEl.classList.add("stale");
  } else {
    rowsEl.classList.remove("stale");
  }

  if (freshness.message) {
    staleWarningEl.textContent = freshness.message;
    staleWarningEl.classList.add("visible");
  } else {
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
    const response = await fetch(`${API_URL}?asset=${encodeURIComponent(selectedAsset)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    lastData = data;
    renderAssetMeta(data);
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
  const response = await fetch("http://localhost:8000/api/assets");
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
