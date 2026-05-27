# Helix-Signal

**Live:** [https://helix.withkeshav.com](https://helix.withkeshav.com)  
**Repository:** [github.com/withkeshav/helix-signal](https://github.com/withkeshav/helix-signal)  
**License:** MIT

Helix-Signal powers **Helix**, an open-source, self-hostable OSINT intelligence platform for stablecoins and chains.

One-stop monitoring terminal covering USDT, USDC, DAI, and PYUSD across 17+ chains. Fully self-hostable with a single `docker compose up`. AI intelligence via open-source models only (no paid ML APIs).

**99 regression tests pass.** Zero paid API dependencies for core operation.

## v3.7.0 Highlights

- **AI Settings UI** — New AI & Anomaly Detection card in Settings tab: mode select (Off/Lite/Full), token budget bar, toggle switches, number inputs
- **Token budget endpoint** — `GET /api/ai/budget` exposes daily usage with real-time progress bar in frontend
- **OpenRouter free tier** — `openrouter/free` added as primary provider in `ai_lite`/`ai_full` chains
- **6 new DB-backed settings** — AI mode, token budget, cache TTL, web search, anomaly detection all editable via Settings UI
- **Anomaly detection enhanced** — `latest_zscore()`, `min_bps` filter, `STD_FLOOR` env var
- **sync-env.sh** — Utility to merge `.env.example` keys into `.env` preserving existing values
- **124 regression tests pass**

## v3.3 Highlights

- **Traefik/Prometheus/Grafana removed** — lighter stack, no TLS secrets or Cloudflare token needed
- **Forecast charts wired to API** — `renderForecastCharts()` uses real `ForecastRun`/`ForecastPoint` data, mock arrays removed
- **Auto-backfill on first run** — fresh databases get 7 days of historical data seeded automatically
- **`LOG_LEVEL` filtering** — `LOG_LEVEL=ERROR` now actually suppresses debug output
- **`previous_status` for source recovery** — alert rule `source transitions error` now fires correctly
- **Compose health conditions** — `frontend` waits for `backend: service_healthy`, redis has `redis-cli ping` healthcheck
- **90d window support** — `window_delta()`, middleware, and compare service all accept `90d`
- **Alembic migration for `previous_status`** — Postgres users don't hit column-missing errors on refresh
- **P0–P3 audit fixes** — 15+ items across behavior, hardening, and cleanup (see CHANGELOG for full list)

## V3 Highlights

- **V3 Risk Score**: 5-component composite (peg stability 35%, liquidity depth 25%, supply stability 15%, concentration 15%, observability 10%) with hard overrides
- **Multi-source engine**: DefiLlama (supply, TVL, peg) + CoinGecko (price, market cap, volume) + DEX Screener (liquidity depth, pool concentration, slippage)
- **Cross-source price validator**: flags discrepancies >0.5% between sources
- **Alerting system**: 9 rule types with persistence tracking, dedup, 4 dispatch channels (dashboard, webhook, Discord, Telegram)
- **OSINT feed**: RSS ingestion (Coindesk, CoinTelegraph, The Block) + CryptoPanic API + FinBERT sentiment scoring
- **Attestation & supply feed**: issuer report age (when parseable) plus DefiLlama on-chain supply feed freshness — no synthetic dates
- **Governance monitoring**: contract upgrade tracking via Etherscan API
- **AI anomaly detection** (gated): Z-score, Isolation Forest, StatsForecast forecast — enabled via `ENABLE_ANOMALY_DETECTION=true`
- **DuckDB analytics**: embedded time-series queries on trend data
- **17 chains**: Tron, Ethereum, BSC, Solana, Arbitrum, Polygon, Avalanche, Optimism, Base, Celo, Fantom, Gnosis, zkSync Era, Aptos, TON, Plasma, NEAR
- **Alpine.js + Chart.js + ECharts frontend**: 6-tab layout (Market, Forecast, Supply, Events, Intel, Health), no build step, CDN-loaded

## Quick Start

### Prerequisites

- Docker Desktop (or Docker Engine + Compose)

### Run (recommended)

```bash
git clone https://github.com/withkeshav/helix-signal.git
cd helix-signal
cp .env.example .env
docker compose up --build -d
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
- `CORS_ORIGINS` — comma-separated allowed origins (default `*`); set in production
- `CONTENT_SECURITY_POLICY` — Content-Security-Policy header (set on backend + nginx)
- `REFRESH_INTERVAL_SECONDS` (default `300`)
- `ENABLE_ANOMALY_DETECTION` (default `false`) — enables ML anomaly detection (requires scikit-learn, numpy, pandas, statsforecast)
- `ENABLE_NLP` (default `false`) — enables FinBERT sentiment scoring (requires transformers + PyTorch)
- `ENABLE_DYNAMIC_CHAINS` (default `false`) — auto-discovers chains from DefiLlama instead of static config
- `ETHERSCAN_API_KEY` — for governance monitoring
- `ALERT_WEBHOOK_URL`, `ALERT_DISCORD_WEBHOOK`, `ALERT_TELEGRAM_BOT_TOKEN` — alert dispatch channels
- `CRYPTOPANIC_API_KEY` — for news feed
- `LOG_LEVEL` (default `INFO`) — set to `DEBUG` for verbose logging
- `LOG_FORMAT` (default `dev`) — set to `json` for structured JSON logs in production
- `HELIX_ADMIN_TOKEN` — required for admin routes (settings, refresh, backfill, metrics, governance)
- `RATE_LIMITER_STORAGE_URI` — Redis URL for multi-worker rate limiting (optional)

Configured chains: `config/chains.json`. Assets: `config/assets.json`. Alerts: `config/alerts.json`.

## API overview

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health` | Operational health and version |
| `GET /api/dashboard` | Live V3 risk monitoring payload |
| `GET /api/trends`, `/api/trends/chains` | Historical windows |
| `GET /api/trends/export`, `/api/events/export` | CSV/JSON export |
| `GET /api/compare` | Cross-asset aligned series |
| `GET /api/chains/{chain_key}` | Chain drill-down |
| `GET /api/events` | Signal feed |
| `GET /api/forecasts` | Latest forecast runs |
| `GET /api/predictive` | Predictive bundle (depeg probability, regime, TimesFM) |
| `GET /api/analytics/correlations` | Pearson correlation matrix (5 metrics, ranked pairs) |
| `GET /api/analytics/patterns` | Trend/volatility/seasonality detection |
| `GET /api/analytics/finbert/sentiment` | On-demand FinBERT sentiment |
| `GET /api/anomaly/detect` | Z-score + Isolation Forest anomaly flags |
| `GET /api/anomaly/forecast` | Supply forecast (StatsForecast/AutoARIMA) |
| `POST /api/admin/backfill` | Optional synthetic history (env-gated; admin token required) |
| `GET /api/alerts/config` | Alert rule definitions (admin token required) |
| `GET /api/settings` | Feature flags and refresh intervals (admin token required) |
| `PUT /api/settings` | Update settings (admin token required) |
| `GET /api/governance` | Governance monitoring (admin token required) |
| `GET /metrics` | Internal Prometheus metrics (admin token required; blocked at nginx) |
| `GET /api/osint/feed` | Recent news articles with sentiment |
| `GET /api/osint/sentiment` | Sentiment time-series |
| `GET /api/osint/attestation` | Issuer report age + DefiLlama supply feed freshness (per asset) |
| `GET /api/osint/correlate` | Sentiment-depeg correlation |
| `GET /api/governance` | Governance monitoring |
| `GET /api/sources/status` | Source health dashboard with circuit breaker states |
| `GET /api/ai/explain` | LLM-generated risk explanation (env-gated) |
| `GET /metrics` | Internal Prometheus metrics (blocked at nginx in production) |

## Project Structure

- `backend/` — FastAPI app, multi-source ingestion, analytics engine, alerts, OSINT, ML models
- `backend/agents/` — event-driven agents (anomaly detection, forecast, alert dispatch)
- `backend/chain/` — blockchain data retrieval layer
- `backend/core/` — framework (registry, plugin base, circuit breaker, cache, config loader, DB manager, rate limiter, OLAP)
- `backend/mcp_server.py` — standalone FastMCP server (port 8100, Stdio/SSE transport)
- `backend/middleware/` — security validation + observability middleware
- `backend/routes/` — modular route files (dashboard, trends, events, analytics, osint, sources, etc.)
- `backend/sources/plugins/` — source plugins (DeFiLlama, CoinGecko, DEX Screener) with circuit breakers
- `backend/signal_engine/` — V3 risk scoring (scoring, metrics, history, risk inputs)
- `frontend/` — pure static HTML, Alpine.js 6-tab dashboard, Chart.js + ECharts, nginx API proxy
- `frontend/js/` — ES6 modules (market, osint, governance, forecast) + 3 Web Components + init.js
- `config/` — chain, asset, and alert configuration
- `docker/clickhouse/` — ClickHouse schema for OLAP deployment (optional)
- `docs/` — architecture, data methodology, adding-asset, adding-chain, plugins, API ref, grant strategy
- `scripts/` — deployment smoke checks, backup.sh, SQLite→Postgres migration

**SQLite → Postgres on a server:** run [`scripts/migrate_sqlite_to_postgres.py`](scripts/migrate_sqlite_to_postgres.py) with backups and `--verify-only` before cutover.

## Documentation (in repo)

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Data methodology: [`docs/data-methodology.md`](docs/data-methodology.md)
- Adding a stablecoin: [`docs/adding-asset.md`](docs/adding-asset.md)
- Adding a chain: [`docs/adding-chain.md`](docs/adding-chain.md)
- Plugin development: [`docs/plugins.md`](docs/plugins.md)
- API reference: [`docs/api.md`](docs/api.md)
- Grant strategy: [`docs/grant-strategy.md`](docs/grant-strategy.md)
- Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security: [`SECURITY.md`](SECURITY.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)
- Backup script: [`scripts/backup.sh`](scripts/backup.sh)

## Not Investment Advice

Helix-Signal is an informational monitoring tool. It is **not** investment advice, financial advice, trading advice, or risk guidance.
Always perform your own due diligence before making financial decisions.
