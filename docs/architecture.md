# Architecture (V2.3)

Helix-Signal follows a backend-first architecture.

## High-Level Flow

```text
DefiLlama stablecoins APIs (+ stablecoinchains for chain TVL context)
    |
    v
FastAPI backend (scheduler + multi-asset refresh loop)
    |
    v
SQLite cache (asset_chain_snapshots, source_status)
    |
    +--> /api/assets
    |
    +--> /api/dashboard?asset=SYMBOL (USDT default fallback)
            |
            +--> signal_engine.scoring (freshness, Helix Signal Score, Depeg Index, concentration)
            |
            v
Vanilla JS + Chart.js frontend (KPI strip, insight panels, charts, chain table)
```

## Components

### Backend (`backend/`)

- FastAPI application with:
  - `/` health-style greeting endpoint
  - `/api/dashboard` with optional `asset` query parameter and V2.3 enriched payload (`freshness`, `asset_signal`, `depeg_index`, `chain_concentration`, derived totals, per-chain momentum and confidence)
  - `/api/assets` for enabled asset listing
- APScheduler background job refreshes source data periodically
- Signal engine parses and normalizes asset-chain snapshots for enabled assets (`signal_engine/core.py`)
- Transparent scoring helpers in `signal_engine/scoring.py` (documented weights and bands)
- SQLAlchemy models persist latest snapshots in SQLite

### Data Store

- SQLite database (`backend/helix.db`)
- Core tables:
  - `asset_chain_snapshots`: per asset and chain current and previous supply values, optional chain aggregate TVL, price, peg metadata, timestamps
  - `source_status`: source health, last attempt, success, and error details

### Frontend (`frontend/`)

- Static HTML, CSS, and JavaScript
- Loads enabled assets and fetches selected-asset dashboard payloads
- Renders:
  - KPI strip (totals, composite score, depeg index, server freshness)
  - Helix Signal methodology list from API component weights
  - Depeg Index and chain concentration cards
  - Chart.js horizontal bar for chain supply share and vertical bar for signal subscores
  - Main chain table with share, labeled chain TVL, 24h change, peg, momentum label, chain signal, data confidence, and sparklines
  - Source health footer

## Design Intent

- Keep frontend thin and deterministic
- Centralize data logic and scoring on the backend for consistency and auditability
- Ensure local reproducibility via Docker Compose
- Fail gracefully when upstream APIs have intermittent issues
- Label chain TVL responsibly when shown (chain aggregate, not per-asset)
