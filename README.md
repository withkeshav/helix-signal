# Helix-Signal

Helix-Signal powers **Helix**, an open-source, self-hostable dashboard for chain-level stablecoin signals.
It turns public data into a clean monitoring surface for supply concentration, peg pressure, freshness, and source health.

## Why Helix

- Transparent: built on publicly accessible data sources
- Self-hostable: runs locally with Docker, no paid dependency required for core features
- Focused: V1 is intentionally narrow and reliable (USDT + top chains)

## V2.3 Highlights

- **Helix Signal Score**: transparent composite 0 to 100 (Normal, Watch, Risk) from peg pressure, supply momentum, chain concentration, and data confidence, with explicit weights in the API and UI
- **Depeg Index**: asset-level peg stress score and deviation context from DefiLlama price (documented as not chain-specific oracle precision)
- **Derived metrics**: aggregate total supply, aggregate 24h supply change, Herfindahl-style concentration (HHI), per-chain share, momentum labels, per-chain signal and data confidence
- **Server-side freshness**: UTC-aware basis timestamp as `max(last_successful_fetch, newest_chain_snapshot)` with Fresh, Aging, and Stale windows aligned to `REFRESH_INTERVAL_SECONDS`
- **Chain TVL (labeled)**: optional column sourced from DefiLlama `stablecoinchains` as **chain-level aggregate** stablecoin TVL, not per-asset TVL
- Premium-style monitoring layout: KPI strip, methodology panel, Depeg and concentration cards, Chart.js share and component charts, expanded chain table
- Multi-asset support unchanged (USDT default; USDC, DAI, PYUSD when enabled in `config/assets.json`)
- Static Vanilla JS + Chart.js frontend (no framework migration)

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
Configured assets are defined in `config/assets.json` (USDT remains default).
Use the dashboard asset selector to switch across enabled assets.

## Project Structure

- `backend/` FastAPI app, scheduler, DefiLlama integration, SQLite models
- `frontend/` static HTML/CSS/JS dashboard with Chart.js (sparklines, share bar, component bar)
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
