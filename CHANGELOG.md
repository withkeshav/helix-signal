# Changelog

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
