# Data Methodology (V1)

This document explains how Helix-Signal computes and presents USDT metrics in V1.

## Primary Source

- Source: DefiLlama stablecoins API
- Endpoint used for USDT chain circulating values:
  - `https://stablecoins.llama.fi/stablecoins?includePrices=true`
- Supplemental endpoint for chain context (TVL where available):
  - `https://stablecoins.llama.fi/stablecoinchains`

## Chain Universe

Helix uses the pinned chain list in `config/chains.json`:

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

The UI ordering follows this configured set, and frontend default sorting is by current USDT supply descending.

## Metric Definitions

### USDT Supply

Per chain, Helix reads USDT `chainCirculating` values from DefiLlama:

- `current` -> `usdt_supply`
- `circulatingPrevDay` -> `usdt_supply_prev_day`
- `circulatingPrevWeek` -> `usdt_supply_prev_week`
- `circulatingPrevMonth` -> `usdt_supply_prev_month`

Values are interpreted as USD-denominated circulating amount (`peggedUSD`) when available.

### TVL

TVL is context-only in V1 and read from DefiLlama chain metadata when present.
If unavailable or fetch fails, TVL is stored as `null` and rendered as `N/A`.

### Peg Price and Peg Status

Peg uses DefiLlama's reported USDT price (`price`) as V1 baseline.

Status thresholds:

- Healthy (green): `|price - 1.0| <= 0.001` (0.1%)
- Watch (yellow): `|price - 1.0| <= 0.005` (0.5%)
- Alert (red): `|price - 1.0| > 0.005`

### 1d / 7d / 30d Delta Logic

Stored values:

- 1d baseline: `usdt_supply_prev_day`
- 7d baseline: `usdt_supply_prev_week`
- 30d baseline: `usdt_supply_prev_month`

Displayed 24h change (%):

- `((usdt_supply - usdt_supply_prev_day) / usdt_supply_prev_day) * 100`
- If baseline is missing or zero, value is shown as `N/A`

Sparklines:

- Sequence: `[prev_week, prev_day, current]`
- Purpose: quick directional context, not full historical charting

## Refresh and Freshness

- Scheduler interval: `REFRESH_INTERVAL_SECONDS` (default 300s)
- On each refresh:
  - attempt DefiLlama fetch
  - upsert chain rows in SQLite
  - upsert source health in `source_status`
- On fetch failure:
  - source status is marked `error`
  - last error is recorded
  - worker continues running (no crash)

## Known V1 Limitations

- Single-source baseline (DefiLlama)
- No deep historical datastore beyond current/prev day/week/month fields
- No trading execution, alerting, or predictive modeling
