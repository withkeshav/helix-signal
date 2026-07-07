# Helix-Signal

**Live:** [https://helix.withkeshav.com](https://helix.withkeshav.com)  
**Repository:** [github.com/withkeshav/helix-signal](https://github.com/withkeshav/helix-signal)  
**License:** MIT

Helix-Signal powers **Helix**, an open-source, self-hostable OSINT intelligence platform for stablecoins and chains.

One-stop monitoring terminal covering USDT, USDC, DAI, and PYUSD across 17+ chains. Fully self-hostable with a single `docker compose up`. AI intelligence via open-source models only (no paid ML APIs).

**460 regression tests pass (0 failed).**

**Model status (honest):** Until you train on historical depegs (`python scripts/train_depeg_model.py`) and set `ONNX_DEPEG_MODEL_PATH`, the UI shows `heuristic_v1` — a rule-based placeholder, not a model trained on real depeg events. Build V4 ONNX models with `python scripts/build_v4_models.py`. Heuristic `.onnx` stubs and `data/depeg_events.json` are now tracked in git so CI tests pass deterministically. See [`.progress/transform.md`](.progress/transform.md) §3.2 for the execution log.

## V4 Highlights

- **24-coin stablecoin taxonomy** — 4 types (Fiat-backed, Crypto-backed, Yield-bearing, Algorithmic) across USDT, USDC, DAI, PYUSD, FDUSD, FRAX, LUSD, GHO, sDAI, USDe, and more
- **Type-specific scoring** — Separate depeg model rules for Fiat (price_dev + coverage + attest_lag), Crypto (price_dev + coll_ratio + liq_queue), and Delta (price_dev + funding + insurance) with per-sub-type V4 weight matrices
- **ONNX ML models** — 3 models built via `onnx.helper` (opset 9): depeg probability, funding regime detection, yield sustainability. Build with `scripts/build_v4_models.py`
- **Investigation engine** — 8-step async pipeline (address clustering, bridge hop tracing, peel chain analysis, blacklist watch, on-chain token lookup, DEWS anomaly scoring, AI narrative generation, yield intelligence)
- **Forensics tab** — Dashboard tab with blacklist stats/events, wallet investigation form, and threat-level KPIs
- **Alerts inbox** — 7th dashboard tab showing fired `SignalEvent` rows with asset/severity filters plus active alert rule list. Backend: `GET /api/alerts` (admin-gated).
- **DEWS** — Distributed Early Warning System combining multi-source anomaly scores with circuit-breaker chain dispatch
- **6 new ORM tables** — `FiatReserve`, `Collateral`, `YieldBearing`, `FundingRate`, `WhaleActivity`, `BlacklistEvent` + 3 DuckDB OLAP tables
- **On-chain intelligence** — Alchemy RPC, Moralis, Flipside, The Graph, Chainlink Oracle feeds + address clustering + bridge hop tracking + peel chain detection
- **3 new API endpoints** — `/api/v1/investigate`, `/api/v1/yield/intelligence`, `/api/v1/blacklist/events`
- **8 Alembic migrations** — Full schema evolution for V4 tables and column additions
- **SA 2.0 style** — All 66 `db.query()` calls migrated to `select()` + `execute()` across 25 files
- **460 regression tests** — All tests pass, including 24 new tests for address tagging, clustering, and webhook dispatch

## V3 Highlights

- **V3 Risk Score**: 5-component composite (depeg 35%, concentration 20%, velocity 15%, liquidity depth 10%, age penalty 20%) with source health modifier. Weights sum to 1.0. Contracting supply contributes via abs().
- **Multi-source engine**: DefiLlama (supply, TVL, peg) + CoinGecko (price, market cap, volume) + DEX Screener (liquidity depth, pool concentration, slippage)
- **Cross-source price validator**: flags discrepancies >0.5% between sources
- **Alerting system**: 9 rule types (peg deviation, slippage, supply contraction, concentration, staleness, source failure/recovery, etc.) with persistence, dedup, and dispatch to dashboard + signed webhooks (primary for external automation: Zapier/Pabbly/Make/Slack/Discord/Telegram/email via webhook bridge). Configured in Settings UI (`webhook_*` keys). Legacy direct channels (native Telegram, Resend email) deferred.
- **OSINT feed**: RSS ingestion (Coindesk, CoinTelegraph, The Block) + LLM-powered sentiment scoring (Ollama Cloud)
- **Attestation & supply feed**: issuer report age (when parseable) plus DefiLlama on-chain supply feed freshness — no synthetic dates
- **Governance monitoring**: contract upgrade tracking via Etherscan API
- **AI anomaly detection** (gated): Z-score, Isolation Forest (trained on startup when enough history), StatsForecast forecast. Train ONNX depeg model with `scripts/train_depeg_model.py` using labels from `data/depeg_events.json`.
- **DuckDB analytics**: embedded time-series queries on trend data
- **17 chains**: Tron, Ethereum, BSC, Solana, Arbitrum, Polygon, Avalanche, Optimism, Base, Celo, Fantom, Gnosis, zkSync Era, Aptos, TON, Plasma, NEAR
- **Alpine.js + ECharts frontend**: 8-tab layout (Signal, Market, Analytics, Intel, Forensics, Alerts, System, Settings), lazy-mounted Settings tab, chart dispose-on-unmount, no build step, CDN-loaded

## Quick Start

### Prerequisites

- Docker Desktop (or Docker Engine + Compose)

### Run (recommended)

```bash
git clone https://github.com/withkeshav/helix-signal.git
cd helix-signal
cp .env.example .env
# REQUIRED before first deploy: SESSION_SIGNING_KEY (openssl rand -hex 32),
# POSTGRES_PASSWORD, HELIX_ADMIN_PASSWORD (for first admin seed)
# If SESSION_SIGNING_KEY is blank, all admin logins will fail with 503.
docker compose up --build -d
# Sign in at Settings → admin / your HELIX_ADMIN_PASSWORD
./scripts/smoke-check.sh http://localhost:80
```

### Public demo

A reference deployment is live at [helix.withkeshav.com](https://helix.withkeshav.com) (same Compose stack; set `HELIX_DOMAIN` in `.env` for your own host).

| Route | Access |
|-------|--------|
| [Dashboard](https://helix.withkeshav.com/) | Public UI + `/api/*` |

Before deploying your own instance, set in `.env`:

- `HELIX_DOMAIN` — public hostname (default `helix.local`)
- Keep `.env` and `secrets/` out of git (already in `.gitignore`)

Full-stack smoke test:

```bash
./scripts/smoke-check.sh https://your-domain.example
```

Backend container is internal-only; use `docker compose exec backend` for direct admin/debug access.

### Dev mode with hot-reload

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml up --build
```

### Local backend with Python venv

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python main.py
```

Or:

```bash
.venv/bin/uvicorn main:app --reload
```

Run tests:

```bash
cd backend
.venv/bin/pytest -q
```

Post-deploy smoke test (checks frontend shell, API health, `/metrics` not public, admin routes require auth):

```bash
./scripts/smoke-check.sh https://your-host.example
```

> **CI Setup:** The smoke job requires a `POSTGRES_PASSWORD` repository secret.
> See [CONTRIBUTING.md](./CONTRIBUTING.md#ci--github-actions-requirements) for
> the full list of required secrets and fork contributor notes.
> **CI artifacts:** Heuristic `.onnx` stubs (`backend/ml_models/*_heuristic.onnx`) and
> `data/depeg_events.json` are tracked in git (gitignore negations) so the `test` job
> runs deterministically. No separate generation step is needed.

### Database migrations

```bash
cd backend
.venv/bin/alembic upgrade head
```

Auto-generate a new migration after model changes:

```bash
.venv/bin/alembic revision --autogenerate -m "describe_change"
```

## Configuration

Copy `.env.example` to `.env` and adjust:

- `HELIX_DOMAIN` — public hostname (default `helix.local`)
- `CONTENT_SECURITY_POLICY` — Content-Security-Policy header (set on backend + nginx)
- `LOG_LEVEL` (default `INFO`) — set to `DEBUG` for verbose logging
- `LOG_FORMAT` (default `dev`) — set to `json` for structured JSON logs in production
- `SESSION_SIGNING_KEY` — **required**; HMAC-SHA256 key for signed session tokens
  (generate via `openssl rand -hex 32`). Backend fails closed with 503 if missing.
- `HELIX_ADMIN_TOKEN` — legacy admin token (retained for `X-Admin-Token` rollout safety;
  will be retired in a future release)
- `RATE_LIMITER_STORAGE_URI` — Redis URL for multi-worker rate limiting (optional)

All user-facing configuration (API keys, models, feature toggles, alert dispatch, refresh intervals, CORS origins) is managed from the Settings UI at `/settings` — no `.env` edits needed.

Configured chains: `config/chains.json`. Assets: `config/assets.json`. Alerts: `config/alerts.json`.

## API overview

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health` | Operational health and version |
| `GET /api/dashboard` | Live V3 risk monitoring payload |
| `GET /api/trends`, `/api/trends/chains` | Historical windows |
| `GET /api/trends/export`, `/api/events/export` | CSV/JSON export |
| `GET /api/compare` | Cross-asset aligned series |
| `GET /api/events` | Signal feed |
| `GET /api/forecasts` | Latest forecast runs |
| `GET /api/predictive` | Predictive bundle (depeg probability, regime, forecast) |
| `GET /api/analytics/correlations` | Pearson correlation matrix (5 metrics, ranked pairs) |
| `GET /api/analytics/patterns` | Trend/volatility/seasonality detection |
| `GET /api/analytics/finbert/sentiment` | On-demand FinBERT sentiment |
| `GET /api/anomaly/detect` | Z-score + Isolation Forest anomaly flags |
| `GET /api/anomaly/forecast` | Supply forecast (StatsForecast/AutoARIMA) |
| `POST /api/admin/backfill` | Optional synthetic history (env-gated; admin token required) |
| `GET /api/alerts/config` | Alert rule definitions (admin token required) |
| `GET /api/alerts` | Fired signal events with optional `?asset=`, `?severity=`, `?limit=` filters (admin token required) |
| `GET /api/settings` | Feature flags and refresh intervals (admin token required) |
| `PUT /api/settings` | Update settings (admin token required) |
| `GET /api/governance` | Governance monitoring (admin token required) |
| `GET /metrics` | Internal Prometheus metrics (admin token required; blocked at nginx) |
| `GET /api/osint/feed` | Recent news articles with sentiment |
| `GET /api/osint/sentiment` | Sentiment time-series |
| `GET /api/osint/attestation` | Issuer report age + DefiLlama supply feed freshness (per asset) |
| `GET /api/osint/correlate` | Sentiment-depeg correlation |
| `GET /api/data-quality/overview` | Data quality overview (admin token required) |
| `GET /api/data-quality/report` | Complete data quality report (admin token required) |
| `GET /api/data-quality/sources` | Source quality metrics (admin token required) |
| `GET /api/data-quality/assets` | Asset quality metrics (admin token required) |
| `GET /api/sources/status` | Source health dashboard with circuit breaker states |
| `GET /api/ai/explain` | LLM-generated risk explanation (env-gated) |
| `GET /api/settings/audit` | Settings audit log (admin token required) |
| `GET /api/settings/audit/history/{key}` | Change history for a specific setting (admin token required) |
| `GET /api/settings/export/json` | Export all settings as downloadable JSON (admin token required) |
| `POST /api/settings/import/json` | Import settings from uploaded JSON file (admin token required) |
| `POST /api/users` | Create user (admin token + multi-user enabled required) |
| `GET /api/users` | List all users (admin token + multi-user enabled required) |
| `POST /api/auth/login` | Authenticate user and return token (multi-user enabled required) |
| `POST /api/v1/investigate` | Investigation pipeline (peel chain, address clustering, bridge hops, blacklist query, OSINT, timeline, risk, AI narrative) |
| `GET /api/dews` | DEWS anomaly scoring and depeg probability per asset |
| `GET /api/onchain/whale-flow` | On-chain whale flow analysis (net inflows/outflows by asset) |
| `GET /api/onchain/holder-concentration` | Top-10 holder concentration percentage per asset |
| `GET /api/v1/blacklist/events` | Query blacklist events with optional filters (admin token required) |
| `GET /api/v1/tags/{address}` | Tags for an address (optional `?chain=` filter) |
| `POST /api/v1/tags` | Create an address tag (admin token required) |
| `DELETE /api/v1/tags/{tag_id}` | Delete a tag by ID (admin token required) |
| `GET /api/v1/tags/export` | CSV export of all address tags (admin token required) |
| `GET /api/v1/blacklist/stats` | Blacklist aggregate statistics (total events, frozen USD, by asset/chain) |
| `GET /api/v1/assets/{symbol}/yield` | Protocol yield analysis and scoring |
| `GET /api/v1/assets/{symbol}/collateral` | Collateral composition breakdown |
| `GET /api/v1/assets/{symbol}/reserve` | Reserve attestation data and timestamp |

## Project Structure

- `backend/` — FastAPI app, multi-source ingestion, analytics engine, alerts, OSINT, ONNX ML models
- `backend/agents/` — event-driven agents (anomaly detection, forecast, alert dispatch)
- `backend/chain/` — blockchain data retrieval + intelligence (address clustering, bridge hop tracking, peel chain detection)
- `backend/chain/intelligence/` — forensics modules (blacklist monitor, address clustering, bridge hop tracker, peel chain detector)
- `backend/core/` — framework (registry, plugin base, circuit breaker, cache, config loader, DB manager, rate limiter)
- `backend/middleware/` — security validation + observability middleware
- `backend/ml_models/` — V4 ONNX models (depeg events, funding regime, yield sustainability)
- `backend/routes/` — modular route files (dashboard, trends, events, analytics, osint, sources, investigate, yield, blacklist, onchain, dews)
- `backend/services/` — core services (cache, dashboard, anomaly, investigation engine, DEWS, onchain, walk-forward)
- `backend/sources/plugins/` — source plugins (DeFiLlama, CoinGecko, DEX Screener, Ethena, Coinglass, Sky, Liquity, Aave, Ondo) with circuit breakers
- `backend/signal_engine/` — V4 risk scoring (scoring, metrics, history, risk inputs, component scorers)
- `backend/services/scheduler.py` — Scheduled job orchestrator (11 functions extracted from `main.py`)
- `backend/services/attestation.py` — Reserve attestation parsing and freshness scoring
- `backend/services/rss_feed.py` — OSINT RSS feed ingestion with sentiment scoring
- `backend/data_quality/` — Data quality checks (freshness, cross-source validation, coverage) using SA 2.0 style
- `frontend/` — pure static HTML, Alpine.js 8-tab dashboard (lazy-mounted Settings), ECharts with dispose-on-unmount, nginx API proxy
- `frontend/js/` — ES6 modules (init, charts, market, osint, governance, forecast, forensics, onchain, taxonomy) + 3 Web Components
- `config/` — chain, asset, and alert configuration
- `docs/` — Architecture, API reference, plus `concepts/`, `guides/`, and `reference/` subdirectories
- `scripts/` — deployment smoke checks, backup.sh, SQLite→Postgres migration, ONNX model builder, depeg training

**SQLite → Postgres on a server:** run [`scripts/migrate_sqlite_to_postgres.py`](scripts/migrate_sqlite_to_postgres.py) with backups and `--verify-only` before cutover.

## Documentation (in repo)

- 📖 [Documentation index](docs/README.md)
- Architecture: [`docs/architecture.md`](docs/architecture.md)
- API reference: [`docs/api.md`](docs/api.md)
- AI Configuration: [`docs/guides/ai-configuration.md`](docs/guides/ai-configuration.md)
- Data methodology: [`docs/concepts/data-methodology.md`](docs/concepts/data-methodology.md)
- Adding a stablecoin: [`docs/guides/adding-asset.md`](docs/guides/adding-asset.md)
- Adding a chain: [`docs/guides/adding-chain.md`](docs/guides/adding-chain.md)
- Plugin development: [`docs/guides/plugins.md`](docs/guides/plugins.md)
- Scoring design: [`docs/scoring-design.md`](docs/scoring-design.md)
- Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security: [`SECURITY.md`](SECURITY.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)
- Backup script: [`scripts/backup.sh`](scripts/backup.sh)

## Not Investment Advice

Helix-Signal is an informational monitoring tool. It is **not** investment advice, financial advice, trading advice, or risk guidance.
Always perform your own due diligence before making financial decisions.
