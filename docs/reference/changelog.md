# Changelog

## [Unreleased] — 2026-06-24

### CI & Maintenance
- **Fixed:** Chronic smoke job failure (3–4 weeks) — `POSTGRES_PASSWORD` is now
  injected in the CI environment before `docker compose up`; previous `touch .env`
  band-aid never satisfied the `:?` hard-required compose variable
- **Fixed:** Removed `xgboost`, `skl2onnx`, and `pandas` from `requirements.txt`
  (zero runtime imports); created `backend/requirements-ml.txt` for training-only deps
- **Fixed:** Trivy and pip-audit no longer fail on training ML deps in the production image
- **Fixed:** Relaxed `requests==2.34.2` exact pin to `requests>=2.32.0,<3`
- **Fixed:** Removed `master` branch from CI trigger (repo uses `main` only)
- **Added:** `backend/.trivyignore` for onnxruntime accepted-risk annotation
- **Added:** Playwright npm caching in smoke job (removes ~60–90s per run)
- **Removed:** Dead `.event-ticker` CSS and `@keyframes ticker` animation
  (HTML consumer removed in previous tickerItems cleanup session)
- **Fixed:** `train_depeg_model.py` docstring incorrectly referenced xgboost and GradientBoostingClassifier
- **Docs:** Added CI secrets table and fork contributor guidance to CONTRIBUTING.md
- **Docs:** Added CI setup note to README.md pointing to CONTRIBUTING.md

## 3.9.5 (2026-06-23)

### Added
- **Webhook Alert System (Sprint 5)** — `backend/services/webhook_dispatcher.py` with `build_alert_payload` (stable v1.0 schema), HMAC-SHA256 `X-Webhook-Signature-256` header, severity filtering (`webhook_min_severity`), simple 3-attempt backoff, timeout. Hooked into `signal_engine/history.py:_flush_events` (post-persist, best-effort non-crashing). Settings: `webhook_enabled`, `webhook_url`, `webhook_signing_secret`, `webhook_min_severity`, `webhook_timeout_seconds` (admin-gated via routes/settings + registry).
- **5-component scoring (Sprint 4)** — liquidity_depth 10%, velocity 15%, concentration 20%, depeg 35%, age 20% (sum=1.0). Continuous depeg interpolation. Crypto HHI 2000/4000/7000 + top3_dex_pool_share. 4-tier age. abs() for velocity (contracting contributes). Updated `docs/scoring-design.md`.
- **SMIDGE Score Card (Sprint 7)** — `backend/sources/bluechip.py`, `services/smidge.py` (S/D/E local + M/I/G via Bluechip), `frontend/js/composables/useSMIDGE.js` + ECharts radar. `GET /api/smidge`, Intel tab panel.
- **Frontend data fixes (Sprint 3 + 0)** — parallel 4-asset fetch, per-source cross-price rows, risk component progress bars, attestation startup refresh, freshness normalization (case-insensitive green/yellow/red), `formatSI`/`formatDate` on KPIs and charts, forecast empty states.

### Changed / Removed
- **Direct Telegram removed** — entire `helix_telegram/` package, `routes/telegram.py`, `tests/test_telegram.py` deleted. Removed telegram branches from `alerts.py`, `main.py` lifespan, routes includes, settings_registry keys (`alert_telegram_*`, `feature_telegram_bot`), admin allowlist, `config/alerts.json` (peg critical now dashboard+webhook+discord), `.env.example`, `requirements.txt`. `config/alerts.json` peg rules retain valid channels.
- **Sprint 6 deferred** — no Email/Resend subscribers or direct push channels. Webhook is the integration point for Zapier/Pabbly/etc. Future adapters will reuse payload.
- **Sprint 1 flags** — `ENABLE_NLP`, `ENABLE_ANOMALY_DETECTION` default true; `enable_predictive` bool coercion; CVaR window 288; per-feature cache TTL; depeg in circuit breaker.
- **Sprint 0 cosmetic** — freshness colors fixed (no more inverted red), supply abbr, chart dates, empty states verified.
- **Dependencies** — added `xgboost>=2.0`, `skl2onnx>=1.16`; removed `python-telegram-bot`.

### Partial / Future
- **Sprint 8 ONNX** — export script + feature vector (supply_velocity_1h) + deps present; training not executed (needs data); model fallback to heuristic if absent.
- **Sprint 9 ML** — anomaly CUSUM, adaptive z-score, per-asset contamination, correlation matrix + endpoint; 8D features / Redis rate limits / LLM web search deferred.
- **Direct notification channels** — Telegram/Email/Slack/Discord native deferred (use webhook + external automation for now).

### Tests
- Full suite: 354 passed, 0 failed (telegram-related pre-existing failures eliminated by removal; import main passes).
- Webhook tests, scoring, predictive pass.

## 3.9.4.1 (2026-06-23)

### Fixed

- **ruff lint errors (14)** — Fixed F823 (undefined loop variable), F541 (f-string without placeholders), and E712 (boolean comparison with `== True`/`== False`) across 7 files. Added missing `_day_start()` helper in backfill.py, removed stale import in bot.py, added missing `timedelta` import in brief.py.
- **Bandit security warnings (4)** — Defused XML parsing in osint.py (`defusedxml.ElementTree`); `# nosec` on dev-only 0.0.0.0 binding in main.py; `# nosec` on hardcoded table name SQL in admin.py; `usedforsecurity=False` on MD5 cache key hashes in cache.py.
- **Settings auto-reload** — `adminToken` `$watch` in `useGovernance.js init()` now triggers `loadSettings()` automatically when the admin token is saved, eliminating the need to manually reload the page.
- **Frontend runtime errors** — Fixed 8 production JS errors in Alpine + Chart.js + ECharts. `tickerItems` undefined: replaced `x-show="false"` with `x-if="false"` on event ticker to prevent Alpine expression evaluation. `toFixed` on undefined/null: added optional chaining (`?.`) and nullish coalescing (`??`) guards on `attSignal.age_days`, `supplyFeed.age_minutes`, `crossSource.avg_price`. Chart canvas reuse: added `Chart.getChart(id)?.destroy()` before `new Chart()` in all chart renderers. `_disposeAllCharts`/resize handler: guarded `this._echarts` and `destroyForecastCharts` with existence checks.

### Changed

- **Dependency** — Added `defusedxml>=0.7.1` to `requirements.txt` (was transitive via `py-serializable`; now an explicit runtime dependency for secure RSS XML parsing).

### Infrastructure

- **Version bumped** — 3.9.4 → 3.9.4.1

## 3.9.4 (2026-06-22)

### Added

- **OsintArticle join table** — New `OsintArticleAsset` model with FK to `osint_articles`, unique constraint on `(article_id, asset_symbol)`, cascade delete. Replaces `asset_symbols` comma-separated string column. Includes Alembic migration with data migration (splits strings into join rows) and column drop.

### Changed

- **Test suite passes 355/355** — Fixed admin auth brute-force lockout (`_FAILED_ATTEMPTS` dict never cleared between tests) causing false 429 responses. Added `_FAILED_ATTEMPTS.clear()` + `limiter.reset()` to the autouse `_reset_shared_globals` fixture. Updated stale rate-limit test values (coingecko 50→100 RPM, dexscreener 59→119 RPM) to match current settings registry.
- **AI endpoints require admin token** — `/api/ai/budget`, `/api/ai/usage`, `/api/ai/warnings` now gated by `_require_admin_token` (was public before).
- **Signal engine history refactored** — `_events_to_insert` module-global list replaced with local `pending_events: list[SignalEvent]` parameter threaded through all `_emit*` call sites, improving test isolation and predictability.
- **Postgres default** — `docker-compose.yml` defaults to Postgres + Alembic enabled; SQLite-only mode requires explicit `DATABASE_URL` override.
- **HTTP client hardening** — `follow_redirects=False` on all `httpx.Client` / `AsyncClient` instances in `sources/base.py` and `http_get_with_retry` helpers.

### Fixed
- **Admin token input always visible** — Move authentication block to top of settings tab outside settings-dependant gating, so token can be entered before settings load (chicken-and-egg fix).
- **FRED SERIES_MAP** — Restore SERIES_MAP definition broken in recent refactor (2ec6017)
- **CoinDesk RSS URL** — Update to canonical URL without trailing slash (ce62b94)
- **RSS User-Agent** — Add browser User-Agent to RSS fetch to bypass 403 on TheBlock (c4b542a)
- **Web3 RPC response** — Guard RPC response for missing result/error keys (9f7ab58)
- **CSP importmap hash** — Allow importmap SHA-256 hash in script-src; unsafe-inline NOT re-added (f5673ee)
- **Frontend port mapping** — Reconcile docker-compose.yml frontend port 8080:80 → 80:80

- **Admin auth lockout per-IP** — Fixed `_ip_key()` proxy CIDR logic: properly extracts real client IP from `X-Forwarded-For` when behind a trusted proxy, avoiding false lockout on shared proxy IPs.
- **Settings import file size** — Rejects uploads >1 MB with 413 status (was no limit).
- **`composite_scoring.py`** — Removed stale `source_ok` penalty that halved risk scores when source had errors.

### Infrastructure

- **CI hardening** — Added gitleaks secrets scan, Playwright frontend render check, always-on smoke job (not only on PR). Removed stale `docs/system_improvements.md` and `docs/system_improvements_summary.md`.

### Documentation

- **Scoring design** — New `docs/scoring-design.md` with asset-level and chain-level risk score formulas.
- **Version bumped** — 3.9.3.1 → 3.9.4

## 3.9.3 (2026-06-21)

### Added

- **Database optimizations** — Added indexes on frequently queried columns, implemented bulk operations, configured connection pooling, and added caching for frequently updated records
- **Rate limiting improvements** — Reduced DexScreener API calls from 3 endpoints to 1, limited chains from 6 to 2 major chains, increased rate limits to 120 RPM for DexScreener and 100 RPM for CoinGecko
- **Asset management pipeline** — Created `scripts/add_stablecoin.py` for automated asset addition with configuration validation
- **Enhanced monitoring system** — Created `scripts/monitor_rate_limits.py` with comprehensive monitoring and alerting capabilities
- **Health tab** — Added new health dashboard with source status, usage metrics, and freshness monitoring

### Changed

- **DexScreener implementation** — Optimized API calls and reduced chain coverage to stay within rate limits
- **Asset addition process** — Enhanced with validation and automated documentation updates
- **Documentation** — Updated guides and added comprehensive system improvements documentation

### Fixed

- **Rate limiting issues** — Resolved excessive API calls that were causing rate limit exceeded errors
- **Database performance** — Optimized queries and operations for better performance
- **Asset configuration validation** — Added comprehensive validation for new asset additions

### Infrastructure

- **Version bumped** — 3.9.2 → 3.9.3

## 3.9.2 (2026-06-04)

### Added

- **Settings Registry expansion** — 18 new settings added: `cors_origins`, `feature_nlp_sentiment`, `llm_extract_cache_ttl`, `openrouter_free_model`, `anomaly_std_floor`, `sentiment_max_articles_per_batch`, `alert_discord_webhook`, `alert_telegram_bot_token`, `alert_telegram_chat_id`, `alert_smtp_host/port/user/pass`, `allow_backfill`, `enable_redis_cache`, `enable_chainlink`, `enable_dynamic_chains`, `feature_multi_user`
- **Rate limit decorators** — 26 admin endpoints now rate-limited (30/min data quality, 30/min audit, 5-30/min import/export, 30/min telegram, 10/min login)
- **AI Configuration Guide** — New `docs/guides/ai-configuration.md` with comprehensive setup instructions

### Changed

- **Import scheme unified** — All `from backend.xxx` imports converted to `from xxx` across 33 files (app runs with `WORKDIR /app/backend`, PYTHONPATH includes `/app/backend`)
- **Diagnostics allowlist** — Environment variables in `/api/admin/diagnostics` filtered by explicit allowlist (`_DIAGNOSTICS_ALLOWLIST`) instead of blocklist, preventing accidental secret exposure
- **Config wiring** — `ai_mode()` falls back to DB `get_setting("ai_mode")` instead of env-only defaults; `REFRESH_INTERVAL_SECONDS` reads from settings DB; module-level secret globals converted to lazy-load functions
- **Chainlink stub** — Legacy `backend/sources/chainlink.py` now delegates to plugin registry via `get_source("chainlink")`
- **Dockerfile PYTHONPATH** — Changed from `PYTHONPATH=/app` to `PYTHONPATH=/app/backend:/app` to support the unified import scheme
- **Auth lockout test** — Updated to account for rate limit decorators (429 accepted alongside 403)
- **`.env.example`** — Expanded with 18 new setting entries for alert dispatch, feature flags, and provider keys

### Fixed

- **Diagnostics env var leak** — Blocklist filter replaced with explicit allowlist to prevent secret exposure
- **Test regression in backfill endpoint** — Restored `POST /api/admin/backfill` endpoint in `admin.py` that was accidentally dropped during route cleanup
- **Scheduler status** — Removed dangling import of non-existent `backend/scheduler` module in `admin.py` health check

### Infrastructure

- **Version bumped** — 3.9.1 → 3.9.2

## 3.9.1 (2026-06-03)

### Added

- **Per-feature AI model overrides** — New settings allow specifying different AI models for different features:
  - `ai_model_risk_explain` — Model for risk explanation feature
  - `ai_model_market_narrative` — Model for market narrative feature  
  - `ai_model_insight_summary` — Model for insight summary feature
  - `ai_model_predictive` — Model for predictive analytics feature
- **AI Model Discovery API** — New endpoints for discovering available models from AI providers:
  - `GET /api/admin/ai/providers` — List all available AI providers
  - `GET /api/admin/ai/providers/{provider_id}/models` — List models for a specific provider
- **Granular per-feature settings** — Detailed configuration options for AI features:
  - Predictive analytics: `predictive_enable_depeg`, `predictive_enable_regime`, `predictive_depeg_horizons`, `predictive_confidence_threshold`
  - AI summaries: `ai_summary_max_length`, `ai_summary_detail_level`
  - AI explanations: `ai_explain_max_factors`, `ai_explain_confidence_min`
  - AI insights: `ai_insights_max_assets`, `ai_insights_correlation_min`
  - OSINT features: `osint_enable_sentiment`, `osint_enable_entity_extraction`
- **Dynamic model selection in Settings UI** — Dropdown menus now show available models from configured AI providers
- **AI Configuration Guide** — New documentation at `docs/guides/ai-configuration.md` with comprehensive setup instructions

### Changed

- **Enhanced Settings UI** — Model selection dropdowns now dynamically fetch available models from AI providers
- **Improved AI Router** — Backend routing logic updated to support per-feature model overrides
- **Settings Registry** — Added 18 new settings for AI model management and feature configuration

### Fixed

- **Model Selection UX** — Settings UI now properly displays available models for each provider
- **Feature Configuration** — Per-feature settings are now properly applied to their respective AI functions

### Added

- **Test pollution fix** — Single comprehensive `autouse=True` fixture `_reset_shared_globals` in `backend/tests/conftest.py` resets ALL cross-module mutable globals (`r.*`, `cache_mod.*`, `budget_mod.*`, `_PROVIDER_*`, `_SOURCE_RATE_LIMITS`) across `services.ai_router`, `services.components.ai.cache`, `services.components.ai.budget`, and `services.source_usage`. Removed per-file `_reset_globals` / `_reset_cache_globals` fixtures from `test_phase2_integration.py` and `test_ai_cache.py` to prevent overlapping subsets causing state leaks. 107/107 tests pass when core test files run together in a single process.

- **AI Market Narrative cache TTL setting** — New `ai_cache_ttl_market_narrative` setting controls cache TTL for Market Narrative AI responses (default 3000 seconds / 50 minutes). Configurable via Settings UI (`/settings`), env var `AI_CACHE_TTL_MARKET_NARRATIVE`, or playbook preset. Enables tuning cache freshness vs. AI cost tradeoff without code changes.

- **Runtime configurable AI feature TTLs** — Per-feature cache TTL overrides now read from settings DB via `_get_feature_cache_ttl()` in `backend/services/components/ai/cache.py`, allowing `ai_cache_ttl_market_narrative` to dynamically override the hardcoded `3000` value. Other features retain hardcoded defaults unless explicitly added.

### Changed

- **Test suite reliability** — Combined run of `test_ai_cache.py`, `test_ai_router.py`, `test_phase2_integration.py` now passes 107/107 tests consistently without fixture pollution between files.

- **Market Narrative refresh control** — No automatic background refresh; user manually triggers via `/api/ai/narrative` endpoint or refresh button. TTL setting now controls how long cached responses are reused before recomputing.

### Fixed

- **Production `/api/osint/attestation` blocking** — Removed synchronous `refresh_attestation_reports()` call from `get_attestation_status()` endpoint. Endpoint now returns cached/stale data immediately without blocking on HTTP fetches to Tether/Circle/Paxos (up to 90+ seconds worst-case). Cache is kept fresh via scheduled job and can be manually refreshed if needed. Addresses production latency spike on uncached endpoint calls.

### Infrastructure

- **Version bumped** — 3.9.0 → 3.9.1

## 3.9.0 (2026-06-01)

### Added

- **Phase A — Technical Debt Cleanup**:
  - `services/dashboard.py` extraction — moved all dashboard computation logic out of `routes/dashboard.py` (now 32 lines vs 384 lines before)
  - `helix_telegram/commands/` package with 4 new bot commands:
    - `/signal <asset>` — Returns current risk score breakdown for a specific asset
    - `/brief` — Returns market brief (top signals, recent alerts, sentiment summary)
    - `/price <asset>` — Returns current price from multiple sources with peg deviation
    - `/refer` — Returns system health and reference links
  - `helix_telegram/ratelimit.py` — In-memory rate limiting middleware with configurable limits
  - `helix_telegram/review.py` — Review queue system for human-in-the-loop moderation of alerts
  - 4 new Telegram API endpoints for review queue management at `/api/telegram/review/*`
  - Anti-abuse rate limiting middleware for all bot commands

- **Phase B — Settings Frontend Completion**:
  - Playbook preset buttons (Max Free, Balanced, Quality) with one-click apply
  - Settings audit log frontend tab with real-time display and filtering
  - Per-feature AI budget sliders for granular cost control
  - Provider priority drag-and-drop UI for visual configuration
  - "Apply Safe Defaults" button with confirmation modal
  - Setting dependency indicators (grayed out when dependency off, rate limit badges, restart badges)
  - Keyboard shortcuts and enhanced UI polish (Esc to close modals, toast notifications)
  - Enhanced settings search and filtering capabilities

### Changelog

- **Version bumped** — 3.8.3 → 3.9.0
- **README refreshed** — Updated with new features and functionality descriptions

## 3.9.1 (2026-06-02)

### Added

- **Phase 3 — Alert Config Migration** — 11 alert settings moved from env vars to Settings UI:
  - `alert_webhook_url`, `alert_discord_webhook`, `alert_telegram_bot_token`, `alert_telegram_chat_id` — dispatch channel credentials
  - `alert_smtp_host`, `alert_smtp_port`, `alert_smtp_user`, `alert_smtp_pass`, `alert_email_to`, `alert_email_from` — SMTP dispatch
  - `alert_slack_webhook` — Slack dispatch channel
  - All dispatch functions in `services/alerts.py` read from DB via `get_setting()`, thread `db` through dispatch chain
  - Removed `import os` from `services/alerts.py`

- **Phase 4 — Adjustable Params Migration** — 5 runtime parameters moved from env vars to Settings UI:
  - `cors_origins` — CORS origins (requires restart)
  - `sentiment_max_articles_per_batch` — batch size for sentiment analysis
  - `attestation_cache_ttl_seconds` — attestation report freshness cache TTL
  - `llm_extract_cache_ttl` — LLM extraction cache TTL
  - `anomaly_std_floor` — z-score standard deviation floor

### Changed

- **Configuration UX** — All user-facing settings now manageable from Settings UI instead of `.env`. `.env.example` reduced to infrastructure-only vars (admin token, log level, database URL).
- **README refreshed** — V3 highlight weights corrected to match code (depeg 35%, concentration 25%, velocity 20%, age penalty 20%). FinBERT reference updated to "LLM-powered sentiment scoring". TimesFM claim removed. Env var list condensed to infrastructure-only.
- **ClickHouse removed** — Fully removed from compose, codebase, tests, and docs (mop-up from prior session).

## 3.8.3 (2026-06-01)

### Fixed

- **Secret leak in settings API** — `get_all_settings()` now masks secret-type values via `mask_secret()` instead of `bool(typed)`, preventing plaintext secret exposure in API responses.
- **AI env bypass** — Added `_resolve_api_key()` to AI router — checks settings DB first via `get_setting()`, falls back to `os.environ`. Eliminates the settings-vs-env dual path that could bypass stored API keys.
- **Telegram bot wiring** — `create_bot_application()` and `add_digest_scheduler()` wired into FastAPI lifespan in `main.py`, gated by `feature_telegram_bot` setting. Bot polling runs as background asyncio task with clean shutdown.
- **Orphan removal** — `backend/mcp_server.py` deleted (was a no-op with dead `_db_session()` and zero consumers).
- **Offset-naive datetime** — Fixed `datetime.utcnow()` → `datetime.now(timezone.utc)` in `signal_engine/components/composite_scoring.py` to prevent `TypeError` when subtracting timezone-aware timestamps.
- **conftest.py path resolution** — Fixed repo root detection from `backend/tests/conftest.py` — `.parent.parent.parent` instead of `.parent.parent` resolves to the correct repo root.

### Changelog

- **Version bumped** — 3.8.2.1 → 3.8.3
- **README refreshed** — Removed stale `backend/mcp_server.py` entry; updated test count.

## 3.8.2.1 (2026-06-01)

### Added

- **Telegram bot integration** — New Telegram bot for alert notifications and user management. Includes `backend/helix_telegram/` module, `backend/routes/telegram.py`, `backend/database.py` schema changes, and Alembic migration for `telegram_users` table.
- **Data quality monitoring** — New `backend/data_quality/` module with routes at `backend/routes/data_quality.py`. Tracks cross-source discrepancies, data freshness, and source reliability.
- **Settings audit & import/export** — `backend/routes/settings_audit.py`, `backend/routes/settings_import_export.py`, `backend/services/settings_audit.py`, `backend/services/settings_import_export.py` for tracking setting changes and bulk configuration management.
- **User service & permissions** — `backend/services/user_service.py`, `backend/services/permissions.py`, `backend/routes/users.py` for user management and role-based access control.
- **Settings metadata & dynamic AI router chains** — Rich metadata (groups, labels, descriptions) on all settings; dynamic AI provider chain configuration (Phase 2 Tasks 1+2).
- **Multi-layer AI cache** — Enhanced exact-match cache with per-feature TTL (`_FEATURE_CACHE_TTL`), `OrderedDict`-based LRU eviction at `_MAX_CACHE_ENTRIES` (default 1000). Semantic cache layer with character trigram Jaccard similarity (`_trigram_similarity`), off by default (`_SEMANTIC_CACHE_ENABLED`), configurable threshold, separate LRU. Cache observability via `get_cache_stats()` with hits, misses, hit rate, tokens_saved, evictions, and semantic stats.
- **Rate limiting & AI cost control** — Per-endpoint rate limiting, AI daily token budget tracking, token usage deduplication, and cost dashboards (Phase 2 Tasks 2.4-2.5).
- **Warning engine** — `backend/services/warning_engine.py` for configurable alerting rules with 9 rule types, persistence tracking, and multi-channel dispatch (Phase 2 Task 2.6).
- **Admin audit features** — Audit trail for admin actions, source usage tracking, rate limit monitoring, and CI pipeline hardening (Phase 2 Tasks 2.7-2.8).
- **Phase 6 — Signal Engine componentization** — `signal_engine/scoring.py` refactored into focused component modules at `signal_engine/components/`: `peg_analysis.py` (peg stability), `concentration.py` (HHI concentration), `supply_momentum.py` (supply velocity), `data_confidence.py` (data quality), `composite_scoring.py` (overall risk). Each module has single responsibility, independent testability, and module-level documentation.
- **Phase 6 — AI service modularization** — AI router components reorganized into `services/components/ai/`: `cache.py` (cache management), `budget.py` (token budget tracking). Clearer interfaces and improved maintainability.
- **Documentation** — New `docs/phase6_code_quality.md` documenting architecture improvements; component README files for modularized modules; updated `docs/api.md` with new endpoints.
- **Alembic migrations** — Added migrations for `telegram_users`, `source_usage`, `asset_freshness`, and `cross_source_discrepancy` tables.

### Changed

- **Version bumped** — 3.8.x → 3.8.2.1
- **Updated README** — Added links to new documentation, Phase 6 code quality docs.
- **Updated .gitignore** — Excluded temporary test files, logs, and development artifacts.

### Fixed

- **Ruff import cleanup** — Removed unused imports in `migrate_sqlite_to_postgres.py` and `train_depeg_model.py`.

## 3.8.1.2 (2026-05-28)

### Fixed

- **Frontend nginx container crash in CI** — Frontend nginx ran as `USER nginx` with `cap_drop: ALL` but couldn't write its PID file to `/run` (owned by root). Added `/run` and `/var/cache/nginx` directories to the `chown nginx:nginx` line in `frontend/Dockerfile`.
- **Smoke-check SIGPIPE flakiness** — `grep -Fq` with `pipefail` caused SIGPIPE (exit 141) when grep closed its stdin early. Changed to `grep -F >/dev/null` to consume full input.
- **CI health check loop silent timeout** — The smoke job's 60-iteration wait loop completed with exit 0 even when all health checks failed, hiding frontend failures. Added explicit `curl http://localhost/` guard with `exit 1` on failure.

## 3.8.1.1 (2026-05-28)

### Fixed

- **CI teardown timeout** — RPC Web3 listener and FRED poller tasks were fire-and-forget infinite loops never cancelled during lifespan shutdown, causing `TestClient` teardown to hang until pytest-timeout killed the process at 120s. Fixed by returning/capturing task handles and cancelling them in the `finally` block with `asyncio.gather(..., return_exceptions=True)`. Added `HELIX_DISABLE_BACKGROUND_TASKS` env var to skip both during tests (follows existing `HELIX_SKIP_STARTUP_REFRESH` pattern).
- **Dockerfile curl version pin** — Replaced brittle `curl=8.14.1-2+deb13u3` exact version pin with `# hadolint ignore=DL3008` + unversioned `curl` install, preventing build failures when the base image apt index updates.
- **`.process/` in `.gitignore`** — Added `.process/` entry to prevent accidental commit of internal session notes.
- **CI smoke job profile + env vars** — Smoke job now runs `docker compose --profile data` (starts postgres/redis required by `depends_on`) with inline `POSTGRES_PASSWORD` env vars to prevent `${POSTGRES_PASSWORD:?}` interpolation failure.
- **CI smoke BASE_URL fix** — Smoke check now passes `BASE_URL=http://localhost` (port 80) matching the production compose mapping, instead of defaulting to dev port 3000.
- **Trivy action tag** — Fixed `aquasecurity/trivy-action@0.30.0` → `@v0.36.0` (0.30.0 tag never existed, was causing action resolution failure).
- **CI smoke `.env` file** — Added `touch .env || true` before compose to satisfy `env_file: .env` directive on fresh checkout (no `.env` in CI runner).
- **Trivy `ignore-unfixed`** — Added `ignore-unfixed: true` to skip base-image OS vulns with no available fix (13 HIGH/CRITICAL in Debian Trixie `python:3.12.13-slim`).
- **SQLite path 3→4 slashes** — Fixed `sqlite:///data/helix.db` → `sqlite:////data/helix.db` in `docker-compose.yml` so the database path resolves as absolute `/data/helix.db` instead of CWD-relative `/app/backend/data/helix.db` on the read-only filesystem. This was the primary cause of backend container crashes in CI.
- **Timezone-aware datetime guard** — Added `tzinfo` check in `health.py` for `AssetFreshness.last_successful_fetch` timestamps (SQLite returns naive datetimes), matching the existing guard for `SourceStatus`. Prevents `TypeError` on `/api/health` endpoint.
- **Override volume mount path** — Fixed `docker-compose.override.yml` to mount `./backend:/app/backend` instead of `./backend:/app`, matching the Dockerfile's `WORKDIR /app/backend`.

## 3.8.1 (2026-05-27)

### Added

- **Per-asset freshness tracking** — New `AssetFreshness` table records each asset's last successful fetch timestamp. Upserted after each successful refresh. Exposed via `/api/health` as `asset_freshness` map + `worst_asset_age_hours`.
- **Cross-source discrepancy persistence** — `cross_source_discrepancy` JSON column added to `AssetTrendSnapshot`, populated from risk_kwargs during trend writes.
- **Cross-asset rotation card** — New frontend card in Overview tab showing pairwise supply correlations and dominance shifts from `/api/analytics/rotation`.
- **Composite indexes** — Added `(asset_symbol, timestamp)` and `(asset_symbol, chain_key, timestamp)` indexes on trend snapshot tables for faster range queries.

### Changed

- **UI layout** — Stress Leaderboard moved above AI cards for faster glance access to chain-level supply velocity.
- **Empty state messages** — Made empty states actionable (e.g. "Needs 7 days of history on multiple assets").

### Fixed

- **Frontend rotation URL** — Fixed route mismatch: frontend now calls `/api/analytics/rotation` instead of the non-existent `/api/analytics/cross-asset-rotation`.

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
- **CI hadolint + Trivy** — Hadolint Dockerfile linting and Trivy vulnerability scan (HIGH/CRITICAL, exit-code 1, ignore-unfixed) added to CI pipeline
- **CI SSH deploy job** — Automated deploy on `v*` tag push via SSH + docker-compose
- **`.dockerignore`** — `backend/.dockerignore` excludes venv, pyc, coverage, egg-info, pytest cache, git

### Changed

- **Budget tracking refactored** — `_deduct_tokens()` replaces `_within_budget()`: deducts actual tokens returned (not estimated pre-pay), supports Redis and local modes uniformly
- **Provider chain reordered** — OpenRouter free → Ollama Cloud → Groq in `ai_lite`; free → fallback → primary → Groq in `ai_full` priority mode
- **`.env.example`** — AI section reorganized with OpenRouter first, `AI_CACHE_TTL_SECONDS` default bumped from 1800→3600
- **Docker images pinned** — `timescaledb:2.26.4-pg16`, `redis:7.4.9-alpine`, `python:3.12.13-slim`, `nginx:1.30.1-alpine` — all immutable minor versions
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
