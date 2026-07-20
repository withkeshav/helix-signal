# Contributing to Helix-Signal

Thanks for helping improve Helix-Signal.

## Local Setup (Docker)

### 1) Clone

```bash
git clone https://github.com/withkeshav/helix-signal.git
cd helix-signal
```

### Demo / seed mode

After `docker compose up`, sign in at **Settings** with `HELIX_ADMIN_USERNAME` / `HELIX_ADMIN_PASSWORD` from `.env`. The backend seeds a single admin on first boot (`scripts/seed_admin.py`). Tabs populate once the 300s refresh cycle runs (or trigger **Refresh** on Signal). For a quick local smoke test without secrets, copy `.env.example` and set only `POSTGRES_PASSWORD`, `SESSION_SIGNING_KEY`, and `HELIX_ADMIN_PASSWORD`.

### 2) Configure environment

Create your local env file (or export equivalent vars):

- `SESSION_SIGNING_KEY` (**required** - generate via `openssl rand -hex 32`)
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
export PYTHONPATH=..
python main.py
```

Or:

```bash
export PYTHONPATH=..
uvicorn main:app --reload
```

### 3c) Local backend setup with Python `venv`

Install dependencies **only** into `backend/.venv`:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
export PYTHONPATH=..
.venv/bin/python main.py
```

Or:

```bash
export PYTHONPATH=..
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
- Keep frontend dependency-light (Alpine.js + `app.js` + ECharts; no build step)
- Follow existing naming patterns and file organization

## Local-only notes (do not commit)

- Handoff / phase status: `.progress/PHASE_LOG.md` (gitignored)
- Planning, briefs, research: anything matching `.gitignore` internal patterns
- **Core** features (scoring, ingest, trends, alerts) must work with AI disabled; LLM providers are optional add-ons only

## API Versioning

- All new endpoints go under `/api/v1/` with Pydantic response models
- Existing `/api/` endpoints remain stable; deprecate via doc comment before removal
- Legacy `db.query()` style is **being migrated** to SA 2.0 `select()` + `execute()` - new code must use SA 2.0 style

## Pull Request Expectations

- Explain what changed and why
- Include manual verification steps
- Run `cd backend && .venv/bin/pytest -q` before opening a PR
- For deploy-related UI/API changes, run `./scripts/smoke-check.sh https://your-host` when applicable
- Confirm no secrets were added (`.env`, `secrets/`, internal briefs)
- Keep docs in sync when behavior or thresholds change
- Do not commit internal or local docs (`.progress/`, briefs, phase logs - see `.gitignore`)

## CI / GitHub Actions Requirements

The `smoke` job spins up the full Docker Compose stack,
which requires certain environment variables. These must be set as
**repository secrets** in GitHub Settings → Secrets and Variables → Actions.

### Required Repository Secrets

| Secret | Purpose | Example CI value |
|---|---|---|
| `POSTGRES_PASSWORD` | Required by docker-compose.yml (`:?` strict) | Any non-empty string e.g. `smoketest-ci` |
| `DEPLOY_HOST` | SSH deploy target hostname | Your server IP or domain |
| `DEPLOY_USER` | SSH deploy username | `deploy` or `ubuntu` |
| `DEPLOY_SSH_KEY` | Private key for SSH deploy step | PEM-format private key |

> **Note for fork contributors:** The `smoke` job will show as red on fork PRs
> because secrets are not passed to forks by default. This is expected GitHub
> behaviour. The `test` job (unit tests, lint, security scan) will still run
> and is the relevant signal for code review.

`AI_MODE=ai_off` and `HELIX_SKIP_STARTUP_REFRESH=1` are injected automatically
by the CI workflow - you do not need to set these as secrets.
