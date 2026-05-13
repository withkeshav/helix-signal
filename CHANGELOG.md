# Changelog

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
- Extended `.gitignore` for V2.3 internal brief filenames

### Out of scope (unchanged)

- Moralis, paid APIs, alerts, auth, database engine migration, plugins, GraphQL, frontend framework migration

## v2.2.1 - Display quality and freshness hotfix

### Fixed
- Hid the TVL column to avoid presenting unsupported per-asset, per-chain liquidity values as meaningful data.
- Corrected freshness behavior to use consistent latest successful fetch timing with readable Fresh, Aging, and Stale labels.
- Updated asset selector labels to clean format such as `USDT (Tether USD)`.

### Improved
- Removed em dashes from public UI copy and documentation.
- Cleaned wording in public-facing files for release hygiene.
- Updated `.gitignore` with exact internal brief filenames present in the project root.

## v2.2.0 - Controlled Multi-Stablecoin Activation

### Added
- Enabled controlled multi-stablecoin dashboard support through `config/assets.json`.
- Added frontend asset selector for switching between supported stablecoins.
- Added asset-aware dashboard loading through `/api/dashboard?asset=SYMBOL`.

### Changed
- Extended the refresh pipeline to process all enabled stablecoin assets.
- Updated dashboard labels and table headings to reflect the selected asset.
- Updated documentation for multi-asset configuration and methodology.

### Preserved
- USDT remains the default dashboard asset.
- DefiLlama public stablecoin endpoints remain the default keyless data source.
- SQLite remains the local cache.
- V2.0 theme, manual refresh, freshness, and source-health UX remain intact.

### Out of Scope
- Moralis integration.
- Alerts, webhooks, and notifications.
- Authentication.
- Paid DefiLlama Pro API dependency.

## v2.1.0 - Multi-Asset Data Model Foundation

- Added a generic asset-chain snapshot model as the new multi-asset-ready foundation.
- Added `config/assets.json` with USDT enabled/default and USDC, DAI, PYUSD disabled.
- Added optional `asset` query support to `/api/dashboard`.
- Added `/api/assets`.
- Preserved DefiLlama public stablecoin endpoints as the default source.
- Preserved V2.0 theme, refresh, freshness, and source-health UX behavior.
- Confirmed Moralis, alerts, auth, paid DefiLlama Pro, and DB engine migration are out of scope.
