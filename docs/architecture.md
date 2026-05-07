# Architecture (V1)

Helix-Signal follows a backend-first architecture.

## High-Level Flow

```text
DefiLlama APIs
    |
    v
FastAPI backend (scheduler + signal engine)
    |
    v
SQLite cache (chain_data, source_status)
    |
    v
/api/dashboard (precomputed payload)
    |
    v
Vanilla JS + Chart.js frontend
```

## Components

### Backend (`backend/`)

- FastAPI application with:
  - `/` health-style greeting endpoint
  - `/api/dashboard` for frontend consumption
- APScheduler background job refreshes source data periodically
- Signal engine parses and normalizes USDT metrics
- SQLAlchemy models persist latest snapshots in SQLite

### Data Store

- SQLite database (`backend/helix.db`)
- Core tables:
  - `chain_data`: per-chain current + previous supply values, tvl, price, timestamps
  - `source_status`: source health, last attempt/success/error details

### Frontend (`frontend/`)

- Static HTML/CSS/JS
- Fetches a single dashboard payload from backend
- Renders:
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
