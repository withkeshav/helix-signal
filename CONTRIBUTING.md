# Contributing to Helix-Signal

Thanks for helping improve Helix-Signal.

## Local Setup (Docker)

### 1) Clone

```bash
git clone <your-fork-or-repo-url>
cd Helix-Signal
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

From `backend/`:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .\.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

You can also use:

```bash
uvicorn main:app --reload
```

### 4) Verify

- API root: `http://localhost:8000`
- Dashboard payload: `http://localhost:8000/api/dashboard`
- Frontend: `http://localhost:3000`

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
- Keep frontend dependency-light (Vanilla JS + Chart.js)
- Follow existing naming patterns and file organization

## Pull Request Expectations

- Explain what changed and why
- Include manual verification steps
- Confirm no secrets were added
- Keep docs in sync when behavior or thresholds change
