# Helix-Signal

Helix-Signal powers **Helix**, an open-source, self-hostable dashboard for chain-level stablecoin signals.
It turns public data into a clean monitoring surface for supply concentration, peg pressure, freshness, and source health.

## Why Helix

- Transparent: built on publicly accessible data sources
- Self-hostable: runs locally with Docker, no paid dependency required for core features
- Multi-asset monitoring (USDT default; USDC, DAI, PYUSD when enabled) with historical trends and a local signal feed

## V2.5 Highlights

- **CI and tests**: GitHub Actions plus pytest (scoring, history, API smoke) using in-memory SQLite
- **Health**: `GET /api/health` with database reachability, last successful fetch, scheduler status, version `2.5.0`
- **Retention**: configurable pruning for trend and event tables (`TREND_RETENTION_DAYS`, `EVENT_RETENTION_DAYS`)
- **Deploy hygiene**: Compose loads `.env`; frontend nginx proxies `/api` to the backend; relative API URLs (no hardcoded localhost)
- **Analyst workflows**: CSV/JSON export for trends and events, cross-asset compare chart, chain drill-down side panel
- **Optional backfill**: env-gated `POST /api/admin/backfill` for coarse synthetic history on new installs

## V2.4 Highlights

- **Historical trends**: SQLite snapshots after each successful refresh, bucketed in 5-minute UTC windows, exposed through `/api/trends` and `/api/trends/chains`
- **Signal feed**: local, deduplicated `signal_events` timeline with `/api/events` and a dashboard analyst-style panel
- **Dashboard**: time window selector (24h, 7d, 30d), four trend charts (signal score, Depeg Index, supply, concentration), low-data copy when fewer than two points exist

## V2.3 Highlights

- **Helix Signal Score**: transparent composite 0 to 100 (Normal, Watch, Risk) from peg pressure, supply momentum, chain concentration, and data confidence
- **Depeg Index**, chain concentration (HHI), server-side freshness, and labeled chain aggregate TVL from DefiLlama `stablecoinchains`

## Quick Start

### Prerequisites

- Docker Desktop (or Docker Engine + Compose)

### Run (recommended)

```bash
cp .env.example .env
docker compose up --build
```

- Dashboard: [http://localhost:3000](http://localhost:3000) (API proxied at `/api`)
- Backend API direct: [http://localhost:8000](http://localhost:8000)

### Local backend with Python venv

All Python dependencies install into `backend/.venv` only:

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
- `TREND_RETENTION_DAYS` (default `90`), `EVENT_RETENTION_DAYS` (default `30`)
- `ALLOW_BACKFILL` (default `false`) — enable optional historical seeding
- `DEFILLAMA_API_KEY` — reserved for a future Pro API toggle; not required for core ingest today

Configured chains: `config/chains.json`. Assets: `config/assets.json`.

## API overview

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health` | Operational health and version |
| `GET /api/dashboard` | Live monitoring payload |
| `GET /api/trends`, `/api/trends/chains` | Historical windows |
| `GET /api/trends/export`, `/api/events/export` | CSV/JSON export |
| `GET /api/compare` | Cross-asset aligned series |
| `GET /api/chains/{chain_key}` | Chain drill-down |
| `GET /api/events` | Local signal feed |
| `POST /api/admin/backfill` | Optional synthetic history (env-gated) |

## Project Structure

- `backend/` FastAPI app, scheduler, DefiLlama integration, SQLite models, services, tests
- `frontend/` static HTML/CSS/JS dashboard with Chart.js and nginx API proxy in Docker
- `config/` chain and asset configuration
- `docs/` architecture and methodology

## Documentation

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Data methodology: [`docs/data-methodology.md`](docs/data-methodology.md)
- Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security: [`SECURITY.md`](SECURITY.md)
- Release notes: [`RELEASE_NOTES.md`](RELEASE_NOTES.md)

## Not Investment Advice

Helix-Signal is an informational monitoring tool. It is **not** investment advice, financial advice, trading advice, or risk guidance.
Always perform your own due diligence before making financial decisions.
