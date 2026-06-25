# Helix Signal Changelog

## v3.10.3 (2026-06-25)

- **Fix: Postgres playbook seed crash** — `_seed_builtin_playbooks` used `is_builtin = 1`, which fails on PostgreSQL BOOLEAN (`operator does not exist: boolean = integer`), causing uvicorn STARTUP_FAILURE (exit 3) during lifespan startup after alembic. Replaced with ORM `Playbook.is_builtin.is_(True)` filter, safe on both SQLite and Postgres.
- **Fix: Fail-loud lifespan** — Wrapped `lifespan()` startup in `try`/`except` that logs `lifespan.startup_failed` with full traceback to stderr before re-raising. Future startup crashes are visible even without container log capture.
- **Fix: Re-export `_within_budget`** — Added `_within_budget` to `ai_router.py` imports for `osint.py` and `sentiment.py` consumers.
- **Fix: CSP + nginx perf** — Re-added `unsafe-eval` to nginx CSP (unblocks Alpine.js), enabled gzip compression, added 7d immutable cache for static assets.
- **Fix: Redis persistence** — Added RDB snapshots + AOF to Redis config.
- **Fix: Chart.js removal** — Dropped Chart.js CDN (-250KB), rewrote charts.js to ECharts-only.
- **Fix: OSINT timeouts** — Added per-source 15s timeouts to RSS fetches and 20s timeout to Twitter GraphQL calls.
- **Fix: Audit follow-up** — Fixed `_makeBar`/`_renderForecastCanvas` exports (runtime import error), moved ECharts instances to `_echarts` map, replaced `immutable` cache with `no-cache` on non-hashed assets, added HSTS to static assets location, removed redundant `--save 3600 1` from Redis, added dependabot npm tracking for CDN deps.
- Rollback anchor: `c1e38bf`

## v3.10.2 (2026-06-24)

- Fix cache.py SyntaxError from indented try/except mismatch
- Re-release after Cursor re-verify

## v3.10.1 (2026-06-24)

Bugfix audit pass — 8 groups of fixes across auth, security, reliability, performance, and code quality.

### Group 1 — Auth
- Fix ghost identity in token parsing (A-3)
- Fix user list crash on null `email`/`login_enabled` (B-2)

### Group 2 — Security
- SSRF protection for webhook URLs via private IP check (A-2)
- Require admin auth on `/sources/status`, `/sources/usage`, `/sources/{name}/config` (F-1)
- Narrow CORS from wildcard `*` to explicit methods/headers (A-1)
- Remove `unsafe-eval` from CSP (A-8)

### Group 3 — Auth hardening
- Fix null user crash in audit log entries (B-1)
- Add `X-Frame-Options: DENY` to all responses (A-7)

### Group 4 — Reliability
- Fix `AttributeError` in `_attach_daily_latest` when datetime is unset (F-4)
- Atomic import lock via `INSERT ... WHERE NOT EXISTS` (F-5)
- Guard background tasks behind startup flags (C-1 + F-6)

### Group 5 — Performance
- Bulk DB queries for settings page load (D-2)
- Bulk freshness query for asset cache (D-3)

### Group 6 — Information disclosure
- Remove `platform.node()` from diagnostics (A-6)
- Sanitize error responses: strip internals from 500s (F-2)

### Group 7 — Performance
- Replace nested z-score loop with generator expression (D-1)

### Group 8 — Code quality
- Remove ~100 unused imports across backend (E-1)
- Replace all bare `except Exception: pass` with `logger.debug/warning` + `exc_info=True` (E-2)

## v3.10.0 (2026-05-28)

- Auth+API+DB hardening
- Signed session tokens
- SMIDGE join fix
- 500 crash hardening
- osint_article indexes
- Frontend ReferenceError/resize/audit-poll fixes
- Dockerignore cleanup
