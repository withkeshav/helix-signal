# Data Methodology (V2.3)

This document explains how Helix-Signal computes and presents asset-chain stablecoin metrics and the Helix Signal Score in V2.3.

## Primary Source

- Source: DefiLlama stablecoins API
- Endpoint used for asset chain circulating values:
  - `https://stablecoins.llama.fi/stablecoins?includePrices=true`
- Supplemental endpoint for **chain-level aggregate** TVL context:
  - `https://stablecoins.llama.fi/stablecoinchains`

## Asset and Chain Universe

Helix uses:

- `config/chains.json` for chain universe
- `config/assets.json` for stablecoin asset universe

By default in V2.3:

- USDT is enabled and default
- USDC, DAI, and PYUSD are enabled when parser and API checks pass

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

### Aggregate supply KPIs

For the selected asset, the dashboard also reports:

- **Total supply**: sum of `supply_current` across configured chains with numeric values
- **Aggregate 24h change (%)**: `((sum(supply_current) - sum(supply_prev_day)) / sum(supply_prev_day)) * 100` when the prior-day sum is positive

### TVL (chain aggregate, labeled)

Values in the **Chain TVL** column come from DefiLlama `stablecoinchains`. They represent **chain-level aggregate stablecoin TVL** for that chain, **not** this asset alone and not a guaranteed per-asset, per-chain liquidity figure.

Helix only surfaces this field with that explicit labeling in the UI and API schema description so operators are not misled about attribution.

### Peg Price and Peg Status

Peg uses DefiLlama's reported selected-asset `price` as baseline (one price across chains in the current model).

Status thresholds (same as prior releases):

- Healthy: `|price - 1.0| <= 0.001` (0.1%)
- Watch: `|price - 1.0| <= 0.005` (0.5%)
- Alert: `|price - 1.0| > 0.005`

### Depeg Index

The **Depeg Index** is a 0 to 100 score derived from absolute percent deviation of the asset-level price from the USD peg anchor (1.0). It is documented as **not** chain-specific oracle precision.

### Helix Signal Score (composite)

The composite **Helix Signal Score** is 0 to 100 with bands:

- **Normal**: 0 to 39
- **Watch**: 40 to 69
- **Risk**: 70 to 100

Higher scores mean more suggested monitoring attention (stress across dimensions), not a prediction of failure.

**Weights** (documented in code and API `components`):

- Peg pressure: 35%
- Supply momentum: 25%
- Chain concentration: 20%
- Data confidence: 20%

Subscore notes:

- **Peg pressure**: maps from the same peg stress logic as the Depeg Index
- **Supply momentum**: uses aggregate current supply versus prior day, week, and month sums when available
- **Chain concentration**: Herfindahl-style HHI on normalized chain supply shares plus top-chain share context
- **Data confidence**: combines DefiLlama source status and recency of the combined freshness basis versus refresh interval

Per-chain rows expose simplified **chain signal** and **data confidence** hints for table scanning; the authoritative composite remains asset-level.

### 1d / 7d / 30d Delta Logic

Stored values:

- 1d baseline: `supply_prev_day`
- 7d baseline: `supply_prev_week`
- 30d baseline: `supply_prev_month`

Displayed 24h change (%), per chain:

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
  - refresh worker records `last_successful_fetch` using the **maximum** successful per-asset snapshot time in that pass (not only the last asset processed)
- On fetch failure:
  - source status is marked `error`
  - last error is recorded
  - worker continues running (no crash)

**Server-side freshness** (V2.3): the API returns a `freshness` object computed only on the server using UTC-aware timestamps:

- **Basis timestamp**: `max(last_successful_fetch, newest_chain_snapshot)` when both exist, otherwise whichever exists
- **Fresh**: age within `max(900s, 3 * REFRESH_INTERVAL_SECONDS)`
- **Aging**: older than fresh window but within `max(3600s, 12 * REFRESH_INTERVAL_SECONDS)`
- **Stale**: older than the warning window, or missing basis, or source status is `error`

The frontend displays this server payload to avoid client clock and parsing inconsistencies.

## Known V2.3 Limitations

- Single-source baseline (DefiLlama)
- No deep historical datastore beyond current and prev day, week, and month fields
- No trading execution, alerting, or predictive modeling
- Chain TVL is chain aggregate context only, as labeled
