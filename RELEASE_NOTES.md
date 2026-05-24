# Release Notes

## v3.3.0 — Stack Simplification & Audit Fixes

Major infrastructure cleanup: Traefik, Prometheus, and Grafana removed from the stack. Comprehensive P0–P3 audit fixes applied across the entire codebase. Frontend forecast charts finally wired to real API data. Auto-backfill on first run gives immediate historical data for new deployments.

**106 tests pass.** Zero paid API dependencies.

### Highlights

- **Traefik/Prometheus/Grafana removed** — no more TLS secrets, `cloudflare_token`, `acme.json`, `web_gateway` network, or monitoring containers. Frontend serves directly on port 80.
- **P0 blockers fixed** — `depends_on` removed from default-profile backend (compose validates without `--profile data`); dead `_get_http_session` calls replaced with `httpx.Client()` context managers
- **P1 behavior fixes** — `LOG_LEVEL` filtering wired, Celery health timeout added, forecast charts use real API data, sources routes rate-limited, `previous_status` tracking for recovery alerts, 90d window support, numpy/sklearn pinned
- **P2 hardening** — compose health conditions (`frontend`→`backend` with `service_healthy`, redis healthcheck), AI_MODE aligned, Postgres `pool_pre_ping`/`pool_recycle`, flaky test fixed, structured logging on plugin/RSS failures
- **P3 cleanup** — `prophet_forecast` → `statsforecast_supply`, dead imports removed, stale Grafana/Traefik references purged from docs and gitignore
- **Auto-backfill** — fresh databases get 7 days of historical data seeded automatically on first boot
- **Alembic migration** — `da39a3ee5e6b` adds `previous_status` column for Postgres users

See `CHANGELOG.md` for the full list of changes.

## Unreleased — Next-level platform

Reliability, VPS-ready data plane, predictive intelligence, and optional AI — core risk engine runs with `AI_MODE=ai_off`.

### Highlights

- **Unified risk scoring** across dashboard and historical trends; liquidity metrics wired from DEX data
- **Single-node Compose profile**: TimescaleDB + Redis + Celery + MLflow (`docker compose --profile data up`)
- **Predictive layer** (`/api/predictive`): regime, depeg probability, ES — no external LLM dependency
- **AI-lite router** (`/api/ai/explain`): OpenRouter-lite / Ollama / Groq with token budget and graceful fallback
- **Risk terminal UI**: glass panels, animated gauge, event ticker, predictive readout
- **Contributor handoff**: local `.progress/PHASE_LOG.md` only (gitignored)

See `CHANGELOG.md` for the full list.

## v3.1.0 — Maintenance & Quality

Helix-Signal v3.1.0 is a maintenance release fixing critical bugs, eliminating technical debt, and improving code quality.

### Highlights

- **Fixed anomaly.py crash**: numpy/pandas now imported at module level (was causing NameError in production)
- **DB session refactor**: Replaced 20+ `try/finally` blocks with FastAPI `Depends(get_db)` dependency injection
- **Alert evaluator rewrite**: Replaced fragile `in` string-matching with a callable registry using `@_register_condition` decorator
- **HTTP client migration**: All network calls migrated from `requests` to `httpx` across 6 source/service files
- **Alembic migrations**: Initialized automated migration system (`alembic upgrade head`)
- **Restored missing functions**: `osint.py` had 3 referenced but undefined functions (`_fetch_rss`, `_fetch_cryptopanic`, `_classify_asset`)
- **Cleanup**: 5 stale execution briefs deleted; dead `frontend/main.js` gitignored

See `CHANGELOG.md` for the full list of changes.

## v2.5.0 - Trust the terminal

Helix-Signal v2.5 focuses on **operational maturity** and **analyst ergonomics** on top of the V2.4 trend and event memory layer.

### Highlights

- GitHub Actions CI and pytest (`backend/.venv` locally; venv in CI workflow)
- `GET /api/health` for deploy and uptime checks
- SQLite retention job and Compose/nginx deploy fixes
- Trend and event CSV/JSON export, cross-asset compare, chain drill-down
- Optional env-gated backfill for synthetic daily seed points

See `CHANGELOG.md` for the full list.

## v2.4.0 - Historical Trends and Signal Feed

Helix-Signal v2.4 adds **forward-collected historical trends**, **REST trend endpoints**, and a **local signal event feed** while keeping the V2.3 stack (FastAPI, SQLite, Vanilla JS + Chart.js) and the Helix Signal Score, Depeg Index, server freshness model, manual refresh endpoint, and labeled chain aggregate TVL behavior.

### Highlights

- Trend charts on the dashboard with 24h, 7d, and 30d windows and explicit low-data states for new installs
- SQLite-backed `asset_trend_snapshots`, `chain_trend_snapshots`, and `signal_events` tables
- `/api/trends`, `/api/trends/chains`, and `/api/events` for programmatic access

See `CHANGELOG.md` for the full list of changes.

## v2.3.0 - Helix Signal Score

Helix-Signal v2.3 adds a transparent **Helix Signal Score**, **Depeg Index**, derived aggregate metrics, **server-side freshness**, and a richer monitoring-style dashboard while keeping the same stack (FastAPI, SQLite, Vanilla JS + Chart.js).

### Highlights

- Dashboard API exposes scoring components with documented weights
- Optional **Chain TVL** column labeled as chain-level aggregate context from DefiLlama `stablecoinchains`
- KPI strip, methodology panel, and Chart.js visualizations for share and subscores

See `CHANGELOG.md` for the full list of changes and fixes.

## v1.0.0 - Initial Release

Helix-Signal v1.0.0 introduces the first public version of Helix: a self-hostable USDT chain signal dashboard powered by FastAPI, SQLite, and a static Vanilla JS + Chart.js frontend.
