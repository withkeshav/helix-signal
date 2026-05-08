# Data Methodology (V2.1)

This document explains how Helix-Signal computes and presents asset-chain stablecoin metrics in V2.1.

## Primary Source

- Source: DefiLlama stablecoins API
- Endpoint used for asset chain circulating values:
  - `https://stablecoins.llama.fi/stablecoins?includePrices=true`
- Supplemental endpoint for chain context (TVL where available):
  - `https://stablecoins.llama.fi/stablecoinchains`

## Asset and Chain Universe

Helix uses:

- `config/chains.json` for chain universe
- `config/assets.json` for stablecoin asset universe

By default in V2.2:

- USDT is enabled and default
- USDC, DAI, and PYUSD are enabled when parser/API checks pass

Current pinned chains:

- Tron
- Ethereum
- BSC
- Solana
- Arbitrum
- Plasma
- Polygon
- Aptos
- TON
- Avalanche

The UI sorts by current supply descending for the selected asset.

## Metric Definitions

### Asset Supply

For each selected asset symbol (USDT, USDC, DAI, PYUSD), Helix reads `chainCirculating` values from DefiLlama:

- `current` -> `supply_current`
- `circulatingPrevDay` -> `supply_prev_day`
- `circulatingPrevWeek` -> `supply_prev_week`
- `circulatingPrevMonth` -> `supply_prev_month`

Values are interpreted as USD-denominated circulating amount (`peggedUSD`) when available.

### TVL

Reliable per-asset, per-chain TVL is not consistently available from the current DefiLlama public stablecoin payloads.
To avoid implying precision where it is not guaranteed, the dashboard currently hides the TVL column for V2.2.1.
Helix will only re-enable a visible liquidity column when the upstream data is consistently attributable to both asset and chain.

### Peg Price and Peg Status

Peg uses DefiLlama's reported selected-asset price (`price`) as baseline.

Status thresholds:

- Healthy (green): `|price - 1.0| <= 0.001` (0.1%)
- Watch (yellow): `|price - 1.0| <= 0.005` (0.5%)
- Alert (red): `|price - 1.0| > 0.005`

### 1d / 7d / 30d Delta Logic

Stored values:

- 1d baseline: `supply_prev_day`
- 7d baseline: `supply_prev_week`
- 30d baseline: `supply_prev_month`

Displayed 24h change (%):

- `((supply_current - supply_prev_day) / supply_prev_day) * 100`
- If baseline is missing or zero, value is shown as `N/A`

Sparklines:

- Sequence: `[prev_week, prev_day, current]`
- Purpose: quick directional context, not full historical charting
- Sparse-chain assets are supported; UI shows only available configured chain rows for the selected asset.

## Refresh and Freshness

- Scheduler interval: `REFRESH_INTERVAL_SECONDS` (default 300s)
- On each refresh:
  - attempt DefiLlama fetch for each enabled asset
  - upsert asset-chain rows in SQLite
  - upsert source health in `source_status`
- On fetch failure:
  - source status is marked `error`
  - last error is recorded
  - worker continues running (no crash)

Frontend freshness labels use the latest successful fetch timestamp from source status and newest available chain snapshot timestamp:

- Fresh: within the configured recent threshold (derived from `REFRESH_INTERVAL_SECONDS`, minimum 15 minutes)
- Aging: older than fresh threshold but still within warning threshold (minimum 60 minutes)
- Stale: older than warning threshold or source status reports error

## Known V2.1 Limitations

- Single-source baseline (DefiLlama)
- No deep historical datastore beyond current/prev day/week/month fields
- No trading execution, alerting, or predictive modeling
- Multi-asset dashboard is active with controlled enabled assets through `config/assets.json`
