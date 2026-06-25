# Architecture (V3)

Helix-Signal follows a backend-first architecture with a thin static frontend.

## High-Level Flow

```text
DefiLlama (+ CoinGecko, DEX Screener, optional Chainlink)
    |
    v
FastAPI backend (scheduler: ingest + OSINT + retention)
    |
    v
SQLite or PostgreSQL/Timescale (snapshots, trends, events, OSINT)
    |
    +--> /api/health, /api/assets, /api/dashboard
    +--> /api/trends (+ export), /api/events (+ export), /api/compare
    +--> /api/chains/{chain_key}, /api/osint/*, /api/governance
    +--> POST /api/refresh
            |
            +--> signal_engine (scoring, metrics, history)
            +--> services/dashboard.py (dashboard assembly)
            v
Alpine.js + Chart.js frontend (index.html + app.js)
    |
    +-- Docker: nginx proxies /api -> backend:8000 (same-origin relative URLs)
    +-- /metrics blocked at nginx
```

## Deploy topology (production)

```text
Internet
    |
    v
frontend:80  (/api/* proxied to backend:8000, static assets)
    |
    v
backend:8000 (internal network only)
    |
    v
SQLite at /data/helix.db (volume helix_data) — default local profile

Optional VPS data profile (`docker compose --profile data`):

```text
postgres (TimescaleDB)  redis (cache + Celery broker)
    |                        |
    +---- backend:8000       +---- celery-worker
    +---- mlflow:5000
```

**VPS (single-node):** use `docker compose --profile data`; cap Redis at 128MB; set Postgres `shared_buffers` ~25% RAM on the host; keep `AI_MODE=ai_off` unless you need LLM summaries. Add a host swap file before enabling Timescale compression or Celery ML tasks.

**SQLite → Postgres cutover:** run `scripts/migrate_sqlite_to_postgres.py` after backups; use `--verify-only` before switching `DATABASE_URL`. Local step-by-step runbook: `.progress/SERVER_MIGRATION.md` (not in git).
```

Reference deployment: [https://helix.withkeshav.com](https://helix.withkeshav.com)

Environment is loaded from `.env` (copy from `.env.example`). Secrets (`secrets/`, `.env`) stay out of git.

## Components

### Backend (`backend/`)

- **Routes** in `main.py`; dashboard assembly in `services/dashboard.py`
- **Health** (`GET /api/health`): DB ping, scheduler status, version
- **OSINT** (`services/osint.py`): RSS/CryptoPanic ingestion, sentiment, attestation report parsing, supply feed freshness from DefiLlama source status
- **Retention**: daily cron job in `services/retention.py`
- APScheduler: interval ingest + hourly OSINT + retention
- Signal engine: ingest, V3 scoring via `risk_inputs.py`, 5-minute buckets, deduplicated events
- **Predictive** (`services/predictive.py`): statistical/ML outputs — always available without LLM
- **AI router** (`services/ai_router.py`): optional explanations; `AI_MODE=ai_off` keeps core APIs unchanged; optional `AI_REQUIRE_TOKEN` gate with per-IP lockout after 20 failed attempts; pre-flight budget deduct in `enrich_with_ai()`
- **Celery** (`celery_app.py`, `worker_tasks.py`): background refresh and inference when Redis profile is enabled

### Data Store

- SQLite (`backend/helix.db` locally; `/data/helix.db` in Docker)
- In-memory SQLite for pytest uses `StaticPool` so tables persist across connections

### Frontend (`frontend/`)

- `index.html` — dashboard shell, Alpine.js bindings, CDN Chart.js + ECharts
- `js/init.js` — Alpine component (`helixApp`), chart wiring, tab loaders
- `js/stores/` — Alpine stores: `dashboard.js` (shared data), `ui.js` (tab/admin/theme)
- `js/composables/` — Alpine components (per-tab x-data): `useMarket.js`, `useOSINT.js`, `useSMIDGE.js`, `useForecast.js`, `useGovernance.js`
- `js/charts.js` — Chart.js + ECharts rendering (extracted from init.js)
- `js/utils.js` — Shared utility functions (formatUsd, formatWhen, etc.)
- `styles.css` — Design system: tokens, glass, elevation, skeleton, icon utilities
- 5-tab layout: Signal (hero gauge + AI summary + risk/charts) | Market (forecast + supply) | Intel (OSINT + SMIDGE) | System (health + quality) | Settings (governance)
- nginx in Docker: same-origin `/api` proxy; `return 404` for public `/metrics`
- Frontend container binds to host port 80 (mapped from container port 80)
- Content-Security-Policy uses SHA-256 hashes to allow specific inline scripts (like importmap) without using 'unsafe-inline'

## Local development

Python dependencies install only into `backend/.venv`:

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

CI mirrors this pattern (venv created in the workflow job).

Post-deploy validation:

```bash
./scripts/smoke-check.sh https://your-host.example
```

## Design Intent

- Keep frontend thin; centralize logic on the backend
- Self-hosted reproducibility via Docker Compose and pytest regression checks
- Fail gracefully on upstream errors; label chain TVL as chain aggregate context
- Do not fabricate attestation dates — show issuer report age and supply feed freshness separately
