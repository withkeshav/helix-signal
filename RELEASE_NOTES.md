# Release Notes

## v2.3.0 - Helix Signal Score

Helix-Signal v2.3 adds a transparent **Helix Signal Score**, **Depeg Index**, derived aggregate metrics, **server-side freshness**, and a richer monitoring-style dashboard while keeping the same stack (FastAPI, SQLite, Vanilla JS + Chart.js).

### Highlights

- Dashboard API exposes scoring components with documented weights
- Optional **Chain TVL** column labeled as chain-level aggregate context from DefiLlama `stablecoinchains`
- KPI strip, methodology panel, and Chart.js visualizations for share and subscores

See `CHANGELOG.md` for the full list of changes and fixes.

## v1.0.0 - Initial Release

Helix-Signal v1.0.0 introduces the first public version of Helix: a self-hostable USDT chain signal dashboard powered by FastAPI, SQLite, and a static Vanilla JS + Chart.js frontend.

### Highlights

- Backend data engine with scheduled DefiLlama refresh and graceful failure handling
- SQLite-backed cache for chain metrics and source health
- Dashboard API payload (`/api/dashboard`) for frontend consumption
- Frontend terminal-style dashboard with:
  - USDT supply and 24h delta
  - Peg status classification
  - TVL context
  - Chain trend sparklines
  - Source health footer
- Core documentation suite for architecture, methodology, contributing, and security reporting

### Scope

This release focuses on a stable V1 baseline for USDT monitoring across configured top chains, with transparent methodology and local reproducibility via Docker Compose.
