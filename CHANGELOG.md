# Changelog

## 3.8.0 (2026-05-27)

### Added

- **Supply velocity & acceleration signals** — New `services/velocity.py` computes 1h/4h/12h/24h rolling supply deltas and acceleration (second derivative) from existing 5-minute `AssetTrendSnapshot` buckets. Velocity feeds into scoring as a new risk component.
- **Regime detection** — `detect_regime()` in `services/analytics.py` classifies current state as `stable` / `elevated` / `crisis` using composite score + depeg index thresholds. Tracks duration and 48h transition count. Exposed via `GET /api/analytics/regime`.
- **Cross-asset rotation signals** — `cross_asset_rotation()` in `services/analytics.py` computes supply-change correlations between asset pairs (e.g. USDT vs USDC) to detect "flight to safety" patterns. Exposed via `GET /api/analytics/rotation?assets=USDT,USDC`.
- **CUSUM change-point detection** — `detect_change_points()` in `services/anomaly.py` applies Cumulative Sum (CUSUM) on depeg index, supply, and concentration to detect sustained regime shifts missed by fixed z-score. Exposed via `GET /api/anomaly/change-points`.
- **Stress Leaderboard** — `services/stress.py` ranks chains by supply velocity (24h/7d) with direction labels. New `GET /api/analytics/stress-leaderboard` endpoint + frontend card in Overview tab.
- **Metric-specific anomaly thresholds** — Different z-score sensitivities per metric: price (z>2.5, min_bps=5), supply (z>3.5, min_bps=15), depeg index (z>2.5, min_bps=5), reducing false positives while catching earlier price stress.

### Changed

- **Risk score weights rebalanced** — Peg stability 35% → 30%, concentration 15% → 20% per 2025/2026 LEGO & ASRI research evidence on downstream concentration as a primary failure mode.
- **Temporal decay on supply deltas** — Exponential decay (half-life ~7 days) applied to 24h and 7d supply changes inside `supply_stability_component`, weighting recent data higher than older history.
- **Dashboard integration** — Supply velocity outputs merged into `risk_kwargs` before `compute_risk_score()` call, enabling velocity-aware scoring without breaking the existing API contract.
- **Anomaly endpoint extended** — `z_score` results now include `depeg_index` alongside `supply` and `price` for unified monitoring.

## 3.7.0 (2026-05-27)

### Added

- **AI Settings UI** — New "AI & Anomaly Detection" card in Settings tab with mode select (Off/Lite/Full), toggle switches, and number inputs for token budget, cache TTL, web search config
- **Token budget dashboard** — `GET /api/ai/budget` endpoint exposes `daily_budget`, `tokens_used_today`, `tokens_remaining`, `pct_used` with progress bar in frontend
- **DB-backed AI settings** — `ai_mode`, `ai_daily_token_budget`, `ai_cache_ttl_seconds`, `ai_web_search`, `ai_web_search_max_results`, `enable_anomaly_detection` registered in `_DEFAULT_SETTINGS` and editable via Settings UI
- **OpenRouter free tier** — `openrouter/free` model added as primary provider in `ai_lite` and `ai_full` chains; configurable via `OPENROUTER_FREE_MODEL` env var
- **Redis cache for AI responses** — `_try_redis_cache()` / `_cache_set` with `helix:ai:cache:` prefix; falls back to in-memory dict
- **`latest_zscore()`** — Returns latest point's z-score, bps, and anomaly flag for real-time monitoring
- **`min_bps` filter on `zscore_detect()`** — Suppresses tiny statistical fluctuations
- **`STD_FLOOR` env var** — Prevents division-by-near-zero in z-score computation (`ANOMALY_STD_FLOOR`, default 0.001)
- **`sync-env.sh`** — Merges new keys from `.env.example` into `.env` preserving existing values
- **Health endpoint** — `redis_connected` and `db_connected` fields in `/api/health` response
- **`_fetchAi` helper** — Consolidated 4 redundant AI loader methods in `osint.js` into a single `_fetchAi()` helper
- **Chart module extraction** — All chart methods extracted from `init.js` into `frontend/js/charts.js` (12 exported functions, ECharts lazy-load via dynamic `import()`)
- **`frontend/styles.css`** — External stylesheet extracted from inline `<style>` in `index.html`; `.kpi-placeholder` pulse animation, `.empty-state` styles with icon support
- **Empty-state placeholders** — Missing empty states added for Market Overview, AI Narrative, AI Insights, Anomaly Events, and Supply tab
- **CI hadolint + Trivy** — Hadolint Dockerfile linting and Trivy vulnerability scan (HIGH/CRITICAL, exit-code 1) added to CI pipeline
- **CI SSH deploy job** — Automated deploy on `v*` tag push via SSH + docker-compose
- **`.dockerignore`** — `backend/.dockerignore` excludes venv, pyc, coverage, egg-info, pytest cache, git

### Changed

- **Budget tracking refactored** — `_deduct_tokens()` replaces `_within_budget()`: deducts actual tokens returned (not estimated pre-pay), supports Redis and local modes uniformly
- **Provider chain reordered** — OpenRouter free → Ollama Cloud → Groq in `ai_lite`; free → fallback → primary → Groq in `ai_full` priority mode
- **`.env.example`** — AI section reorganized with OpenRouter first, `AI_CACHE_TTL_SECONDS` default bumped from 1800→3600
- **Docker images pinned** — `timescaledb:2.26.4-pg16`, `clickhouse-server:26.3.10.60-alpine`, `redis:7.4.9-alpine`, `python:3.12.13-slim`, `nginx:1.30.1-alpine` — all immutable minor versions
- **`POSTGRES_PASSWORD` required** — Docker errors on empty password (`${POSTGRES_PASSWORD:?}`) instead of defaulting to `helix`
- **Docker healthchecks** — Switched from `python -c` to `curl -f`; added `depends_on` with health conditions for all data services
- **Resource limits** — Backend capped at 768M memory, frontend at 128M via `deploy.resources`
- **Frontend tab ARIA** — Navigation buttons use `role="tablist"`, `role="tab"`, `:aria-selected` attributes
- **CDN scripts deferred** — Chart.js and ECharts CDN scripts now load with `defer` to avoid render blocking
- **`rg → grep` in smoke-check.sh** — Replaced `ripgrep` with standard `grep` for portability
- **CI sleep → polling** — `sleep 15` replaced with 60-iteration polling loop (2s interval) for service readiness

### Fixed

- **Frontend version sync** — Footer pill `v3.5.1` → `v3.7.0` matching backend `HELIX_VERSION`
- **AI auth gate** — `_require_ai_auth()` extracts `X-Admin-Token` from request headers (no FastAPI DI dependency); optional `AI_REQUIRE_TOKEN` env var with per-IP lockout after 20 failed attempts (Redis-backed with in-memory fallback)
- **Pre-flight budget deduct** — Token reservation moved before provider call; accepts 1-2% overage for simplicity
- **Rate limiter on `/api/ai/budget`** — 30/minute limit applied
- **CI coverage floor** bumped from 60% → 65%
- **Non-root nginx** — `frontend/Dockerfile` adds `USER nginx` with `chown` on static assets
- **ClickHouse healthcheck** — Added `clickhouse-client --query="SELECT 1"` healthcheck to prevent rollover queries on unhealthy instance
- **ECharts lazy-load bug** — Replaced broken `import()` UMD import with `<script>` injection that properly sets `window.echarts`; exported `_renderForecastChartsImpl` and wired into Alpine component

## 3.6.0 (2026-05-26)

### Bugfixes

- **Blank page on deploy** — Alpine 3.14.9 CDN auto-starts via `queueMicrotask(() => Vt.start())` before deferred `<script type="module">` scripts execute, causing `ReferenceError: helixApp is not defined`. Switched from CDN `<script src="...cdn.min.js">` to ESM module import (`import Alpine from '.../module.esm.js'`) — the ESM build has no auto-start, Alpine is imported as a hoisted dependency, and `Alpine.start()` is called manually after all component registration.
- **Chart flicker** — ECharts instances stored in separate `_echarts` Map distinct from Chart.js `_charts` Map. `destroyCharts()` no longer wipes forecast charts during the 60s auto-refresh timer. `destroyForecastCharts()` added and called on `switchAsset`/`cycleTheme`/`loadChartRange`. `_setupResizeHandler()` resizes both chart types.
- **Overlapping 60s refresh** — `_loadingDashboard` guard prevents concurrent `loadDashboard()` calls. `loadTab()` uses `await` on all tab loaders.
- **cycleTheme() re-render** — `destroyForecastCharts()` followed by `renderForecastCharts()` when on the Forecast tab, preventing blank charts after theme toggle.
- **Duplicate route registration** — Removed second `app.include_router(settings_router, prefix="/api")` in `backend/routes/__init__.py`.

### API & Backend

- **Forecast API restored** — `ForecastRun` + `ForecastPoint` ORM models in `backend/database.py`. `GET /api/forecasts?asset=X` returns forecasts, points (with `peg`/`supply` aliases), and historical data. `GET /api/analytics/forecast-accuracy` computes accuracy against actuals. Both routers registered and rate-limited.
- **5 forecast endpoint tests** — `backend/tests/test_forecasts.py` covers empty DB, populated DB, and invalid asset scenarios (99 total tests).

### AI Cost Leaks

- **`_extract_report_date_via_llm`** — Gated on `ai_mode() != "ai_off"` and calls shared `_within_budget()` in `backend/services/osint.py`.
- **Sentiment budget** — `_within_sentiment_budget()` now delegates to `ai_router._within_budget()` — single Redis pool, shared key `helix:ai:daily_tokens:*`. Local budget tracking removed.
- **Pre-pay budget** — `enrich_with_ai()` estimates tokens (`max_tokens + len(prompt.split())`) and reserves via `INCRBY` before the provider call. All AI features gated by `AI_MODE` env var.

## 3.5.1 (2026-05-25)

### Security (Audit v1–v3 Remediation)

- **Fail-closed admin auth** — `backend/core/admin_auth.py` with `require_admin_token()` fails closed (503 if unset, 403 if invalid). Applied to all admin routes, settings, refresh, metrics, and governance endpoints.
- **Configurable CORS** — `CORS_ORIGINS` env var (comma-separated, default `*`) with whitespace trimming. Replaces hardcoded `allow_origins=["*"]`.
- **Content-Security-Policy header** — Set on all backend responses and nginx static assets (`frontend/nginx.conf`). Configurable via `CONTENT_SECURITY_POLICY` env var. Mitigates XSS token theft from sessionStorage.
- **Auth-protected GET /api/settings** — Read-only settings no longer public; frontend `loadSettings()` sends `X-Admin-Token`.
- **Auth-protected GET /api/governance** — Was accidentally public despite being in `admin.py`.
- **Auth-protected GET /metrics** — Prometheus metrics require admin token; nginx returns 404 at edge.
- **Input validation** — FinBERT route enforces `max_length=512`; compare `assets` validated at middleware layer; CSP on static frontend assets.
- **Alert dispatcher HTTP checking** — `_dispatch_webhook`, `_dispatch_discord`, `_dispatch_telegram` now call `raise_for_status()`; non-2xx responses logged.
- **Deploy script hardened** — No hardcoded IP (requires `HELIX_DEPLOY_REMOTE`); smoke URL configurable via `HELIX_SMOKE_URL`; admin-route auth verified in smoke checks.

### Bugfixes

- **Chart lifecycle** (`c.destroy is not a function`) — Unified `_disposeChart()` helper branching on `dispose` (ECharts) vs `destroy` (Chart.js).
- **Stale auto-refresh** — No longer fires `POST /api/refresh` without an admin token configured.
- **Resize handler** — Moved from `_renderForecastCanvas` to `init()` via `_setupResizeHandler()`, preventing duplicate listener registration.
- **Health tab layout** — Alert History and Data Quality wrapped in `insight-grid` for consistent spacing.
- **Intel tab nav link added** — Intel tab content existed but had no navigation button.

### API Contracts

- **Forecast point aliases** — `peg` ← `depeg_index`/`price`, `supply` ← `total_supply` mapped in `forecasts.py` so charts display correctly.
- **Anomaly events normalized** — `detect_anomalies()` emits `anomalies[]` list matching frontend expectation.
- **Forecast risk signals** — Loaded from `/api/events` filtered by `forecast_` event type prefix.
- **Data quality card** — Mapped to `{label, value}` rows (NLP, cached data, degraded sources).

### Infrastructure

- **Alembic settings migration** — `Setting` model now inherits `Base.metadata`; ad-hoc `create_all` removed; idempotent migration `f5f21ba3d585`.
- **Redis rate limiter** — Already wired via `RATE_LIMITER_STORAGE_URI` env var; documented in `.env.example`.
- **Smoke-check.sh** — Verifies `/api/settings` and `/api/governance` require auth without token.
- **.env.example** — Added `CORS_ORIGINS`, `CONTENT_SECURITY_POLICY`, `HELIX_DEPLOY_REMOTE`, `HELIX_SMOKE_URL`.

## 3.3.4 (2026-05-24)

### Fixed

- **Frontend version hardcoded** — `index.html` footer was showing `v3.2.0` instead of tracking the backend version. Now displays `v3.3.4` in sync with the API.

## 3.3.3 (2026-05-24)

### Fixed

- **Backend Docker startup on VPS** — root cause was a stale `docker-compose.override.yml` overriding the Dockerfile CMD with `--reload` and dropping `--app-dir`. Override file is now `.gitignore`d to prevent future conflicts. Added `docker-compose.override.yml.example` as a safe reference.
- **`docker-compose.override.yml` gitignored** — prevents local overrides from causing git conflicts or overriding the production CMD

## 3.3.2 (2026-05-24)

### Fixed

- **Backend container startup on VPS** — `CMD` in Dockerfile now uses `--app-dir /app/backend` to explicitly tell uvicorn where to find `main:app`, working around Docker/Python sys.path differences across environments. Backend was crashing with `Could not import module "main"` on VPS despite working locally.

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
