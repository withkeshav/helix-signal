# Contributing to Helix-Signal

Thanks for helping improve Helix-Signal.

## Local Setup (Docker)

### 1) Clone

```bash
git clone https://github.com/withkeshav/helix-signal.git
cd helix-signal
```

### 2) Configure environment

Create your local env file (or export equivalent vars):

- `DEFILLAMA_API_KEY` (optional)
- `DATABASE_URL` (default works for local)
- `REFRESH_INTERVAL_SECONDS` (default `300`)

Reference: `.env.example`

### 3) Start services

```bash
docker compose up --build
```

### 3b) Run backend directly (without Docker)

From `backend/`:

```bash
python main.py
```

Or:

```bash
uvicorn main:app --reload
```

### 3c) Local backend setup with Python `venv`

Install dependencies **only** into `backend/.venv`:

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

### 3d) Run tests

From `backend/`:

```bash
.venv/bin/pytest -q
```

CI runs the same checks (import smoke + pytest) on push and pull requests. Set `HELIX_SKIP_STARTUP_REFRESH=1` is applied automatically in tests to avoid network ingest during pytest.

### 4) Verify

- API root: `http://localhost:8000`
- Health: `http://localhost:8000/api/health`
- Dashboard payload: `http://localhost:8000/api/dashboard`
- Trends: `http://localhost:8000/api/trends?asset=USDT&window=7d` and `http://localhost:8000/api/trends/chains?asset=USDT&window=7d`
- Events: `http://localhost:8000/api/events?asset=USDT&limit=50` (omit `asset` for cross-asset feed)
- Frontend: `http://localhost:3000`

## Trends, windows, and events (V2.4)

When changing behavior:

- **Windows** are validated server-side (`24h`, `7d`, `30d`). Invalid values return HTTP 400 with a clear message.
- **Trend buckets** are fixed at five minutes in UTC. If you change bucketing, update both `signal_engine/history.py` and methodology docs together.
- **Event thresholds** live in `signal_engine/history.py` (depeg zones, supply percent moves, concentration deltas, dedup window). Tune carefully to avoid noisy feeds.
- **New event types** should stay local (SQLite only), include human-readable `title` and `summary`, and respect deduplication rules.

## Adding a New Chain

Edit `config/chains.json` and add an object:

```json
{
  "name": "ExampleChain",
  "defillama_id": "ExampleChain"
}
```

Guidelines:

- `name` should be human-readable for UI display
- `defillama_id` must match the chain key expected from DefiLlama `chainCirculating`
- Keep entries unique and intentionally ordered

After updating config, restart backend (or full compose stack) and confirm the new chain appears in `/api/dashboard`.

## Adding a New Stablecoin Asset (V2.1-ready)

Edit `config/assets.json` and add or modify an asset entry:

```json
{
  "symbol": "USDC",
  "name": "USD Coin",
  "defillama_symbol": "USDC",
  "peg_type": "peggedUSD",
  "enabled": false,
  "default": false
}
```

Guidelines:

- Keep new assets `enabled: false` until parser + UI behavior is verified.
- Ensure `defillama_symbol` matches DefiLlama stablecoin symbol metadata.
- Keep exactly one default asset (`default: true`) for predictable `/api/dashboard` behavior.
- For production-facing activation, only set `enabled: true` after validating:
  - parser extraction from DefiLlama `chainCirculating`
  - `/api/dashboard?asset=SYMBOL` returns valid chains
  - frontend selector can switch and render without regression
- Validate with:
  - `/api/dashboard` (default asset)
  - `/api/dashboard?asset=USDT` (explicit default)
  - `/api/assets` (enabled assets list)

## Code Style

- Keep changes focused and small
- Prefer explicit, readable logic over clever abstractions
- Preserve graceful error handling in source fetchers
- Keep frontend dependency-light (Alpine.js + `app.js` + Chart.js; no build step)
- Follow existing naming patterns and file organization

## Pull Request Expectations

- Explain what changed and why
- Include manual verification steps
- Run `cd backend && .venv/bin/pytest -q` before opening a PR
- For deploy-related UI/API changes, run `./scripts/smoke-check.sh https://your-host` when applicable
- Confirm no secrets were added (`.env`, `secrets/`, `acme.json`, internal briefs)
- Keep docs in sync when behavior or thresholds change
- Do not commit internal execution briefs (see `.gitignore` patterns)
