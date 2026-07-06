# Helix Signal Changelog

## v4.0.0 (2026-07-05)

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
