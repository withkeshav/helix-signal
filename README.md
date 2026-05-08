# Helix-Signal

Helix-Signal powers **Helix**, an open-source, self-hostable dashboard for chain-level stablecoin signals.
It turns public data into a clean monitoring surface for supply concentration, peg pressure, freshness, and source health.

## Why Helix

- Transparent: built on publicly accessible data sources
- Self-hostable: runs locally with Docker, no paid dependency required for core features
- Focused: V1 is intentionally narrow and reliable (USDT + top chains)

## V2.1 Highlights

- Top 10 chains by configured USDT coverage
- USDT circulating supply snapshot per chain
- 24h change (%) using DefiLlama previous-day values
- TVL context for each chain (when available)
- Peg status classification around $1.00
- Source health footer for DefiLlama status
- Lightweight sparklines from current / previous day / previous week supply values
- Theme system (auto/light/dark) with saved preference
- Manual refresh control with non-blocking error handling
- Freshness confidence labels (Fresh, Aging, Stale)
- Multi-asset-ready backend model (`asset_chain_snapshots`) with USDT as default enabled asset
- Asset-aware dashboard contract (`/api/dashboard?asset=USDT`) with backward-friendly default behavior

## Quick Start

### Prerequisites

- Docker Desktop (or Docker Engine + Compose)

### Run

```bash
docker compose up --build
```

### Backend-only (without Docker)

From `backend/`:

```bash
python main.py
```

Or:

```bash
uvicorn main:app --reload
```

### Local development with Python `venv`

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .\.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Open

- Backend API: [http://localhost:8000](http://localhost:8000)
- Dashboard API payload: [http://localhost:8000/api/dashboard](http://localhost:8000/api/dashboard)
- Frontend dashboard: [http://localhost:3000](http://localhost:3000)

## Configuration

Copy values from `.env.example` as needed:

- `DEFILLAMA_API_KEY` (optional; not required for core V1)
- `DATABASE_URL` (SQLite path)
- `REFRESH_INTERVAL_SECONDS` (default `300`)

Configured chains are pinned in `config/chains.json`.
Configured assets are defined in `config/assets.json` (USDT enabled by default; other assets disabled by default).

## Project Structure

- `backend/` FastAPI app, scheduler, DefiLlama integration, SQLite models
- `frontend/` static HTML/CSS/JS dashboard with Chart.js sparklines
- `config/` chain/source configuration
- `docs/` architecture and methodology documentation

## Documentation

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Data methodology: [`docs/data-methodology.md`](docs/data-methodology.md)
- Contributing guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security policy: [`SECURITY.md`](SECURITY.md)
- Release notes: [`RELEASE_NOTES.md`](RELEASE_NOTES.md)

## Not Investment Advice

Helix-Signal is an informational monitoring tool. It is **not** investment advice, financial advice, trading advice, or risk guidance.
Always perform your own due diligence before making financial decisions.
