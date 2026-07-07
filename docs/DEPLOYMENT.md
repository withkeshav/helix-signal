# Helix Signal — Deployment Runbook

> Tracked items: deploy profiles, cache-busting, CSP drift, CI gaps, config hazards.
> This is a living document — update when deployment constraints change.

## Prerequisites

- Docker + Compose plugin
- `.env` configured (copy from `.env.example`) — **`SESSION_SIGNING_KEY` must be set** (`openssl rand -hex 32`). Blank value = all admin logins return 503.
- Git checkout of target release

## Deploy

```bash
git pull origin main
docker compose up -d --build
```

Verify:

```bash
docker ps --filter name=helix
curl -sf http://localhost/api/health | python3 -m json.tool
```

---

## Tracked Items

### 1. Dual `--no-cache` rebuild on large changes

When both backend and frontend change significantly (e.g. UI redesign, model changes), rebuild without cache:

```bash
docker compose build --no-cache backend frontend
docker compose up -d
```

### 3. nginx static-JS cache-bust

`frontend/nginx.conf` sets `max-age=0` on HTML but does not version static JS bundles. After a frontend deploy, users may load stale JS from browser cache.

**Workaround:** Hard-refresh (Ctrl+Shift+R) or increment a query-string param in `index.html`.

**Fix-tracked:** Versioned JS filenames in build pipeline.

### 4. CSP drift: backend middleware vs nginx

CSP headers are set in **two places**:
- `backend/config/middleware.py` (default CSP)
- `frontend/nginx.conf` (nginx-level CSP)

These can drift — if the backend middleware is updated, nginx.conf must be updated in sync.

**Verify:** Check both files for matching CSP directives before deploy.

### 5. CI does not exercise Postgres `init_db()` seed path

The CI unit test suite runs against SQLite. The `init_db()` playbook seed path against a real PostgreSQL is never exercised in CI.

**Risk:** A regression in the ORM seed logic (like the `boolean = integer` bug) will not be caught in CI. Only a full Docker Compose smoke test with a real Postgres container catches it.

**Fix-tracked:** Add a CI job that starts Postgres via service container and runs `init_db()` against it.

### 6. `docker-compose.override.yml` — reload hazard

A gitignored `docker-compose.override.yml` in the project root can override the backend `command`, e.g. injecting `--reload` or changing `--app-dir`. This:
- Suppresses `Application startup complete.` in logs (reloader worker)
- Can mask startup failures
- Can introduce port/volume conflicts

**Action:** Check for `docker-compose.override.yml` before deploying. Remove or rename it if it would interfere with production behavior.

```bash
test -f docker-compose.override.yml && echo "WARNING: override file present"
```

### 7. `_should_use_alembic()` forces alembic on Postgres

In `backend/database.py`, `_should_use_alembic()` returns `True` for **any** `postgresql://` URL, even when `HELIX_USE_ALEMBIC=false`:

```python
def _should_use_alembic() -> bool:
    explicit = os.getenv("HELIX_USE_ALEMBIC", "").strip().lower() in ("1", "true", "yes")
    return explicit or DATABASE_URL.startswith("postgresql")
```

This couples startup to migration availability (e.g. TimescaleDB extension). Set `DATABASE_URL` to a non-Postgres value if you need to bypass alembic with a Postgres backing store.

**Fix-tracked:** Pre-existing, not introduced by any current fix. Flagged for follow-up.

### 8. CI-tracked artifacts

The heuristic `.onnx` model stubs (`backend/ml_models/*_heuristic.onnx`) and curated depeg event labels (`data/depeg_events.json`) are tracked in git via `.gitignore` negations so the CI `test` job runs deterministically without a generation step. These files are small (1–2 KB each) and updated only during model version bumps.

If you see CI failures in `test_dews.py` or `test_ml_models.py`, verify these files exist and are not gitignored:

```bash
git check-ignore -v data/depeg_events.json              # should NOT be ignored
git check-ignore -v backend/ml_models/*_heuristic.onnx   # should NOT be ignored
```

### 9. Proxy-aware rate limiting

The rate limiter reads `X-Forwarded-For` to identify clients behind nginx. By default, any client can set this header to bypass per-IP limits. Set `TRUSTED_PROXY_CIDR` in `.env` (e.g. `TRUSTED_PROXY_CIDR=10.0.0.0/8`) to restrict XFF trust to your Docker network. Clients outside this CIDR are identified by their direct connection IP.

See `SECURITY.md` §X-Forwarded-For Trust for details.

---

## Incident Response

### Backend crash-loop (exit code 3)

If the backend container restarts repeatedly with exit code 3 (uvicorn's `STARTUP_FAILURE`):

1. Check logs: `docker compose logs backend`
2. Look for `lifespan.startup_failed` — if present, the fail-loud wrapper captured the exception
3. If no `lifespan.startup_failed`, the crash is before the wrapper (e.g. import error)
4. Common causes:
   - `init_db()` failure (alembic migration issue, DB unreachable)
   - Playbook seed SQL incompatibility (Postgres BOOLEAN operator)
   - Missing env vars
5. Rollback: `git reset --hard <rollback-anchor>` then rebuild

### Rollback anchor

Each release documents its rollback anchor (a known-good commit SHA). To roll back:

```bash
git reset --hard <anchor-sha>
docker compose up -d --build
```

---

## Version History

| Tag | SHA | Date | Notes |
|-----|-----|------|-------|
| v4.0.0 | `HEAD` | 2026-07-05 | Current prod HEAD — 24-coin taxonomy, ONNX models, forensics, investigation |
| v3.10.3 | `0496bea` | 2026-06-25 | Bugfix audit completed |
| v3.10.2 | `c56df3b` | 2026-06-24 | UI/UX redesign rollout |
| v3.10.1 | `6757a71` | 2026-06-24 | Bugfix audit pass (auth, security, perf) |

---

*Last updated: 2026-07-05*
