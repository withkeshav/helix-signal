# Helix Signal — Deployment Runbook

> Living document for safe deploy + **post-deploy operator setup**.  
> Current release target: **v4.4.0** (platform Phases 1–8: public 24h, multi-webhook, scoped API keys, AI registry, timeline).  
> Companions: `SECURITY.md`, `docs/guides/ai-configuration.md`, `docs/guides/cross-tab-auth.md`.

## Prerequisites

- Docker + Compose plugin
- `.env` configured (copy from `.env.example`) — **`SESSION_SIGNING_KEY` must be set** (`openssl rand -hex 32`). Blank value = all admin logins return 503.
- **`SETTINGS_ENCRYPTION_KEY`** (recommended for production): Fernet key for secret settings at rest. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Without it, secrets store as plaintext (dev OK).
- **`RATE_LIMITER_STORAGE_URI`** defaults to `redis://redis:6379/0` in `docker-compose.yml` so multi-worker rate limits share state. Backend image must include the **`redis`** Python package (`backend/requirements.txt`) or startup fails with `ConfigurationError: 'redis' prerequisite not available`.
- **Alembic:** revision ids longer than 32 chars require `alembic_version.version_num` ≥ VARCHAR(64). Migration `v4_013` widens the column; if a deploy is stuck mid-upgrade with `StringDataRightTruncation`, run `ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64);` then restart backend. Head includes **`v4_017_platform_tables`** (webhook_endpoints, ai_providers, fred_yields, api_keys.access_policy).
- **Auth:** single seeded admin (`HELIX_ADMIN_USERNAME` / `HELIX_ADMIN_PASSWORD`). Sign in at Settings → Admin login. See `docs/guides/cross-tab-auth.md`.
- **Compose project name must stay `helix-signal`** so the volume stays `helix-signal_postgres_data`.
- Git checkout of target release (after push, `git pull origin main` on the server)

### Before first public internet exposure

Do these in `.env` / Control Room (see `SECURITY.md`):

| Setting | Recommendation |
|---------|----------------|
| `ai_require_token` | **true** — AI explain/narrative not anonymous |
| `api_auth_mode` | `key_required` for non-admin API consumers |
| `HELIX_COOKIE_SECURE` | `1` behind HTTPS |
| `SETTINGS_ENCRYPTION_KEY` | set (Fernet) |
| `TRUSTED_PROXY_CIDR` | Docker/proxy network only |
| Settings export/import | Export masks secrets; import **skips** mask sentinels (will not clobber live keys) |

---

## Deploy

```bash
# ALWAYS use the same project name (server volume: helix-signal_postgres_data)
export COMPOSE_PROJECT_NAME=helix-signal
cd /apps/helix-signal   # or your checkout path
git pull origin main
# preserve .env — do not rotate POSTGRES_PASSWORD casually
bash scripts/backup.sh || true

# Full rebuild when FE + BE both changed (v4.4.0-class releases)
docker compose -p helix-signal build --no-cache backend frontend   # optional but safer after large FE/BE delta
docker compose -p helix-signal up -d --build --remove-orphans

# Never:
# docker compose down -v   # wipes Postgres named volume
```

### Verify boot

```bash
docker volume ls | grep postgres   # expect helix-signal_postgres_data
docker compose -p helix-signal ps  # postgres, redis, backend, frontend healthy
curl -sf http://127.0.0.1:8000/api/health | python3 -m json.tool
# expect: status ok, db/redis true, scheduler_running true, version "4.4.0" (or current release)
curl -sfI http://127.0.0.1:3080/ 2>/dev/null || curl -sfI http://127.0.0.1/
docker compose -p helix-signal exec -T backend alembic current
# expect head including v4_016_web_search_snapshots after migrate
./scripts/smoke-check.sh http://127.0.0.1   # or your public base URL
```

Hard-refresh the browser (Ctrl+Shift+R) after frontend deploys so static JS is not stale.

SQLAdmin (Tier-2): `http://<host>/admin` with seeded admin — for rare table ops, not daily Control Room use.

---

## Post-deploy operator guide (v4.4.0)

Complete these **after** containers are healthy. Order matters for AI and web search.

### 0. Run migrations (v4.4.0+)

```bash
docker compose -p helix-signal exec backend alembic upgrade head
```

Expect head **`v4_017_platform_tables`**. SQLite dev uses `create_all`; Postgres/Timescale prod requires this step.

### 1. Admin login

1. Open the app → **Settings**.
2. **Admin login** with `HELIX_ADMIN_USERNAME` / `HELIX_ADMIN_PASSWORD` from `.env`.
3. Confirm nav shows authenticated state (not stuck “logged out” with a valid cookie).
4. Control Room sub-tabs: Overview, AI & Models, Data & Sources, Alerts, **Display & Access**, Security, Advanced.

See `docs/guides/cross-tab-auth.md` for single-admin session model.

### 2. Security posture (if exposed beyond trusted LAN)

In Control Room → **Security** (or Advanced):

1. Set **`api_auth_mode`** = `key_required` if third parties call intelligence APIs.
2. Set **`ai_require_token`** = **true** so AI routes need admin session / token.
3. Confirm `.env`: `HELIX_COOKIE_SECURE=1` (HTTPS), `TRUSTED_PROXY_CIDR` correct.
4. Create API keys if needed: Control Room Security or `POST /api/v1/api-keys` / SQLAdmin.

### 3. AI mode and provider keys

In Control Room → **AI & Models**:

1. Run **Quick Setup** (2 steps) or set playbook (Off / Lite / Full).
2. Set **`ai_mode`**: `ai_off` | `ai_lite` | `ai_full` (enum select).
3. **Rotate secrets** (paste new key only; leave blank/`configured` to keep existing):
   - `Ollama` — LLM (required for default models)
   - `OpenRouter` — fallback / stronger models
4. **Refresh model lists** → pick per-feature models (or type `provider:model_id` manually).
5. Confirm feature toggles: `feature_ai_explain`, `feature_ai_summary`, `feature_ai_narrative`, `feature_ai_insights`.
6. Open **Signal** → AI cards: structured `STATUS` + bullets, or deterministic fallback when AI off / failed.
7. Errors should surface under panels when HTTP fails (not silent forever).

Canonical guide: `docs/guides/ai-configuration.md`.

### 4. Optional web search (AI headline context)

**Opt-in only.** Ollama alone does **not** enable web search.

| Requirement | Detail |
|-------------|--------|
| Keys | Control Room secrets: **Tavily** and/or **Exa** |
| Mode | `ai_mode` is `ai_lite` or `ai_full` |
| Chain | Tavily → Exa → Ollama `web_search` (3rd fallback only) |
| Cadence | Cron **06:15 & 18:15 UTC** (`web-search-refresh`) |
| First fill | After keys are set, **restart backend once** so `web-search-startup-once` can run ~5 minutes later if cache empty/stale |
| AI path | Cached `WEB_CONTEXT` only — no live search on each AI click |
| Spend | Successful searches increment `SourceUsage` as `web_search_{provider}` |

Verify later:

```bash
docker compose -p helix-signal exec -T backend python -c "
from database import SessionLocal, WebSearchSnapshot
from services.web_search.job import web_search_feature_enabled
db=SessionLocal()
print('feature', web_search_feature_enabled(db))
print('rows', db.query(WebSearchSnapshot).count())
db.close()
"
```

### 5. On-chain / whale data (optional)

1. Advanced / secrets: **Moralis**, **Alchemy**, **The Graph**, **Flipside** as needed.
2. Enable **`feature_onchain_signals`** and **`provider_moralis`** (and related providers).
3. Whale rows persist to `whale_activity_snapshots` (not cache-only).  
   Note: series field `exchange_inflow_usd_24h` is **gross large-transfer volume** (historical name); alias `large_transfer_volume_usd_24h` may appear in series payloads.

### 6. Market forecasts

- Job **`forecast-refresh`** (cron ~5/11/17/23:20 UTC) + **startup-once ~3 min after boot**.
- Model id: `helix_linear_trend` (trend extrapolate from `asset_trend_snapshots` — not TimesFM).
- Market tab overlays use `forecast_points.peg` / `.supply`. Empty charts mean no history yet or job not run — not a permanent wrong overlay.
- Need core refresh history first (defillama-refresh) so trends exist for extrapolation.

### 7. Data & jobs sanity

| Job / area | Expectation |
|------------|-------------|
| Core refresh | ~`refresh_core_seconds` (default 300s) — strip KPIs fill |
| OSINT | Interval from `refresh_osint_minutes` |
| Fiat reserves | Daily ~05:00 UTC, best-effort |
| Insights | Daily deterministic rebuild ~04:30 — **no LLM** on that path |
| Retention | Nightly prune; web search snapshots default 30 days |
| Overview | Control Room Overview: scheduler, quality, last prune |

### 8. Display & Access (v4.4.0)

1. Control Room → **Display & Access**: confirm `public_history_hours` (default **24**).
2. Log out → confirm anonymous trends clamp to 24h; Forensics tab hidden unless `public_show_forensics`.
3. Log in → full history on same URL.

### 9. Webhooks & SMTP (v4.4.0)

1. Control Room → **Alerts** → add webhook endpoints (name, URL, signing secret, optional event filters).
2. Configure SMTP + `alert_email_event_types`; use **Send test email**.
3. See `docs/guides/alert-routing.md`.

### 10. Scoped API keys (v4.4.0)

1. Control Room → **Security** → create key with bundle checkboxes (default `core:read` only).
2. Optional asset list + max history hours.
3. See `docs/api/scopes.md`.

### 11. Tab smoke checklist (UI)

| Tab | Check |
|-----|--------|
| **Signal** | Hero score, strip, token cards switch asset **and** DEWS/AI follow same asset, AI cards, fundamentals |
| **Market** | Supply KPIs without visiting Signal first; forecast charts or honest empty state; contagion/rotation |
| **Intel** | OSINT, SMIDGE, on-chain cards when configured |
| **Forensics** | Blacklist stats; Cmd+K / investigate address works |
| **Alerts** | Active/filtered vs recent event stream labels make sense |
| **System** | Sources + quality; Admin ops if needed |
| **Settings** | Secrets rotate, enums for `ai_mode` / `api_auth_mode`, Advanced float keys (e.g. anomaly floor) |

### 12. Settings import / export

- **Export** includes secrets only as `"configured"`.
- **Import** **skips** secret keys when value is a mask sentinel — will not wipe live API keys.
- To change a key: Control Room **Rotate** with a real new value, or import an intentional plaintext secret.
- Import toast shows imported / skipped / errors.

### 13. Optional: force one-shot jobs after deploy

If you need cache/forecast sooner than cron:

```bash
# Web search (only if feature on — Tavily/Exa + ai_mode)
docker compose -p helix-signal exec -T backend python -c "
from database import SessionLocal
from services.web_search.job import run_web_search_job
db=SessionLocal(); print(run_web_search_job(db)); db.close()
"

# Forecasts
docker compose -p helix-signal exec -T backend python -c "
from database import SessionLocal
from services.forecast_writer import run_forecast_job
db=SessionLocal(); print(run_forecast_job(db)); db.close()
"
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
| v4.4.0 | local | 2026-07-20 | Platform Phases 1–8: public 24h, multi-webhook, scoped API keys, AI registry + 3-tier fallback, timeline, FRED Postgres |
| v4.3.0 | local `95c1d24`+ | 2026-07-20 | Re-arch, web search cache, Control Room polish, forecast writer, secret import/PUT safety, FE asset/overlay fixes |
| v4.2.0 | local | 2026-07-19 | Hypertables, event labels, scheduler hardening |
| v4.1.0 | local | 2026-07-19 | Control Room (6 sub-tabs), data-quality snapshots, insight assets API |
| v4.0.7 | local | 2026-07-19 | Global strip + signal hero, `.data-table` lists, Fernet settings encryption, security headers, OLAP amputate (fred_yields only) |
| v4.0.6 | local | 2026-07-19 | Frontend liveness (`refreshTick`), `GET /api/dashboard/summary`, settings-driven retention (11 tables), Timescale `drop_chunks` + compression |
| v4.0.5.1 | local | 2026-07-16 | AI provider simplification (Ollama Cloud + OpenRouter), per-feature `provider:model_id` settings, budget enforcement removed, error-logging hardening, APScheduler `max_instances=1` |
| v4.0.5 | local | 2026-07-16 | SQLAdmin `/admin`, secured intelligence API keys + tiers, Alpine settings shrink, FRED/ONNX DB-first |
| v4.0.4 | `d0a69ab` | 2026-07-10 | Settings wiring fix — DB priority over env, audit redaction, mask_secret, unified Settings UI, Signal refresh |
| v4.0.3 | `HEAD` | 2026-07-08 | FE lifecycle refactor — x-if tabs, single Market, auth dedupe, chart lifecycle, Settings wizard + AI mapping, bounded empty states |
| v4.0.2 | `c5427f5` | 2026-07-08 | Cookie session auth, alert rule editor, asset enable overrides, provider test, CI Postgres path, E2E expansion |
| v4.0.1 | `cabb85a` | 2026-07-08 | Audit rectification — auth, hardening, reliability, SA 2.0, docs, tests |
| v4.0.0 | `cabb85a` | 2026-07-05 | Current prod HEAD — 24-coin taxonomy, ONNX models, forensics, investigation |
| v3.10.3 | `0496bea` | 2026-06-25 | Bugfix audit completed |
| v3.10.2 | `c56df3b` | 2026-06-24 | UI/UX redesign rollout |
| v3.10.1 | `6757a71` | 2026-06-24 | Bugfix audit pass (auth, security, perf) |

---

*Last updated: 2026-07-20 (v4.4.0 post-deploy operator guide)*
