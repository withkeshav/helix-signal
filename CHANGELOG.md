# Changelog

## v2.5.0 - Trust the terminal

### Added

- **CI**: GitHub Actions workflow runs import smoke and pytest from `backend/.venv` pattern in CI (venv created in workflow).
- **Tests**: `backend/tests/` with pytest for scoring, history bucketing, and API smoke (in-memory SQLite).
- **Health**: `GET /api/health` with `status`, `db`, `last_successful_fetch`, `scheduler_running`, and `version` `2.5.0`.
- **Retention**: Daily job prunes trend rows (`TREND_RETENTION_DAYS`, default 90) and events (`EVENT_RETENTION_DAYS`, default 30).
- **Deploy**: Compose uses `.env`; frontend nginx proxies `/api` to backend; dashboard uses same-origin relative API paths.
- **Exports**: `GET /api/trends/export` and `GET /api/events/export` (CSV or JSON, max 10k rows) plus UI export buttons.
- **Compare**: `GET /api/compare?assets=USDT,USDC&window=7d` and dashboard multi-line chart.
- **Chain drill-down**: `GET /api/chains/{chain_key}?asset=USDT` and clickable chain rows with side panel.
- **Optional backfill**: `POST /api/admin/backfill` when `ALLOW_BACKFILL=true` (7–30 days, synthetic labeled rows).
- **Refactor**: Dashboard assembly moved to `backend/services/dashboard.py`.

### Fixed

- Duplicate `isinstance(rows, list)` guard in `sources/defillama.py`.
- Documented `DEFILLAMA_API_KEY` as reserved (free DefiLlama endpoints used).

### Documentation

- Updated README, architecture, methodology, CONTRIBUTING, and RELEASE_NOTES for V2.5.
- `.gitignore` patterns for V2.5 internal execution brief filenames.

### Out of scope (unchanged)

- External alerts, webhooks, paid APIs, Moralis, auth, Postgres or dedicated time-series stores, framework migrations, plugins, GraphQL, hosted cloud tiers.

## v2.4.0 - Historical Trends and Signal Feed

### Added

- Historical trend snapshot storage for asset-level and chain-level monitoring (5-minute UTC buckets, SQLite).
- Trend APIs: `GET /api/trends`, `GET /api/trends/chains` with `window` in `24h`, `7d`, or `30d`.
- Signal event feed stored locally with deduplication, plus `GET /api/events` (optional `asset` filter).
- Dashboard trend charts for signal score, Depeg Index, total supply, and concentration score, plus a compact event feed panel with low-data messaging.
- Shared metric bundle helper in `signal_engine/metrics.py` for consistent snapshot values.

### Documentation

- Updated `README.md`, `docs/data-methodology.md`, `docs/architecture.md`, `CONTRIBUTING.md`, and `RELEASE_NOTES.md` for V2.4.
- Extended `.gitignore` for the V2.4 internal brief filename.

### Out of scope (unchanged)

- External alerts, webhooks, paid APIs, Moralis, auth, Postgres or dedicated time-series stores, framework migrations, plugins, GraphQL, hosted cloud tiers, long historical backfill.

## v2.3.0 - Helix Signal Score and monitoring dashboard

### Added

- **Helix Signal Score**: transparent 0 to 100 composite with Normal, Watch, and Risk bands; explicit 35% / 25% / 20% / 20% component weights returned in `/api/dashboard`
- **Depeg Index** and **chain concentration** (HHI and top share) in the dashboard API and UI
- **Derived metrics**: aggregate total supply, aggregate 24h supply change, per-chain supply momentum labels, chain share, per-chain signal and data confidence
- **Server-side `freshness` object** in `/api/dashboard` using UTC basis `max(last_successful_fetch, newest_chain_snapshot)` and refresh-interval-derived windows
- **Chain TVL** restored as optional **chain-level aggregate** context from DefiLlama `stablecoinchains`, with clear labeling in API and UI (not per-asset TVL)
- Premium-style dashboard layout: KPI strip, methodology and insight panels, Chart.js share and component charts, expanded chain table

### Fixed

- Freshness and source timing inconsistencies by computing freshness on the server and consuming it in the frontend (avoids client-only max timestamp mistakes)
- Refresh pipeline now tracks **maximum** successful per-asset fetch time when updating `last_successful_fetch` so multi-asset passes do not appear artificially stale

### Documentation

- Updated `README.md`, `docs/data-methodology.md`, `docs/architecture.md` for V2.3
