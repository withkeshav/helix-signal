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

By default in V2.1:

- USDT is enabled and default
- USDC, DAI, and PYUSD are present as disabled draft entries

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

For the selected asset symbol, Helix reads `chainCirculating` values from DefiLlama:

- `current` -> `supply_current`
- `circulatingPrevDay` -> `supply_prev_day`
- `circulatingPrevWeek` -> `supply_prev_week`
- `circulatingPrevMonth` -> `supply_prev_month`

Values are interpreted as USD-denominated circulating amount (`peggedUSD`) when available.

### TVL

TVL is context-only in V1 and read from DefiLlama chain metadata when present.
If unavailable or fetch fails, TVL is stored as `null` and rendered as `N/A`.

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

## Known V2.1 Limitations

- Single-source baseline (DefiLlama)
- No deep historical datastore beyond current/prev day/week/month fields
- No trading execution, alerting, or predictive modeling
- Multi-asset architecture is ready, but only USDT is enabled by default in current release posture
