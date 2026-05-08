# Architecture (V2.1)

Helix-Signal follows a backend-first architecture.

## High-Level Flow

```text
DefiLlama stablecoins APIs
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
            v
Vanilla JS + Chart.js frontend with asset selector
```

## Components

### Backend (`backend/`)

- FastAPI application with:
  - `/` health-style greeting endpoint
  - `/api/dashboard` with optional `asset` query parameter
  - `/api/assets` for enabled asset listing
- APScheduler background job refreshes source data periodically
- Signal engine parses and normalizes asset-chain snapshots for enabled assets
- SQLAlchemy models persist latest snapshots in SQLite

### Data Store

- SQLite database (`backend/helix.db`)
- Core tables:
  - `asset_chain_snapshots`: per asset + chain current/previous supply values, tvl, price, peg metadata, timestamps
  - `source_status`: source health, last attempt/success/error details

### Frontend (`frontend/`)

- Static HTML/CSS/JS
- Loads enabled assets and fetches selected-asset dashboard payloads
- Renders:
  - asset-aware title and supply column
  - main chain table
  - 24h change signal badges
  - peg status
  - sparklines with Chart.js
  - source health footer

## Design Intent

- Keep frontend thin and deterministic
- Centralize data logic in backend for consistency
- Ensure local reproducibility via Docker Compose
- Fail gracefully when upstream APIs have intermittent issues
