# Architecture (V2.5)

Helix-Signal follows a backend-first architecture with a thin static frontend.

## High-Level Flow

```text
DefiLlama stablecoins APIs (+ stablecoinchains for chain TVL context)
    |
    v
FastAPI backend (scheduler: ingest + daily retention)
    |
    v
SQLite cache (snapshots, trends, events)
    |
    +--> /api/health, /api/assets, /api/dashboard
    +--> /api/trends (+ export), /api/trends/chains
    +--> /api/events (+ export), /api/compare
    +--> /api/chains/{chain_key}, POST /api/admin/backfill (optional)
    +--> POST /api/refresh
            |
            +--> signal_engine (scoring, metrics, history)
            +--> services/dashboard.py (dashboard assembly)
            v
Vanilla JS + Chart.js frontend
    |
    +-- Docker: nginx proxies /api -> backend:8000 (same-origin relative URLs)
```

## Deploy topology (Docker Compose)

```text
Browser -> frontend:80 (/api/* proxied) -> backend:8000
                \-> static dashboard assets
Backend -> SQLite at /data/helix.db (volume helix_data)
```

Environment is loaded from `.env` (copy from `.env.example`).

## Components

### Backend (`backend/`)

- **Routes** in `main.py`; dashboard assembly in `services/dashboard.py`
- **Health** (`GET /api/health`): DB ping, last successful fetch, scheduler running, version `2.5.0`
- **Retention**: daily cron job in `services/retention.py` (`TREND_RETENTION_DAYS`, `EVENT_RETENTION_DAYS`)
- **Exports**: `services/exports.py` — CSV/JSON, max 10k rows
- **Compare / chain detail / backfill**: `services/compare.py`, `chain_detail.py`, `backfill.py`
- APScheduler: interval ingest (unless `HELIX_SKIP_STARTUP_REFRESH` for tests) + retention
- Signal engine unchanged in role: ingest, scoring, 5-minute buckets, deduplicated events

### Data Store

- SQLite (`backend/helix.db` locally; `/data/helix.db` in Docker)
- In-memory SQLite for pytest uses `StaticPool` so tables persist across connections

### Frontend (`frontend/`)

- Same-origin `/api` when served behind nginx in Compose
- `window.HELIX_API_ROOT` optional override for split-host dev
- V2.5 UI: export buttons, compare chart, chain drill-down side panel

## Local development

Python dependencies install only into `backend/.venv`:

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

CI mirrors this pattern (venv created in the workflow job).

## Design Intent

- Keep frontend thin; centralize logic on the backend
- Self-hosted reproducibility via Docker Compose and pytest regression checks
- Fail gracefully on upstream errors; label chain TVL as chain aggregate context
