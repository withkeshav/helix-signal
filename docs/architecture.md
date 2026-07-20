# Architecture (V4)

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
    +--> /api/osint/*, /api/governance
    +--> POST /api/refresh
            |
            +--> signal_engine (scoring, metrics, history)
            +--> services/dashboard.py (dashboard assembly)
            v
Alpine.js + ECharts frontend (index.html + init.js)
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
SQLite at /data/helix.db (volume helix_data) - default local profile

Optional VPS data profile:

```text
postgres (TimescaleDB)  redis (cache + broker)
    |                        |
    +---- backend:8000       +---- (APScheduler in-process)
```

**VPS (single-node):** cap Redis at 128MB; set Postgres `shared_buffers` ~25% RAM on the host; keep `AI_MODE=ai_off` unless you need LLM summaries. Add a host swap file before enabling Timescale compression.

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
- Signal engine: ingest, V4 scoring via `risk_inputs.py`, 5-minute buckets, deduplicated events
- **`osint.py` decomposed** → `attestation.py` (reserve parsing + freshness) + `rss_feed.py` (RSS sentiment) with backward-compatible re-exports
- **`services/scheduler.py`** - 11 job functions extracted from `main.py` (409→190 lines) via `register_scheduler_jobs()`
- **`services/dashboard.py`** - `build_dashboard_response` decomposed: 274→31 lines orchestration + 6 sub-functions
- **`data_quality/`** - Freshness, cross-source validation, coverage checks using SA 2.0 style
- **SA 2.0 migration** - All 63 `db.query()` calls in production code converted to `select()` + `execute()`
- **Predictive** (`services/predictive.py`): statistical/ML outputs - always available without LLM
- **AI router** (`services/ai_router.py`): optional explanations; `AI_MODE=ai_off` keeps core APIs unchanged; optional `ai_require_token` gate; usage tracked (no hard token budget)
- **Web search cache** (`services/web_search/`): scheduled only - job `web-search-refresh` (06:15 & 18:15 UTC) + optional startup-once if cache stale; table `web_search_snapshots`; chain Tavily → Exa → Ollama search; **opt-in only when Tavily and/or Exa secret present** (Ollama alone never enables); AI injects cached `WEB_CONTEXT` on `/api/ai/*` - never live search on HTTP path
- **Insight assets** (`services/insight_assets.py`): deterministic snapshots on schedule; LLM narratives via `/api/ai/*` not the insight job
- **APScheduler** runs all periodic jobs in-process (ingest, OSINT, retention, quality, web search, fiat scrape, …) - no separate worker needed
- **CORS origins** loaded from env at module level (safe before `init_db()`). DB setting (`cors_origins`) loaded into `app.state.cors_origins` after DB init for future live-refresh on Settings update.
- **Settings priority** (`providers/settings.py`): runtime reads use **DB → env → default**. Secrets use Fernet when `SETTINGS_ENCRYPTION_KEY` is set. `GET /api/settings` never returns raw secrets (`"configured"` only). Constrained strings are exposed as `type=enum` with `options` for Control Room selects. Import skips masked secret sentinels so export→import cannot clobber live keys.

### Data Store

- SQLite (`backend/helix.db` locally; `/data/helix.db` in Docker)
- In-memory SQLite for pytest uses `StaticPool` so tables persist across connections
- **AssetFreshness** has a `UNIQUE` constraint on `asset_symbol`; upserts use `db.merge()` for race-free concurrent refreshes

### Frontend (`frontend/`)

- `index.html` - dashboard shell, Alpine.js bindings, CDN ECharts + **Tabler CSS** layout base
- `js/init.js` - Alpine root (`helixApp`), Cmd+K, refresh loop; tab/asset synced with `$store.ui` / `$store.dashboard`
- `js/stores/` - **source of truth**: `dashboard.js` (shared risk data), `ui.js` (tab/auth/theme/refreshTick)
- `js/composables/` - per-tab panels: Signal `market`, Market supply/forecast, Intel, Forensics, Alerts, System, Settings Control Room
- `js/charts.js` - ECharts + `helixTheme()`; sparklines for global strip
- `js/utils.js` - formatUsd, formatWhen, etc.
- `styles.css` - Helix tokens override Tabler; glass, skeleton, Control Room, hero
- **IA:** Signal is answer-first home (risk + **fundamentals** yield/collateral/reserve); Market = forecasts/supply; Intel = OSINT; Forensics = investigate; Settings = single-admin Control Room
- **Data plane:** Moralis refresh persists `whale_activity_snapshots`; fiat reserve daily scrape is best-effort; Market tab bootstraps dashboard store without visiting Signal
- nginx: same-origin `/api`; `^~ /admin` → SQLAdmin; CSP allows `cdn.jsdelivr.net` for ECharts/Alpine/Tabler
- Compose project name **`helix-signal`** → volume `helix-signal_postgres_data` (never `down -v` on upgrade)

## Local development

Python dependencies install only into `backend/.venv`:

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
export PYTHONPATH=..   # so backend.sources.plugins resolves from backend/
.venv/bin/uvicorn main:app --reload
```

CI mirrors this pattern (venv created in the workflow job).

Post-deploy validation:

```bash
./scripts/smoke-check.sh https://your-host.example
```

## Test coverage

- **Backend:** pytest suite (`cd backend && python -m pytest`) - ~560+ cases as of v4.4.0

## Data assets (v4.1.0+ / post-4.4.0)

- **`data_quality_snapshots`** - daily persisted quality metrics; `GET /api/data-quality/summary` serves the latest row.
- **`insight_assets`** - versioned deterministic insight objects; GET path is deterministic-only (no LLM on request).
- **`whale_activity_snapshots`** - written when Moralis is configured during on-chain refresh (not cache-only).
- **`fiat_reserve_snapshots`** - optional daily scrape job (`fiat-reserve-scrape`); failures isolated.
- **`fred_yields`** - FRED macro series in Postgres (v4.4.0+); DuckDB mirror optional during cutover.
- **`webhook_endpoints`** - multi-destination signed alert routing (v4.4.0+).
- **`ai_providers`** - OpenAI-compatible LLM registry (v4.4.0+).

## Public display policy (v4.4.0+)

Anonymous visitors read `/api/public/config` for effective history hours (default 24), tab/export/forensics flags, and demo mode window. Admin session bypasses clamps on authenticated `/api/*` routes.

## Settings Control Room (v4.1.0+)

Tier 0: optional first-run wizard. Tier 1: Settings Control Room (7 sub-tabs including **Display & Access**, ~30 high-touch keys + secret rotate). Tier 2: SQLAdmin at `/admin` for full registry / rare table ops. Auth is single-admin (seeded user), not multi-user self-service.

## OLAP / DuckDB (v4.0.7+)

DuckDB is **not** an active analytics mirror in 4.0.x. `core/olap.py` provides only the shared connection; **`fred_yields`** is maintained in **Postgres** (v4.4.0+) with an optional DuckDB mirror in `chain/fred_api.py`. Seven unused mirror schemas were removed in v4.0.7 (WO-BE-7a).
- **Frontend E2E:** 15 Playwright specs in `frontend/e2e/` covering Signal, Market, Analytics, Intel, Forensics, Alerts, System, Settings. Run with `FRONTEND_PORT=3080 docker compose up -d --build frontend` then `cd frontend && npx playwright test --project=chromium`. See [README E2E section](../README.md#e2e-tests-playwright).

## Design Intent

- Keep frontend thin; centralize logic on the backend
- Self-hosted reproducibility via Docker Compose and pytest regression checks
- Fail gracefully on upstream errors; label chain TVL as chain aggregate context
- Do not fabricate attestation dates - show issuer report age and supply feed freshness separately
