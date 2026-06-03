# Helix-Signal

**Live:** [https://helix.withkeshav.com](https://helix.withkeshav.com)  
**Repository:** [github.com/withkeshav/helix-signal](https://github.com/withkeshav/helix-signal)  
**License:** MIT

Helix-Signal powers **Helix**, an open-source, self-hostable OSINT intelligence platform for stablecoins and chains.

One-stop monitoring terminal covering USDT, USDC, DAI, and PYUSD across 17+ chains. Fully self-hostable with a single `docker compose up`. AI intelligence via open-source models only (no paid ML APIs).

**328 regression tests pass.** Zero paid API dependencies for core operation.

## V3 Highlights

- **V3 Risk Score**: Composite (depeg 35%, concentration 25%, velocity 20%, age penalty 20%) with source health modifier
- **Multi-source engine**: DefiLlama (supply, TVL, peg) + CoinGecko (price, market cap, volume) + DEX Screener (liquidity depth, pool concentration, slippage)
- **Cross-source price validator**: flags discrepancies >0.5% between sources
- **Alerting system**: 9 rule types with persistence tracking, dedup, 4 dispatch channels (dashboard, webhook, Discord, Telegram)
- **OSINT feed**: RSS ingestion (Coindesk, CoinTelegraph, The Block) + LLM-powered sentiment scoring (Ollama Cloud)
- **Attestation & supply feed**: issuer report age (when parseable) plus DefiLlama on-chain supply feed freshness — no synthetic dates
- **Governance monitoring**: contract upgrade tracking via Etherscan API
- **AI anomaly detection** (gated): Z-score, Isolation Forest, StatsForecast forecast — enable via Settings UI
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
# Set POSTGRES_PASSWORD in .env (required — docker will error if empty)
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
- `CONTENT_SECURITY_POLICY` — Content-Security-Policy header (set on backend + nginx)
- `LOG_LEVEL` (default `INFO`) — set to `DEBUG` for verbose logging
- `LOG_FORMAT` (default `dev`) — set to `json` for structured JSON logs in production
- `HELIX_ADMIN_TOKEN` — required for admin routes (settings, refresh, backfill, metrics, governance)
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
| `GET /api/chains/{chain_key}` | Chain drill-down |
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

## Project Structure

- `backend/` — FastAPI app, multi-source ingestion, analytics engine, alerts, OSINT, ML models
- `backend/agents/` — event-driven agents (anomaly detection, forecast, alert dispatch)
- `backend/chain/` — blockchain data retrieval layer
- `backend/core/` — framework (registry, plugin base, circuit breaker, cache, config loader, DB manager, rate limiter)
- `backend/middleware/` — security validation + observability middleware
- `backend/routes/` — modular route files (dashboard, trends, events, analytics, osint, sources, etc.)
- `backend/sources/plugins/` — source plugins (DeFiLlama, CoinGecko, DEX Screener) with circuit breakers
- `backend/signal_engine/` — V3 risk scoring (scoring, metrics, history, risk inputs)
- `frontend/` — pure static HTML, Alpine.js 6-tab dashboard, Chart.js + ECharts, nginx API proxy
- `frontend/js/` — ES6 modules (init, charts, market, osint, governance, forecast) + 3 Web Components
- `config/` — chain, asset, and alert configuration
- `docs/` — Architecture, API reference, plus `concepts/`, `guides/`, and `reference/` subdirectories
- `scripts/` — deployment smoke checks, backup.sh, SQLite→Postgres migration

**SQLite → Postgres on a server:** run [`scripts/migrate_sqlite_to_postgres.py`](scripts/migrate_sqlite_to_postgres.py) with backups and `--verify-only` before cutover.

## Documentation (in repo)

- 📖 [Documentation index](docs/README.md)
- Architecture: [`docs/architecture.md`](docs/architecture.md)
- API reference: [`docs/api.md`](docs/api.md)
- Data methodology: [`docs/concepts/data-methodology.md`](docs/concepts/data-methodology.md)
- Adding a stablecoin: [`docs/guides/adding-asset.md`](docs/guides/adding-asset.md)
- Adding a chain: [`docs/guides/adding-chain.md`](docs/guides/adding-chain.md)
- Plugin development: [`docs/guides/plugins.md`](docs/guides/plugins.md)
- Code quality improvements: [`docs/reference/phase6_code_quality.md`](docs/reference/phase6_code_quality.md)
- Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security: [`SECURITY.md`](SECURITY.md)
- Changelog: [`docs/reference/changelog.md`](docs/reference/changelog.md)
- Backup script: [`scripts/backup.sh`](scripts/backup.sh)

## Not Investment Advice

Helix-Signal is an informational monitoring tool. It is **not** investment advice, financial advice, trading advice, or risk guidance.
Always perform your own due diligence before making financial decisions.
