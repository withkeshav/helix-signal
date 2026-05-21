# Release Notes

## Unreleased — Production fixes

Follow-up fixes on top of v3.1.0 for the public demo deployment. No version bump.

### Highlights

- **Dashboard restored**: Alpine.js terminal shell and external `app.js` load correctly; trend chart and tab navigation work again
- **Data pipeline stabilized**: DefiLlama refresh no longer crashes on missing `timezone` import; trend buckets populate after refresh
- **Attestation clarity**: UI and API now show **issuer report age** separately from **DefiLlama supply feed freshness** — unknown stays unknown when issuer dates cannot be parsed
- **Deploy guardrails**: smoke-check script, Traefik basic-auth middleware file, nginx blocks public `/metrics`, `acme.json` excluded from git

See `CHANGELOG.md` for the full list.

## v3.1.0 — Maintenance & Quality

Helix-Signal v3.1.0 is a maintenance release fixing critical bugs, eliminating technical debt, and improving code quality.

### Highlights

- **Fixed anomaly.py crash**: numpy/pandas now imported at module level (was causing NameError in production)
- **DB session refactor**: Replaced 20+ `try/finally` blocks with FastAPI `Depends(get_db)` dependency injection
- **Alert evaluator rewrite**: Replaced fragile `in` string-matching with a callable registry using `@_register_condition` decorator
- **HTTP client migration**: All network calls migrated from `requests` to `httpx` across 6 source/service files
- **Alembic migrations**: Initialized automated migration system (`alembic upgrade head`)
- **Restored missing functions**: `osint.py` had 3 referenced but undefined functions (`_fetch_rss`, `_fetch_cryptopanic`, `_classify_asset`)
- **Cleanup**: 5 stale execution briefs deleted; dead `frontend/main.js` gitignored

See `CHANGELOG.md` for the full list of changes.

## v2.5.0 - Trust the terminal

Helix-Signal v2.5 focuses on **operational maturity** and **analyst ergonomics** on top of the V2.4 trend and event memory layer.

### Highlights

- GitHub Actions CI and pytest (`backend/.venv` locally; venv in CI workflow)
- `GET /api/health` for deploy and uptime checks
- SQLite retention job and Compose/nginx deploy fixes
- Trend and event CSV/JSON export, cross-asset compare, chain drill-down
- Optional env-gated backfill for synthetic daily seed points

See `CHANGELOG.md` for the full list.

## v2.4.0 - Historical Trends and Signal Feed

Helix-Signal v2.4 adds **forward-collected historical trends**, **REST trend endpoints**, and a **local signal event feed** while keeping the V2.3 stack (FastAPI, SQLite, Vanilla JS + Chart.js) and the Helix Signal Score, Depeg Index, server freshness model, manual refresh endpoint, and labeled chain aggregate TVL behavior.

### Highlights

- Trend charts on the dashboard with 24h, 7d, and 30d windows and explicit low-data states for new installs
- SQLite-backed `asset_trend_snapshots`, `chain_trend_snapshots`, and `signal_events` tables
- `/api/trends`, `/api/trends/chains`, and `/api/events` for programmatic access

See `CHANGELOG.md` for the full list of changes.

## v2.3.0 - Helix Signal Score

Helix-Signal v2.3 adds a transparent **Helix Signal Score**, **Depeg Index**, derived aggregate metrics, **server-side freshness**, and a richer monitoring-style dashboard while keeping the same stack (FastAPI, SQLite, Vanilla JS + Chart.js).

### Highlights

- Dashboard API exposes scoring components with documented weights
- Optional **Chain TVL** column labeled as chain-level aggregate context from DefiLlama `stablecoinchains`
- KPI strip, methodology panel, and Chart.js visualizations for share and subscores

See `CHANGELOG.md` for the full list of changes and fixes.

## v1.0.0 - Initial Release

Helix-Signal v1.0.0 introduces the first public version of Helix: a self-hostable USDT chain signal dashboard powered by FastAPI, SQLite, and a static Vanilla JS + Chart.js frontend.
