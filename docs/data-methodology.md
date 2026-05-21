# Data Methodology (V2.4)

This document explains how Helix-Signal computes and presents asset-chain stablecoin metrics, the Helix Signal Score, historical trends, and the local signal feed.

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

By default in V2.4:

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
  - on a successful pass, record `last_successful_fetch` as the **UTC completion time** of that ingest pass
  - on a successful pass, write **trend snapshots** and evaluate **signal events** (V2.4, see below)
- On fetch failure:
  - source status is marked `error`
  - last error is recorded
  - worker continues running (no crash)
  - trend snapshots are **not** written for that pass (avoids misleading history)

**Server-side freshness** (V2.3+): the API returns a `freshness` object computed only on the server using UTC-aware timestamps:

- **Basis timestamp**: primarily `last_successful_fetch` when the source is healthy, so a successful refresh does not read as stale solely because upstream chain labels are older
- **Fresh**: age within `max(900s, 3 * REFRESH_INTERVAL_SECONDS)`
- **Aging**: older than fresh window but within `max(3600s, 12 * REFRESH_INTERVAL_SECONDS)`
- **Stale**: older than the warning window, or missing basis, or source status is `error`

The `freshness.reason` field may reference the newest chain snapshot age as context only.

The frontend displays this server payload to avoid client clock and parsing inconsistencies.

## Historical trend snapshots (V2.4)

After each **successful** multi-asset refresh (DefiLlama source status `ok`), Helix stores:

- **Asset trend snapshots** (`asset_trend_snapshots`): one row per enabled asset per 5-minute UTC bucket (`floor(epoch_seconds / 300)`), including total supply, price, Depeg Index, Helix Signal Score and band, concentration subscore, aggregate data confidence label, and source status.
- **Chain trend snapshots** (`chain_trend_snapshots`): one row per configured chain row per asset per bucket, including supply, share percent, labeled chain aggregate TVL, chain signal score and band, and chain data confidence score.

**Timing**: timestamps use the same UTC completion instant as `last_successful_fetch` for that pass.

**Duplicate control**: rows in the current bucket are replaced on re-entry within the same 5-minute window so manual refresh spam does not create parallel duplicates.

**Limits**: there is **no long backfill**. History begins when V2.4 code is first deployed and successful refreshes run. Charts may show a low-data state until at least two buckets exist.

**Interpretation**: trend lines mirror the same scoring definitions as the live dashboard. **Chain TVL** in stored chain trends remains **chain-level aggregate** stablecoin TVL from DefiLlama `stablecoinchains`, not asset-specific DeFi TVL.

## Signal events (V2.4)

The **signal feed** is a local SQLite timeline of meaningful deltas, not outbound alerts.

**Event types** (examples):

- `signal_band_change`: composite band changed (Normal, Watch, Risk) with severity by direction
- `depeg_pressure_change`: Depeg Index crossed informational zones (low below 40, mid 40 to 69, high 70+)
- `large_supply_change`: snapshot-to-snapshot total supply percent move exceeds about 1% (info) or 2% (warning)
- `concentration_change`: top-chain share jump of about five percentage points, or concentration subscore jump of about ten points
- `data_confidence_drop`: aggregate label fell from High to Medium or Low
- `source_recovered`: DefiLlama status transitioned from `error` to `ok`

**Deduplication**: the same event type, asset, chain scope, severity, and `new_value` is suppressed if an equal row exists within about 30 minutes.

## Retention (V2.5)

A daily scheduler job deletes rows older than configured thresholds:

- `TREND_RETENTION_DAYS` (default **90**) — `asset_trend_snapshots` and `chain_trend_snapshots`
- `EVENT_RETENTION_DAYS` (default **30**) — `signal_events`

Fresh installs with little history are unaffected beyond normal low-data messaging.

## Optional synthetic backfill (V2.5)

When `ALLOW_BACKFILL=true`, `POST /api/admin/backfill?asset=SYMBOL&days=7` may insert **coarse daily** points from DefiLlama circulating charts. Rows use `source_status=synthetic_backfill` and do not overwrite calendar days that already have live ingest snapshots. Compare and export consumers may exclude synthetic rows where noted. This is for faster chart context on new installs, not a full historical re-score.

## Attestation and supply feed (OSINT)

`/api/osint/attestation` returns **two independent signals** per asset:

### Issuer attestation report age

Parsed only from issuer transparency pages when a report date can be proven (e.g. Circle USDC). Thresholds:

- **fresh**: report age &lt; 90 days
- **aging**: 90–179 days
- **stale**: 180+ days
- **unknown**: issuer page not parseable (USDT, PYUSD today)
- **n/a**: on-chain-only assets (DAI) — no issuer attestation model

Helix does **not** use DefiLlama refresh time as a proxy for attestation dates.

### DefiLlama supply feed freshness

Derived from `SourceStatus.last_successful_fetch` for the `defillama` source (same ingest pipeline as dashboard supply). Thresholds align with dashboard freshness windows:

- **fresh**: ≤ 15 minutes
- **aging**: ≤ 60 minutes
- **stale**: &gt; 60 minutes

This reflects how recently on-chain supply data was ingested, not audit report recency.

## Known limitations

- Single-source baseline (DefiLlama)
- Live dashboard still only exposes current and prev day, week, and month fields from DefiLlama; **trend charts** add forward-point storage but do not import long external history
- No trading execution, outbound alerting, or predictive modeling
- Chain TVL is chain aggregate context only, as labeled
