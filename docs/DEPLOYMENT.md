# Helix Signal — Deployment Runbook

> Tracked items: deploy profiles, cache-busting, CSP drift, CI gaps, config hazards.
> This is a living document — update when deployment constraints change.

## Prerequisites

- Docker + Compose plugin
- `.env` configured (copy from `.env.example`)
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

### 1. Profile: `data` services

`scripts/deploy.sh` does **not** pass `--profile data` by default. If the compose file profiles the `postgres`/`redis` services behind `data`, they will **not** start without the flag.

**Action:** Either:
- Add `COMPOSE_PROFILES=data` to prod `.env`
- Or pass `--profile data` to every `docker compose up` invocation

### 2. Dual `--no-cache` rebuild on large changes

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
| v3.10.2 | `3a37921` | 2026-06-24 | Pre-fix prod HEAD |
| f6f1d40 | `f6f1d40` | 2026-06-25 | Playbook seed fix + fail-loud lifespan (not yet in prod) |

---

*Last updated: 2026-06-25*
