# Helix-Signal

Helix-Signal powers **Helix**, an open-source, self-hostable OSINT intelligence platform for stablecoins and chains.

One-stop monitoring terminal covering USDT, USDC, DAI, and PYUSD across 17+ chains. Fully self-hostable with a single `docker compose up`. AI intelligence via open-source models only (no paid ML APIs).

## V3 Highlights

- **V3 Risk Score**: 5-component composite (peg stability 35%, liquidity depth 25%, supply stability 15%, concentration 15%, observability 10%) with hard overrides
- **Multi-source engine**: DefiLlama (supply, TVL, peg) + CoinGecko (price, market cap, volume) + DEX Screener (liquidity depth, pool concentration, slippage)
- **Cross-source price validator**: flags discrepancies >0.5% between sources
- **Alerting system**: 9 rule types with persistence tracking, dedup, 4 dispatch channels (dashboard, webhook, Discord, Telegram)
- **OSINT feed**: RSS ingestion (Coindesk, CoinTelegraph, The Block) + CryptoPanic API + FinBERT sentiment scoring
- **Governance monitoring**: contract upgrade tracking via Etherscan API
- **AI anomaly detection** (gated): Z-score, Isolation Forest, Prophet forecast — enabled via `ENABLE_ANOMALY_DETECTION=true`
- **DuckDB analytics**: embedded time-series queries on trend data
- **17 chains**: Tron, Ethereum, BSC, Solana, Arbitrum, Polygon, Avalanche, Optimism, Base, Celo, Fantom, Gnosis, zkSync Era, Aptos, TON, Plasma, NEAR
- **Alpine.js + htmx frontend**: 4-tab layout (Overview, Peg & Liquidity, Supply & Flows, Intelligence), no build step, CDN-loaded

## Quick Start

### Prerequisites

- Docker Desktop (or Docker Engine + Compose)

### Run (recommended)

```bash
cp .env.example .env
mkdir -p secrets && echo "admin" > secrets/grafana_admin_password.txt
docker compose up --build
```

- Dashboard: [http://helix.local](http://helix.local) (via Traefik, API proxied at `/api`)
- Backend API direct: [http://localhost:8000](http://localhost:8000)
- Prometheus: [http://prometheus.helix.local](http://prometheus.helix.local)
- Grafana: [http://grafana.helix.local](http://grafana.helix.local) (default: admin / admin)
- Traefik dashboard: [http://localhost:8080](http://localhost:8080) (dev only)

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

## Configuration

Copy `.env.example` to `.env` and adjust:

- `DATABASE_URL` — see comments in `.env.example` for local venv vs Docker paths
- `REFRESH_INTERVAL_SECONDS` (default `300`)
- `ENABLE_ANOMALY_DETECTION` (default `false`) — enables ML anomaly detection (requires scikit-learn, numpy, pandas, statsforecast)
- `ENABLE_NLP` (default `false`) — enables FinBERT sentiment scoring (requires transformers + PyTorch)
- `ENABLE_DYNAMIC_CHAINS` (default `false`) — auto-discovers chains from DefiLlama instead of static config
- `ETHERSCAN_API_KEY` — for governance monitoring
- `ALERT_WEBHOOK_URL`, `ALERT_DISCORD_WEBHOOK`, `ALERT_TELEGRAM_BOT_TOKEN` — alert dispatch channels
- `CRYPTOPANIC_API_KEY` — for news feed

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
| `POST /api/admin/backfill` | Optional synthetic history (env-gated) |
| `GET /api/alerts/config` | Alert rule definitions |
| `GET /api/osint/feed` | Recent news articles with sentiment |
| `GET /api/osint/sentiment` | Sentiment time-series |
| `GET /api/osint/attestation` | Transparency report freshness |
| `GET /api/osint/correlate` | Sentiment-depeg correlation |
| `GET /api/governance` | Governance monitoring |
| `GET /api/anomaly/detect` | Z-score + Isolation Forest anomaly flags |
| `GET /api/anomaly/forecast` | Supply forecast (Prophet) |
| `GET /metrics` | Prometheus metrics (request count, latency, scheduler, source health) |

## Project Structure

- `backend/` FastAPI app, multi-source ingestion, DuckDB analytics, alerts, OSINT, governance, ML anomaly detection, 15 tests
- `frontend/` Alpine.js + htmx + Chart.js dashboard with nginx API proxy in Docker
- `config/` chain, asset, and alert configuration
- `docs/` architecture and methodology
- `research/` platform research artifacts

## Documentation

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Data methodology: [`docs/data-methodology.md`](docs/data-methodology.md)
- Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security: [`SECURITY.md`](SECURITY.md)
- Release notes: [`RELEASE_NOTES.md`](RELEASE_NOTES.md)

## Not Investment Advice

Helix-Signal is an informational monitoring tool. It is **not** investment advice, financial advice, trading advice, or risk guidance.
Always perform your own due diligence before making financial decisions.
