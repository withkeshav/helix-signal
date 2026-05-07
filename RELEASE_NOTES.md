# Release Notes

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
