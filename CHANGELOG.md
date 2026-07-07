# Helix Signal Changelog

## v4.0.1 (pending)

### Fixed
- **`SESSION_SIGNING_KEY` loud failure** — Startup log ERROR warning if key is blank + improved 503 detail message includes fix instruction. `docs/DEPLOYMENT.md` and `README.md` deploy checklists now explicitly flag this as REQUIRED before first deploy. *(GLM-01)*
- **Admin token storage split** — Alerts, Tags, and AdminOps composables now read admin token from `$store.ui.adminHeaders()` (single source of truth in `sessionStorage`) instead of their own `localStorage` reads. Login in Settings now correctly authorizes all admin-gated panels. *(GLM-02)*
- **AI warnings banner auth-gated** — `_loadWarnings()` now skips fetch when no admin token is present (avoids recurring 401 in network tab every 60s) and passes `X-Admin-Token` header when logged in, so warnings actually populate for admins. *(GLM-03)*
- **CI artifact force-tracking** — Heuristic `.onnx` stubs and `data/depeg_events.json` force-tracked via `.gitignore` negations. `onnx>=1.16.0` added to `requirements-dev.txt`. Optional model-regeneration step added to CI workflow. The 4 previously-failing CI tests (`test_dews.py` + `test_ml_models.py`) now pass deterministically. *(GH-CI)*
- **`TRUSTED_PROXY_CIDR` deploy config** — Startup WARNING log when unset. Default `10.0.0.0/8` in `.env.example`. Documented in README config, `docs/DEPLOYMENT.md`, and `SECURITY.md`. *(GLM-04)*
- **CORS origins loaded in lifespan** — CORS middleware stays at module level with env fallback (safe before `init_db`). DB setting (`cors_origins`) loaded into `app.state.cors_origins` after DB init, ready for future live-refresh on Settings update. *(GLM-05 — Option A)*
- **`/api/auth/me` hardcoded fallback removed** — Missing User record now returns 404 with `{"error": "user_record_not_found"}` instead of faking admin credentials. *(GLM-06)*
- **`loop` variable shadow in lifespan** — Removed redundant `asyncio.get_running_loop()` call (reused existing `loop` variable). *(GLM-22)*

## v4.0.0 (2026-07-05)

### Added
- **Alerts inbox UI** — New "Alerts" tab showing fired `SignalEvent` rows with asset/severity filters, plus the active alert rule list. Backend: `GET /api/alerts` (admin-gated, supports `?asset=`, `?severity=`, `?limit=`). Composable: `frontend/js/composables/useAlerts.js`. *(Phase 2.1)*
- **Address tagging manager UI** — Tags sub-panel in the Forensics tab: search-by-address lookup, create/delete tags (admin), CSV export. Wraps the existing `/api/v1/tags` CRUD API. Composable: `frontend/js/composables/useTags.js`. *(Phase 2.2)*
- **Fundamentals panel UI** — Yield / Collateral / Reserve intelligence cards in the Market tab, driven by the active asset. Composable: `frontend/js/composables/useFundamentals.js`. *(Phase 2.3)*
- **Analytics explorer UI** — New "Analytics" tab with regime detection (state/duration/transitions), change-point detection list, and cross-asset correlation matrix heatmap. Composable: `frontend/js/composables/useAnalytics.js`. *(Phase 2.4)*
- **Trends deep-dive + export** — Deep-dive modal on the Signal tab with chain breakdown (`/api/trends/chains`) + CSV export button (`/api/trends/export`). Composable: `frontend/js/composables/useTrendsDeepDive.js`. *(Phase 2.5)*
- **Admin operations drawer** — Slide-out drawer in the System tab with scheduler status (live from `/admin/diagnostics`), synthetic backfill trigger, diagnostics JSON download, and events CSV export. Composable: `frontend/js/composables/useAdminOps.js`. *(Phase 2.6)*
- **Settings registry audit script** — Reusable `backend/scripts/audit_settings.py` to cross-reference registry keys against codebase usage. *(Phase 1.6)*
- **AI facade** — Public `services/components/ai/facade.py` re-exporting `ollama_cloud`, `within_budget`, `get_budget_status` (no underscore). Updated 6 call sites to import from the facade instead of private `ai_router` symbols. Backward-compat aliases retained. Documented in `docs/api.md`. *(Phase 1.8)*
- **`refresh_chain_data` integration tests** — Added `test_refresh_chain_data.py` with 2 tests: no-enabled-assets early-return path + success path with stubbed async source registry. Covers the previously untested core async refresh flow. *(Phase 1.10)*

### Changed
- **Settings tab lazy-mounted via `<template x-if>`** — Settings DOM subtree (~870 lines) now mounts only when the Settings tab is active and unmounts on tab switch. Reduces initial DOM size and prevents hidden watchers/computeds from running. `useGovernance` state persists across mount/unmount cycles. *(Phase 3.0)*
- **Browser back/forward support** — Added `popstate` listener to sync tab state from URL hash when browser navigation buttons are used. Tab routing continues to use `location.hash` (no `@alpinejs/history` dependency — custom History API approach chosen after ESM compat review). *(Phase 3.1)*
- **Yield/Collateral/Reserve schemas completed** — `*Out` pydantic models in `routes/yield_intelligence.py` now expose all DB columns (was missing: `apy_7d_avg`, `apy_7d_delta`, `yield_sustainability`, `funding_rate_*`, `insurance_fund_*`, `staking_ratio`, `lending_utilization_pct`, `collateral_assets`, `liquidation_threshold`, `liquidation_queue_usd`, `debt_ceiling_utilization_pct`, `largest_vault_usd`, `collateral_health_score`, `reserve_composition`, `attestation_url`, `attestation_source`, `attestation_lag_days`, `genius_act_compliant`, `mica_status`). Removed stale fields (`total_supply`, `total_collateral_usd`, `total_debt_usd`, `recovery_mode`) that did not exist on the DB models. *(Phase 2.3)*
- **`/sources/{name}/config` now returns real metadata** — Class, module, health-check capability, and instance load state instead of empty `{"name": name}`. *(Phase 1.1)*

### Fixed
- **Chart-dispose-on-unmount** — Added centralized `disposeAllChartInstances()` and `setupVisibilityDispose()` helpers in `charts.js`. Charts are now disposed on tab-leave and when the page becomes hidden (`visibilitychange`), preventing memory leaks from accumulated ECharts instances. *(Phase 3.3)*
- **`sources/moralis.py` — Missing `import time`** — Added `import time` to resolve `NameError` at runtime when retry logic fires. *(Phase 1.3)*
- **`routes/admin.py` — Scheduler health check placeholder** — Replaced `pass` with live `app.state.scheduler.running` read, threaded `request.app` through `_build_diagnostics`/`_get_health`. Falls back to `False` on `AttributeError`. *(Phase 1.4)*
- **Ruff lint fixes** — Ran `ruff check --fix backend/` (1 error auto-fixed). Ruff already runs in CI pipeline (ci.yml:42). *(Phase 1.5)*
- **`services/rss_feed.py` — Broken import** — `classify_article_structured` imported from nonexistent `services.components.ai.providers._ollama_cloud` (latent crash). Fixed to use facade with correct signature; extracted `_default_classification()` helper. *(Phase 1.8)*

### Removed
- **Stub CRUD endpoints in `routes/alerts.py`** — Removed 5 placeholder routes (list/create/get/put/delete). Only `/alerts/config` retained. *(Phase 1.1)*
- **Stub CRUD endpoints in `routes/reports.py`** — Removed 5 placeholder routes (list/create/get/put/delete). Only `/reports/summary` retained. *(Phase 1.1)*
- **Dead endpoint `routes/narrative.py`** — Removed `/api/v1/assets/{symbol}/narrative` (no UI consumer, replaced by `/api/ai/narrative`). *(Phase 1.2)*
- **Dead endpoint `routes/chain_detail.py`** — Removed `/api/chains/{chain_key}` (no UI consumer; service module retained for Phase 2 re-add). *(Phase 1.2)*
- **Dead test `TestNarrative`** — Removed 2 tests for the deleted narrative endpoint. *(Phase 1.2)*
- **Dormant OSINT settings** — `osint_enable_sentiment`, `osint_enable_entity_extraction`, `osint_min_sentiment_score` removed from `settings_registry.py` (never read; OSINT uses `feature_nlp_sentiment`). Removed stale entries from `docs/guides/ai-configuration.md`. *(Phase 1.6)*
- **Duplicate SMTP settings** — `smtp_host`, `smtp_port`, `smtp_user` removed from `settings_registry.py` (duplicates of `alert_smtp_*` which is the namespace `services/alerts.py` actually reads). *(Phase 1.6)*
- **`backend/helix.db.bak` untracked** — Removed from git tracking via `git rm --cached` (635 KB binary artifact). Strengthened `.gitignore` to cover `*.db.bak`, `backend/test.db`, `backend/test_persistent.db`, `backend/tests/*.db`. *(Phase 1.7)*

### Security
- **CORS default hardened** — `cors_origins` registry default changed from `"*"` to `http://localhost:3000,http://localhost`. Production deployments must set explicit origins. Warning for `"*"` already in place (`main.py:182`). *(Phase 3.4)*
- **Webhook auth returns proper HTTP status codes** — `external_intel_webhook.py` now returns 401 (invalid signature/secret), 400 (invalid JSON), 503 (disabled) instead of 200 with `{status:"error"}` body. *(Phase 3.4)*
- **Webhook dispatch moved to background thread** — `signal_engine/history.py:_flush_events` now dispatches webhooks via `threading.Thread(daemon=True)` instead of blocking the history refresh flow synchronously. *(Phase 3.4)*

### Chores
- **Clustering test assertions strengthened** — `test_clustering.py` "with_data" tests now assert non-empty results against seeded blacklist events (was `isinstance(result, list)` — passed on empty). Orchestrator test asserts ≥1 clustered address. *(Phase 1.10)*

### Code Quality — Sprint 9
- **`build_dashboard_response` decomposed** — 274→31 lines orchestration with 6 sub-functions (`_aggregate_chain_data`, `_compute_signals`, `_compute_freshness`, `_build_sources_payload`, etc.) in `services/dashboard.py`
- **`osint.py` split** — 701→167 lines thin orchestrator; `attestation.py` (385 lines) + `rss_feed.py` (177 lines) extracted with backward-compatible re-exports
- **Scheduler module** — 11 job functions moved from `main.py` (409→190 lines) to new `services/scheduler.py` with `register_scheduler_jobs()` helper
- **SA 2.0 migration** — All 66 `db.query()` calls across 25 files in `services/` and `data_quality/` converted to `select()` + `execute()` style (27 filter/where, 4 conditional-query builders, 6 `func.count`, 4 `delete()` conversions)
- **433 tests passing** — 9 new DeFiLlama mock tests (`test_defillama_mocked.py`), 6 new signal engine tests (`test_signal_engine.py`)
- **Frontend a11y** — `@media (prefers-reduced-motion: reduce)`, `:focus-visible` outlines, `aria-label` on icon-only buttons, `role="dialog"`/`aria-modal` on all modals, global toast/modal composables in `stores/ui.js`

### Sprint 8 — Frontend Forensics
- **Forensics tab** — New 6th tab (Signal, Market, Intel, Forensics, System, Settings) with KPI cards (blacklist events, active investigations, threat level), events table, and investigate form
- **Stablecoin taxonomy** — `frontend/js/taxonomy.js` with 24-coin definitions across 4 types (Fiat, Crypto, Yield, Algo) plus `getTypeBadge()` helper
- **Type badge icons** — 6 new SVG icons (shield, search-addr, fingerprint, and 4 type badge icons) in index.html sprite
- **On-chain composable** — `useOnchain.js` with wallet/contract/transaction lookup, token metadata, and risk signals from Alchemy/Moralis/GraphQL sources
- **Market tab badges** — Token cards show type badges (blue/purple/green/orange) and narrative card row
- **CSS additions** — Badge color classes, forensic table styling, investigate panel layout, icon sizing
- Rollback anchor: `HEAD`

### Sprint 7 — API Routes & Testing
- **4 new API routes** — `POST /api/v1/investigate` (investigation pipeline), `GET /api/v1/assets/{symbol}/yield` (protocol yield analysis), `GET /api/v1/blacklist/events` (blacklist event query, admin token required), `GET /api/v1/assets/{symbol}/narrative` (market narrative with 30-min Redis cache)
- **401 passing tests** — 13 new Sprint 7 tests for investigation engine, blacklist, yield intelligence, narrative; SAWarning fix in investigation_engine.py (Coercing Subquery → explicit `select()`)
- **Router registration** — All 4 routes registered in `routes/__init__.py` under `/api/v1` prefix with Pydantic response models

### Sprint 6 — DEWS & On-Chain Intelligence
- **DEWS (Distributed Early Warning System)** — `backend/services/dews.py` with multi-source anomaly scoring, circuit breaker chain, and alert dispatch
- **On-chain sources** — Alchemy RPC (`sources/alchemy_rpc.py`), Moralis (`sources/moralis.py`), Flipside (`sources/flipside.py`), The Graph (`sources/thegraph.py`), Chainlink Oracle (`sources/chainlink_oracle.py`), on-chain tokens (`sources/onchain_tokens.py`)
- **Address clustering** — `backend/chain/intelligence/address_clustering.py` — heuristic cluster detection from on-chain tx patterns
- **Bridge hop tracker** — `backend/chain/intelligence/bridge_hop_tracker.py` — CCTP/Stargate/Across/LayerZero/Synapse/Tornado Cash/Railgun routing
- **Peel chain detector** — `backend/chain/intelligence/peel_chain_detector.py` — fund movement tracing through intermediate addresses

### Sprint 5 — ONNX ML Models & Anomaly Service
- **3 ONNX models** — `depeg_events.py` (depeg probability scoring), `funding_regime.py` (perpetual futures regime detection), `yield_sustainability_model.py` (yield protocol health) — built via `onnx.helper` opset 9
- **Build script** — `scripts/build_v4_models.py` for manual ONNX graph construction (no skl2onnx dependency)
- **Anomaly service** — `backend/services/anomaly.py` with ONNX inference pipeline, heuristic fallback rules, type-specific scoring (Fiat/Crypto/Yield/Delta)
- **Walk-forward validation** — `backend/services/walk_forward.py` for time-series-aware model evaluation

### Sprint 4 — Evaluators, Rules & OSINT Expansion
- **9 evaluators** — Full evaluator suite for V4 components (reserve, collateral, yield, funding, concentration, velocity, liquidity, attestation, governance)
- **Rule engine** — Type-specific scoring rules: Fiat (price_dev + coverage + attest_lag + reg_flag), Crypto (price_dev + coll_ratio + liq_queue + debt_ceil), Delta (price_dev + funding + insurance + perp_oi)
- **OSINT expansion** — Additional RSS sources + LLM provider integration for enhanced narrative generation
- **External intel webhook** — Signed webhook receiver for third-party intelligence feeds

### Sprint 3 — V4 Scoring Engine
- **4 component scorers** — `ReserveScorer`, `CollateralScorer`, `YieldScorer`, `FundingScorer` with type-dispatched weight matrices
- **V4 dispatch** — `signal_engine/core.py` updated with V4 weight matrices and band consolidation (Healthy, Normal/Caution, Warning, Distress, Critical)
- **Reserve scraper** — Automated reserve report fetching from issuer websites (USDT, USDC, DAI, PYUSD)

### Sprint 2 — Data Source Plugins
- **Ethena plugin** — Staking APY, insurance fund, TVL, funding rate data from Ethena protocol
- **Coinglass plugin** — Open interest, liquidations, and funding rate aggregation from Coinglass API
- **Sky (MakerDAO) plugin** — DAI savings rate, collateralization ratio, debt ceiling updates
- **Liquity plugin** — LUSD collateral ratio, redemption volume, stability pool metrics
- **Aave plugin** — GHO supply/borrow rates, aToken data, liquidity pool status
- **Ondo plugin** — USDY/Ondo yield data, TVL, and protocol metrics

### Sprint 1 — Foundation: Taxonomy, ORM, Settings
- **24-coin taxonomy** — `STABLECOIN_TAXONOMY` with 4 types: Fiat-backed (USDT, USDC, PYUSD, FDUSD, USDP, TUSD, USDD, FRAX, GUSD, BUSD, USDe), Crypto-backed (DAI, LUSD, GHO, USDM, crvUSD, sUSD), Yield-bearing (sDAI, USDS, sUSDe, USDY), Algorithmic (USDe, crvUSD, Ethena)
- **6 new ORM models** — `FiatReserve`, `Collateral`, `YieldBearing`, `FundingRate`, `WhaleActivity`, `BlacklistEvent`
- **3 DuckDB OLAP tables** — Yield, whale, blacklist time-series for analytical queries
- **16 new settings** — API keys and endpoints for Coinglass, Ethena, Sky, Liquity, Aave, Ondo, Blacklist monitor, Intel webhook
- **8 Alembic migrations** — Full schema evolution for V4 tables and column additions
- **V4 weight matrices** — 6 sub-types (USDT, USDC, DAI, LUSD, PYUSD, GHO) with per-component weights
- **Band unification** — `Healthy`, `Normal` (merged from Caution), `Warning`, `Distress`, `Critical`
- **CLI tool** — `scripts/add_stablecoin.py --type` argument for V4-compatible asset registration
- **`.gitignore` updates** — `*.onnx`, `*.duckdb`, `/data/` patterns

## v3.10.3 (2026-06-25)

- **Fix: Postgres playbook seed crash** — `_seed_builtin_playbooks` used `is_builtin = 1`, which fails on PostgreSQL BOOLEAN (`operator does not exist: boolean = integer`), causing uvicorn STARTUP_FAILURE (exit 3) during lifespan startup after alembic. Replaced with ORM `Playbook.is_builtin.is_(True)` filter, safe on both SQLite and Postgres.
- **Fix: Fail-loud lifespan** — Wrapped `lifespan()` startup in `try`/`except` that logs `lifespan.startup_failed` with full traceback to stderr before re-raising. Future startup crashes are visible even without container log capture.
- **Fix: Re-export `_within_budget`** — Added `_within_budget` to `ai_router.py` imports for `osint.py` and `sentiment.py` consumers.
- **Fix: CSP + nginx perf** — Re-added `unsafe-eval` to nginx CSP (unblocks Alpine.js), enabled gzip compression, added 7d immutable cache for static assets.
- **Fix: Redis persistence** — Added RDB snapshots + AOF to Redis config.
- **Fix: Chart.js removal** — Dropped Chart.js CDN (-250KB), rewrote charts.js to ECharts-only.
- **Fix: OSINT timeouts** — Added per-source 15s timeouts to RSS fetches and 20s timeout to Twitter GraphQL calls.
- **Fix: Audit follow-up** — Fixed `_makeBar`/`_renderForecastCanvas` exports (runtime import error), moved ECharts instances to `_echarts` map, replaced `immutable` cache with `no-cache` on non-hashed assets, added HSTS to static assets location, removed redundant `--save 3600 1` from Redis, added dependabot npm tracking for CDN deps.
- **Chore: Remove redundant docker profiles** — All services had `profiles: ["data"]`; stripped from postgres, redis, backend, frontend. `docker compose up -d` now works without `--profile data`. Updated CI, docs, and .env.example references.
- Rollback anchor: `c1e38bf`

## v3.10.2 (2026-06-24)

- Fix cache.py SyntaxError from indented try/except mismatch
- Re-release after Cursor re-verify

## v3.10.1 (2026-06-24)

Bugfix audit pass — 8 groups of fixes across auth, security, reliability, performance, and code quality.

### Group 1 — Auth
- Fix ghost identity in token parsing (A-3)
- Fix user list crash on null `email`/`login_enabled` (B-2)

### Group 2 — Security
- SSRF protection for webhook URLs via private IP check (A-2)
- Require admin auth on `/sources/status`, `/sources/usage`, `/sources/{name}/config` (F-1)
- Narrow CORS from wildcard `*` to explicit methods/headers (A-1)
- Remove `unsafe-eval` from CSP (A-8)

### Group 3 — Auth hardening
- Fix null user crash in audit log entries (B-1)
- Add `X-Frame-Options: DENY` to all responses (A-7)

### Group 4 — Reliability
- Fix `AttributeError` in `_attach_daily_latest` when datetime is unset (F-4)
- Atomic import lock via `INSERT ... WHERE NOT EXISTS` (F-5)
- Guard background tasks behind startup flags (C-1 + F-6)

### Group 5 — Performance
- Bulk DB queries for settings page load (D-2)
- Bulk freshness query for asset cache (D-3)

### Group 6 — Information disclosure
- Remove `platform.node()` from diagnostics (A-6)
- Sanitize error responses: strip internals from 500s (F-2)

### Group 7 — Performance
- Replace nested z-score loop with generator expression (D-1)

### Group 8 — Code quality
- Remove ~100 unused imports across backend (E-1)
- Replace all bare `except Exception: pass` with `logger.debug/warning` + `exc_info=True` (E-2)

## v3.10.0 (2026-05-28)

- Auth+API+DB hardening
- Signed session tokens
- SMIDGE join fix
- 500 crash hardening
- osint_article indexes
- Frontend ReferenceError/resize/audit-poll fixes
- Dockerignore cleanup
