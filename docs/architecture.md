# Architecture (V2.4)

Helix-Signal follows a backend-first architecture.

## High-Level Flow

```text
DefiLlama stablecoins APIs (+ stablecoinchains for chain TVL context)
    |
    v
FastAPI backend (scheduler + multi-asset refresh loop)
    |
    v
SQLite cache (asset_chain_snapshots, source_status, asset_trend_snapshots, chain_trend_snapshots, signal_events)
    |
    +--> /api/assets
    |
    +--> /api/dashboard?asset=SYMBOL (USDT default fallback)
    |
    +--> /api/trends and /api/trends/chains (historical windows 24h, 7d, 30d)
    |
    +--> /api/events (local signal feed, optional asset filter)
    |
    +--> POST /api/refresh (manual ingest refresh, same pipeline as scheduler)
            |
            +--> signal_engine.scoring (freshness, Helix Signal Score, Depeg Index, concentration)
            |
            +--> signal_engine.metrics (shared bundle for snapshots)
            |
            +--> signal_engine.history (trend rows + deduplicated events after successful refresh)
            |
            v
Vanilla JS + Chart.js frontend (KPI strip, insight panels, charts, chain table, trend charts, event feed)
```

## Components

### Backend (`backend/`)

- FastAPI application with:
  - `/` health-style greeting endpoint
  - `/api/dashboard` with optional `asset` query parameter and V2.3 enriched payload (`freshness`, `asset_signal`, `depeg_index`, `chain_concentration`, derived totals, per-chain momentum and confidence)
  - `/api/assets` for enabled asset listing
  - `POST /api/refresh` to run the same ingest job as the scheduler
  - `/api/trends` and `/api/trends/chains` for historical series (`window` = `24h`, `7d`, or `30d`)
  - `/api/events` for the local signal feed (`asset` optional)
- APScheduler background job refreshes source data periodically
- Signal engine parses and normalizes asset-chain snapshots for enabled assets (`signal_engine/core.py`)
- Transparent scoring helpers in `signal_engine/scoring.py` (documented weights and bands)
- `signal_engine/metrics.py` builds a consistent metric bundle for history snapshots
- `signal_engine/history.py` writes 5-minute bucketed trend rows and deduplicated `signal_events` after successful refreshes
- SQLAlchemy models persist latest snapshots and append-only style history in SQLite

### Data Store

- SQLite database (`backend/helix.db`)
- Core tables:
  - `asset_chain_snapshots`: per asset and chain current and previous supply values, optional chain aggregate TVL, price, peg metadata, timestamps
  - `source_status`: source health, last attempt, success, and error details
  - `asset_trend_snapshots` and `chain_trend_snapshots`: forward-collected monitoring history (V2.4)
  - `signal_events`: local explainable timeline entries (V2.4)

### Frontend (`frontend/`)

- Static HTML, CSS, and JavaScript
- Loads enabled assets and fetches selected-asset dashboard payloads
- Renders:
  - KPI strip (totals, composite score, depeg index, server freshness)
  - Helix Signal methodology list from API component weights
  - Depeg Index and chain concentration cards
  - Chart.js horizontal bar for chain supply share and vertical bar for signal subscores
  - Historical trend charts (signal score, Depeg Index, supply, concentration) with 24h, 7d, and 30d window selector
  - Compact signal feed panel sourced from `/api/events`
  - Main chain table with share, labeled chain TVL, 24h change, peg, momentum label, chain signal, data confidence, and sparklines
  - Source health footer

## Design Intent

- Keep frontend thin and deterministic
- Centralize data logic and scoring on the backend for consistency and auditability
- Ensure local reproducibility via Docker Compose
- Fail gracefully when upstream APIs have intermittent issues
- Label chain TVL responsibly when shown (chain aggregate, not per-asset)
