# Changelog

## 3.3.0 (2026-05-24)

### Removed

- **Traefik reverse proxy removed** — entire `traefik/` directory deleted, Traefik service block removed from compose
- **Prometheus scraper + Grafana removed** — `prometheus/` and `grafana/` directories deleted; services, volumes, secrets removed from compose
- **`web_gateway` external network removed** — all services now use `internal` network only
- **No secrets required for Quick Start** — `cloudflare_token`, `acme.json`, `grafana_admin_password` no longer needed
- **Dead `frontend/main.js` removed** — 1022-line vanilla JS file, superseded by Alpine.js rewrite

### Frontend

- **Forecast charts wired to API** — `renderForecastCharts()` now fetches real `ForecastRun`/`ForecastPoint` data instead of mock arrays
- **Theme toggle rebuilds charts** — `cycleTheme()` now redraws Chart.js/ECHarts after switching dark/light
- **dataQualityHistory populated** — wired from `dashboardResponse.data_quality`
- **Stale response guard** — trend chart discards responses from stale asset selections
- **`loadCorrelations` properly awaited** — no longer fires-and-forgets before render
- **Refresh error handling** — checks `r.ok` before proceeding after POST `/api/refresh`

### Hardening

- **`LOG_LEVEL` filtering wired** — `structlog.stdlib.filter_by_level` + `logging.basicConfig(level=...)`; `PrintLoggerFactory` replaced with `LoggerFactory`
- **Celery inspect timeout** — `inspect(timeout=2.0)` prevents health endpoint hangs
- **`previous_status` column on `SourceStatus`** — persisted in `_upsert_source_status` so recovery alerts fire correctly; Alembic migration `da39a3ee5e6b` added
- **Postgres pool hardening** — `pool_pre_ping=True`, `pool_recycle=3600` when `DATABASE_URL` is postgresql
- **SQLAlchemy pool_pre_ping/recycle** for Postgres reliability
- **Compose health conditions** — `frontend` depends on `backend` with `condition: service_healthy`; redis healthcheck via `redis-cli ping`
- **Celery `AI_MODE` default** aligned to `ai_off` (was `ai_lite`)
- **`depends_on` removed from default backend** — compose validates without `--profile data`
- **Structured logging on plugin failures** — `registry.py` logs `ml_plugin_import_failed` and `rss_fetch_failed` warnings with error context
- **`window_delta()` supports 90d** — aligns middleware, utils, and compare service
- **Sources routes rate-limited** — `@limiter.limit("60/minute")` on `/sources/status` and `/sources/{name}/config`
- **Flaky test fixed** — `test_event_dedup_window_positive` asserts exact `EVENT_DEDUP_MINUTES == 30`
- **numpy/sklearn pinned** in `requirements-dev.txt`
- **`prophet_forecast` renamed** to `statsforecast_supply` — accurate name for underlying StatsForecast/AutoARIMA implementation

### Config & Cleanup

- **`.env.example` cleaned** — `GRAFANA_ADMIN_PASSWORD`, `PROMETHEUS_RETENTION`, and Traefik TLS section removed
- **`.gitignore` cleaned** — `acme.json`, `prometheus/data/`, `grafana/data/` entries removed
- **`SECURITY.md` cleaned** — Traefik basic-auth and acme.json references removed
- **Dead imports removed** — unused `get_logger` in `routes/events.py`, `routes/trends.py`, `routes/dashboard.py`; unused `build_governance_payload` in `routes/analytics.py`
- **Forecast API key rename** — `"price"` → `"peg"` for historical data (mapped to depeg_index, not USD price)
- **`sys.path` fix** — repo root added to path so local `uvicorn backend.main:app` works from both repo root and `backend/` directory

### Fixed

- **Docker package structure fixed** — `backend/Dockerfile` now `COPY . /app/backend` + `WORKDIR /app/backend`, creating the `backend` package that `from backend.core.*` imports require; compose volume mounts updated from `/config` to `/app/config` to match new depth
- **Fresh clone runs out of the box** — `docker compose up` no longer crashes with `ModuleNotFoundError: No module named 'backend'`

### Developer Experience

- **Auto-backfill on first run** — when DB has fewer than 24 trend rows, automatically seeds 7 days of synthetic history per enabled asset; gated by `HELIX_SKIP_STARTUP_REFRESH` (same env var used in tests)
- **Dev compose no longer skips refresh** — `HELIX_SKIP_STARTUP_REFRESH` replaced with `ALLOW_BACKFILL: "true"` in override
- **`_internal` param on `run_backfill`** — bypasses `ALLOW_BACKFILL` env check for startup auto-backfill

## 3.2.0 (2026-05-23)

### Added

- **FinBERT sentiment plugin** (`ml_models/finbert/`) — registered `@register_model("finbert")`, `predict()`/`predict_batch()` with graceful fallback
- **Analytics engine** (`services/analytics.py`) — `compute_correlations()` (Pearson matrix + pair ranking), `detect_patterns()` (trend slope, volatility, day-of-week seasonality), `_pearson()` with edge case handling
- **Analytics routes** — `GET /analytics/correlations`, `GET /analytics/patterns`, `GET /analytics/finbert/sentiment`
- **Anomaly detector guard** — `predict()` returns safe fallback when `self.trained=False` (was crashing on sklearn `NotFittedError`)
- **ClickHouse schema** (`data/clickhouse/schema.sql`) — `ReplacingMergeTree` tables for asset/chain snapshots and forecast points
- **DatabaseManager** (`core/database_manager.py`) — lazy `clickhouse_connect` client with LZ4, `get_trend_history()` OLAP→OLTP fallback, batch writes
- **Data retention** — 6-table pruning with per-table env TTLs, ClickHouse `ALTER TABLE DELETE` path
- **Docker Compose ClickHouse service** — `clickhouse/clickhouse-server:24-alpine`, `data` profile, 1GB limit, initdb schema auto-load
- **Security middleware** — `SecurityValidationMiddleware` validates `asset` (A-Z0-9, 2-16 chars) and `window` (24h/7d/30d/90d), `sanitize_query_params()` redacts secrets
- **Observability middleware** — 5 Prometheus metrics (`helix_http_requests_total`, `helix_http_request_duration_seconds`, `helix_source_health`, `helix_model_inference_seconds`, `helix_cache_hit_ratio`), structlog structured request logging
- **Container hardening** — `no-new-privileges:true`, `cap_drop: ALL`, `read_only: true`, `tmpfs` on backend, celery-beat, celery-worker, timesfm
- **6-tab terminal UI** — Market, Forecast, Supply, Events, Intel, Health tabs with ECharts confidence bands, evidence drawer, command bar with search
- **Grant strategy** — 5 funding tracks identified (Alchemy, EF ESP, Optimism, Uniswap, Gitcoin) with application materials
- **Documentation** — `docs/adding-asset.md`, `docs/adding-chain.md`, `docs/plugins.md`, `docs/api.md`, `docs/grant-strategy.md`, `scripts/backup.sh`

### Fixed

- **Anomaly detector** no longer crashes on `NotFittedError` when called before training

### Tests

- **106 total tests** (was 53 at Phase 2, was 35 at Phase 1)

Next-level platform: reliability, VPS data plane, predictive core, optional AI router, terminal UI.

### Fixed

- **Scoring parity**: unified `signal_engine/risk_inputs.py` so dashboard and trend bundles use identical `compute_risk_score` inputs
- **Liquidity wiring**: forward DEX liquidity estimates (slippage, top-3 pool share) instead of hardcoded zeros; stop mapping supply 24h delta into TVL change
- **Source health**: per-source CoinGecko/DexScreener status; Prometheus `helix_source_health` reads DB instead of hardcoded `1`
- **AutoARIMA seasonality**: `season_length=288` for 5-minute buckets (daily cycle)

### Added

- **SQLite→Postgres migration**: `scripts/migrate_sqlite_to_postgres.py` with backup, row-level copy, and `--verify-only`; server runbook in gitignored `.progress/SERVER_MIGRATION.md`
- **Redis dashboard cache** (`ENABLE_REDIS_CACHE`), MLflow predictive logging, ONNX inference hook with heuristic fallback
- **Local handoff only**: `.progress/PHASE_LOG.md` (gitignored; not in repo)
- **VPS data profile** (`docker compose --profile data`): TimescaleDB, Redis (cache + Celery), Celery worker, MLflow
- **Alembic Timescale migration**: hypertables + `asset_signal_1h` continuous aggregate on PostgreSQL
- **Predictive API** (`GET /api/predictive`): regime, depeg probability horizons, expected shortfall — core ML, no LLM required
- **AI router** (`GET /api/ai/explain`): optional OpenRouter-lite → Ollama Cloud → Groq with `AI_MODE=ai_off|ai_lite|ai_full`
- **Celery tasks**: `worker_tasks.py` for refresh, predictive inference, AI enrichment
- **Terminal UI**: Outfit/Sora fonts, glass panels, SVG risk gauge, event ticker, predictive readout
- **VPS deploy notes** inlined in `docs/architecture.md` (no separate internal ops doc in git)

### Fixed (prior unreleased)

- **Dashboard blank page**: restored full Alpine.js shell in `frontend/index.html`; moved app logic to `frontend/app.js`; fixed Chart.js trend syntax error blocking Alpine init
- **`metrics.py` crash**: added missing `timezone` import that broke DefiLlama source status updates and trend persistence
- **Attestation conflation**: split issuer report age from DefiLlama supply feed freshness in `/api/osint/attestation` and UI (no synthetic attestation dates)
- **Overview attestation panel**: loads on dashboard init, not only after visiting Intel tab

### Added

- **`scripts/smoke-check.sh`**: post-deploy checks for frontend shell markers, API health, and blocked public `/metrics`
- **Hourly attestation refresh**: OSINT scheduler job calls `refresh_attestation_reports(force=True)`

### Changed

- **Frontend nginx**: return 404 for `/metrics` at the edge

## v3.1.0 — Maintenance & Quality

### Changed
- **DB session wiring**: Replaced all `SessionLocal()` + `try/finally` patterns with FastAPI `Depends(get_db)` dependency injection across all 20+ API routes
- **Alert rule evaluator**: Replaced fragile string-matching (`if "depeg_bps > 50" in cond`) with a callable registry (`@_register_condition` decorator + longest-prefix matching) for maintainable rule evaluation
- **HTTP client**: Migrated all network calls from `requests` sync to `httpx.Client` across `base.py`, `defillama.py`, `coingecko.py`, `alerts.py`, `osint.py`, `governance.py`

### Fixed
- **`anomaly.py` crash**: Added `numpy` and `pandas` at module level (were only imported lazily inside `zscore_detect`, causing `NameError` in `isolation_forest_detect`, `train_models`, and `prophet_forecast`)
- **`osint.py`**: Restored missing `_fetch_rss`, `_fetch_cryptopanic`, and `_classify_asset` functions (were referenced but not defined)

### Added
- **Alembic migrations**: Initialized migration directory, autogenerated `initial_schema` migration, added to `requirements.txt`
- **Dead file protection**: `frontend/main.js` (1022-line dead vanilla JS — superseded by Alpine.js) added to `.gitignore`

### Removed
- 5 stale execution briefs deleted from root: `initial_BRIEF.md`, `V2.0`, `V2.1`, `V2.2`, `V2.3` briefs

## v3.0.0 - OSINT Intelligence Terminal

### Added
- **V3 Risk Score**: 5-component composite (peg stability 35%, liquidity depth 25%, supply stability 15%, concentration 15%, observability 10%) with hard overrides for depeg >200bps and data staleness
- **Multi-source engine**: AbstractSource base class + CoinGecko (price, market cap, volume), DEX Screener (liquidity depth, pool concentration, slippage), Chainlink (optional on-chain oracle)
- **Cross-source price validator**: flags discrepancies >0.5% between DefiLlama and CoinGecko
- **Alerting system**: 9 rule types (peg deviation, slippage spike, supply contraction, concentration spike, data staleness, source failure/recovery) with persistence tracking, dedup, 4 dispatch channels (dashboard, webhook, Discord, Telegram)
- **OSINT feed**: RSS ingestion (Coindesk, CoinTelegraph, The Block) + CryptoPanic API + FinBERT sentiment scoring
- **Governance monitoring**: contract upgrade tracking via Etherscan API
- **AI anomaly detection** (gated): Z-score rolling 3σ, Isolation Forest multi-metric anomaly, Prophet 24h supply/depeg forecast — enabled via `ENABLE_ANOMALY_DETECTION=true`
- **DuckDB analytics**: embedded time-series queries on trend data
- **17 chains**: Tron, Ethereum, BSC, Solana, Arbitrum, Polygon, Avalanche, Optimism, Base, Celo, Fantom, Gnosis, zkSync Era, Aptos, TON, Plasma, NEAR
- **Alpine.js + htmx frontend**: 4-tab layout (Overview, Peg & Liquidity, Supply & Flows, Intelligence), CDN-loaded, zero build step
- **Chart.js wiring**: distribution + supply bar charts, sentiment overlay, attestation status

### Phase 6 — Production Hardening
- **Traefik reverse proxy**: auto-TLS via Let's Encrypt, Docker provider, dashboard
- **Prometheus `/metrics` endpoint**: request count, latency histogram, scheduler health, source health gauges, DB connection count
- **Prometheus + Grafana stack**: managed via docker-compose, pre-provisioned datasource and dashboard
- **CI/CD pipeline**: GitHub Actions → lint → test → Docker build → push to GHCR on tags
- **Integration tests**: vcr.py for recorded API responses (DefiLlama, CoinGecko, DEX Screener)
- **docker-compose.override.yml**: dev mode with hot-reload, debug logging
- **Secrets management**: Docker secrets for Grafana admin password
- **Version**: bumped to 3.0.0

### Documentation
- Updated README, .env.example for V3 endpoints and monitoring stack
- Updated CHANGELOG for full V3 history

## v2.5.0 - Trust the terminal

### Added

- **CI**: GitHub Actions workflow runs import smoke and pytest from `backend/.venv` pattern in CI (venv created in workflow).
- **Tests**: `backend/tests/` with pytest for scoring, history bucketing, and API smoke (in-memory SQLite).
- **Health**: `GET /api/health` with `status`, `db`, `last_successful_fetch`, `scheduler_running`, and `version` `2.5.0`.
- **Retention**: Daily job prunes trend rows (`TREND_RETENTION_DAYS`, default 90) and events (`EVENT_RETENTION_DAYS`, default 30).
- **Deploy**: Compose uses `.env`; frontend nginx proxies `/api` to backend; dashboard uses same-origin relative API paths.
- **Exports**: `GET /api/trends/export` and `GET /api/events/export` (CSV or JSON, max 10k rows) plus UI export buttons.
- **Compare**: `GET /api/compare?assets=USDT,USDC&window=7d` and dashboard multi-line chart.
- **Chain drill-down**: `GET /api/chains/{chain_key}?asset=USDT` and clickable chain rows with side panel.
- **Optional backfill**: `POST /api/admin/backfill` when `ALLOW_BACKFILL=true` (7–30 days, synthetic labeled rows).
- **Refactor**: Dashboard assembly moved to `backend/services/dashboard.py`.

### Fixed

- Duplicate `isinstance(rows, list)` guard in `sources/defillama.py`.
- Documented `DEFILLAMA_API_KEY` as reserved (free DefiLlama endpoints used).

### Documentation

- Updated README, architecture, methodology, CONTRIBUTING, and RELEASE_NOTES for V2.5.
- `.gitignore` patterns for V2.5 internal execution brief filenames.

### Out of scope (unchanged)

- External alerts, webhooks, paid APIs, Moralis, auth, Postgres or dedicated time-series stores, framework migrations, plugins, GraphQL, hosted cloud tiers.

## v2.4.0 - Historical Trends and Signal Feed

### Added

- Historical trend snapshot storage for asset-level and chain-level monitoring (5-minute UTC buckets, SQLite).
- Trend APIs: `GET /api/trends`, `GET /api/trends/chains` with `window` in `24h`, `7d`, or `30d`.
- Signal event feed stored locally with deduplication, plus `GET /api/events` (optional `asset` filter).
- Dashboard trend charts for signal score, Depeg Index, total supply, and concentration score, plus a compact event feed panel with low-data messaging.
- Shared metric bundle helper in `signal_engine/metrics.py` for consistent snapshot values.

### Documentation

- Updated `README.md`, `docs/data-methodology.md`, `docs/architecture.md`, `CONTRIBUTING.md`, and `RELEASE_NOTES.md` for V2.4.
- Extended `.gitignore` for the V2.4 internal brief filename.

### Out of scope (unchanged)

- External alerts, webhooks, paid APIs, Moralis, auth, Postgres or dedicated time-series stores, framework migrations, plugins, GraphQL, hosted cloud tiers, long historical backfill.

## v2.3.0 - Helix Signal Score and monitoring dashboard

### Added

- **Helix Signal Score**: transparent 0 to 100 composite with Normal, Watch, and Risk bands; explicit 35% / 25% / 20% / 20% component weights returned in `/api/dashboard`
- **Depeg Index** and **chain concentration** (HHI and top share) in the dashboard API and UI
- **Derived metrics**: aggregate total supply, aggregate 24h supply change, per-chain supply momentum labels, chain share, per-chain signal and data confidence
- **Server-side `freshness` object** in `/api/dashboard` using UTC basis `max(last_successful_fetch, newest_chain_snapshot)` and refresh-interval-derived windows
- **Chain TVL** restored as optional **chain-level aggregate** context from DefiLlama `stablecoinchains`, with clear labeling in API and UI (not per-asset TVL)
- Premium-style dashboard layout: KPI strip, methodology and insight panels, Chart.js share and component charts, expanded chain table

### Fixed

- Freshness and source timing inconsistencies by computing freshness on the server and consuming it in the frontend (avoids client-only max timestamp mistakes)
- Refresh pipeline now tracks **maximum** successful per-asset fetch time when updating `last_successful_fetch` so multi-asset passes do not appear artificially stale

### Documentation

- Updated `README.md`, `docs/data-methodology.md`, `docs/architecture.md` for V2.3
