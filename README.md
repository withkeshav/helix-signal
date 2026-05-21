# Helix-Signal

**Live:** [https://helix.withkeshav.com](https://helix.withkeshav.com)  
**Repository:** [github.com/withkeshav/helix-signal](https://github.com/withkeshav/helix-signal)

Helix-Signal powers **Helix**, an open-source, self-hostable OSINT intelligence platform for stablecoins and chains.

One-stop monitoring terminal covering USDT, USDC, DAI, and PYUSD across 17+ chains. Fully self-hostable with a single `docker compose up`. AI intelligence via open-source models only (no paid ML APIs).

## V3 Highlights

- **V3 Risk Score**: 5-component composite (peg stability 35%, liquidity depth 25%, supply stability 15%, concentration 15%, observability 10%) with hard overrides
- **Multi-source engine**: DefiLlama (supply, TVL, peg) + CoinGecko (price, market cap, volume) + DEX Screener (liquidity depth, pool concentration, slippage)
- **Cross-source price validator**: flags discrepancies >0.5% between sources
- **Alerting system**: 9 rule types with persistence tracking, dedup, 4 dispatch channels (dashboard, webhook, Discord, Telegram)
- **OSINT feed**: RSS ingestion (Coindesk, CoinTelegraph, The Block) + CryptoPanic API + FinBERT sentiment scoring
- **Attestation & supply feed**: issuer report age (when parseable) plus DefiLlama on-chain supply feed freshness — no synthetic dates
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
git clone https://github.com/withkeshav/helix-signal.git
cd helix-signal
cp .env.example .env
mkdir -p secrets
echo "set-a-strong-password" > secrets/grafana_admin_password.txt
docker network create web_gateway || true
docker compose up --build -d
./scripts/smoke-check.sh http://localhost:3000
```

### Public demo

A reference deployment is live at [helix.withkeshav.com](https://helix.withkeshav.com) (same Compose stack; set `HELIX_DOMAIN` in `.env` for your own host).

| Route | Access |
|-------|--------|
| [Dashboard](https://helix.withkeshav.com/) | Public UI + `/api/*` |
| Admin surfaces (`/dashboard/`, `/prometheus/`, `/grafana/`) | Basic-auth protected on a full Traefik deploy |

Before deploying your own instance, set in `.env`:

- `HELIX_DOMAIN` — hostname Traefik routes to (default `helix.local`)
- Replace the Traefik basic-auth user in `traefik/dynamic/middlewares.yml` (default `admin` / `changeme`)
- Set ACME contact email in `traefik/traefik.yml`
- Create `secrets/cloudflare_token.txt` if using Cloudflare DNS challenge (see `docker-compose.yml`)
- Keep `acme.json`, `.env`, and `secrets/` out of git (already in `.gitignore`)

Full-stack smoke test (Traefik + TLS + admin auth):

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

Post-deploy smoke test (checks frontend shell, API health, auth on admin routes, `/metrics` not public):

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

- `HELIX_DOMAIN` — public hostname for Traefik routing (default `helix.local`; required for TLS production deploy)
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
| `GET /api/osint/attestation` | Issuer report age + DefiLlama supply feed freshness (per asset) |
| `GET /api/osint/correlate` | Sentiment-depeg correlation |
| `GET /api/governance` | Governance monitoring |
| `GET /api/anomaly/detect` | Z-score + Isolation Forest anomaly flags |
| `GET /api/anomaly/forecast` | Supply forecast (Prophet) |
| `GET /metrics` | Internal metrics endpoint (not publicly exposed via frontend route) |

## Project Structure

- `backend/` — FastAPI app, multi-source ingestion, DuckDB analytics, alerts, OSINT, governance, ML anomaly detection, Alembic migrations
- `frontend/` — Alpine.js dashboard (`index.html` + `app.js`), Chart.js, nginx API proxy in Docker
- `config/` — chain, asset, and alert configuration
- `docs/` — architecture and methodology (public)
- `scripts/` — deployment smoke checks
- `traefik/` — reverse proxy static config + `dynamic/middlewares.yml` for basic auth

Internal planning briefs, `.progress`, and local `research/` artifacts are gitignored and not part of the public repo.

## Documentation

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Data methodology: [`docs/data-methodology.md`](docs/data-methodology.md)
- Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security: [`SECURITY.md`](SECURITY.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)
- Release notes: [`RELEASE_NOTES.md`](RELEASE_NOTES.md)

## Not Investment Advice

Helix-Signal is an informational monitoring tool. It is **not** investment advice, financial advice, trading advice, or risk guidance.
Always perform your own due diligence before making financial decisions.
