# API Reference

Base path: `/api` (proxied through nginx in Docker; same-origin from frontend)

> **API Versioning Note:** Most routes live at `/api/*` with no version prefix. The V4 intelligence/forensics endpoints (`investigate`, `yield`, `collateral`, `reserve`, `blacklist`, `tags`) use `/api/v1/*`. A future dedicated versioning pass will standardize all routes under `/api/v1`. See `.opencode/AGENTS.md` decision history for context.

## Intelligence API (v4.1.0+)

Self-host first; optional API keys for other apps.

### Auth modes (`api_auth_mode` setting / `API_AUTH_MODE` env)

| Mode | Read routes (dashboard, trends, OSINT, …) | Keyed-always (investigate, alerts, blacklist, tag writes) |
|------|-------------------------------------------|-----------------------------------------------------------|
| `open` (default) | Anonymous OK | API key **or** admin session |
| `key_required` | API key **or** admin session | API key **or** admin session |

Public always: `GET /api/health`, `GET /api/version`.

### Create a key (admin session / legacy token)

```bash
curl -s -X POST http://localhost/api/v1/api-keys \
  -H "X-Admin-Token: $HELIX_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"my-app","scopes":["intelligence:read","investigate:write"],"rate_limit_rpm":60}'
```

Raw `api_key` is returned **once**. Store it securely.

### Call intelligence routes

```bash
# Bearer
curl -s http://localhost/api/dashboard?asset=USDT -H "Authorization: Bearer hx_..."

# Or header
curl -s http://localhost/api/dashboard?asset=USDT -H "X-API-Key: hx_..."
```

Scopes / bundles: see **[docs/api/scopes.md](api/scopes.md)**. Defaults for new keys: `core:read` only. Legacy `intelligence:read` expands to all read bundles. Optional `access_policy` clamps assets and history hours.

### Call intelligence routes

```bash
# Bearer
curl -s http://localhost/api/dashboard?asset=USDT -H "Authorization: Bearer hx_..."

# Or header
curl -s http://localhost/api/dashboard?asset=USDT -H "X-API-Key: hx_..."
```

Manage keys in Control Room → Security or `GET/DELETE /api/v1/api-keys`.

### Public lite API (anonymous, clamped)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/public/config` | Non-secret Display & Access policy |
| GET | `/api/public/dashboard` | Lite dashboard |
| GET | `/api/public/trends?asset=&window=` | Window clamped to `public_history_hours` (default 24) |
| GET | `/api/public/osint/headlines` | Limited headlines |
| GET | `/api/public/timeline?asset=` | Lite strip (band + recent items) |

Admin session uses full `/api/*` routes (unclamped).

### Webhooks & SMTP

| Method | Path | Notes |
|--------|------|-------|
| GET/POST | `/api/v1/webhook-endpoints` | Multi-endpoint CRUD |
| PUT/DELETE | `/api/v1/webhook-endpoints/{id}` | Update / delete |
| POST | `/api/v1/webhook-endpoints/{id}/test` | Signed test POST |
| GET | `/api/v1/alert-event-catalog` | Event category checkboxes |
| POST | `/api/v1/alerts/test-email` | SMTP test |

See `docs/guides/alert-routing.md`.

### AI providers & health

| Method | Path | Notes |
|--------|------|-------|
| GET/POST | `/api/v1/ai-providers` | Registry CRUD |
| PUT/DELETE | `/api/v1/ai-providers/{id}` | Update / delete |
| POST | `/api/v1/ai-providers/{id}/test` | Connection test |
| GET | `/api/settings/ai-health` | Provider + usage card |
| GET | `/api/settings/web-search-status` | Cache / last run |
| POST | `/api/settings/web-search/run` | Manual job |

### Timeline

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/timeline?asset=&from=&to=` | Merged scores/events/OSINT/web/FRED; needs `events:read`+`osint:read` (or legacy read) |

### Operator Admin Panel

Browser UI: `/admin` (SQLAdmin). Requires an admin user login (same seeded account as Settings). nginx must proxy with `location ^~ /admin`.

### On-chain / whale (when enabled)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/onchain/whale-flow?asset=` | Mint/burn + large transfers (The Graph / Moralis / Flipside) |
| GET | `/api/onchain/holder-concentration?asset=` | Requires Moralis |
| GET | `/api/v1/series/whale?asset=&days=` | History from **`whale_activity_snapshots`** (persisted on Moralis refresh) |

Enable `feature_onchain_signals` + `provider_moralis` and set `secret_moralis_api_key` in Control Room.

### Operator login (single-admin product model)

Helix is **single-operator** by default: one seeded admin (`HELIX_ADMIN_USERNAME` / `HELIX_ADMIN_PASSWORD`). No self-service multi-user.

| Method | Path | Notes |
|--------|------|--------|
| POST | `/api/auth/login` | Form body `username` + `password`. Returns `access_token` + sets httpOnly `helix_session` (~30 min). Rejects non-admin roles. |
| POST | `/api/auth/logout` | Clears cookie; requires valid session. |
| GET | `/api/auth/me` | Current operator `{username, role}`. |

Admin-gated routes accept: signed session cookie, `X-Admin-Token: <access_token>`, or legacy `HELIX_ADMIN_TOKEN`. See `docs/guides/cross-tab-auth.md`.

---

## Core

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|------------|
| GET | `/api/health` | Operational status, DB ping, scheduler state, version | 60/min |
| GET | `/api/version` | Application version string | 60/min |
| GET | `/api/assets` | Available assets with metadata | 60/min |
| GET | `/api/dashboard?asset=USDT` | Live risk monitoring payload | 60/min |
| GET | `/api/dashboard/summary` | Per-asset token-card summary for all enabled assets (one query set) | 60/min |
| POST | `/api/refresh` | Trigger immediate data refresh | 10/min |
| GET | `/api/metrics` | Prometheus metrics (internal, blocked at nginx in production) | — |
| GET | `/api/settings` | Feature flags, provider toggles, intervals (requires X-Admin-Token) | 10/min |
| PUT | `/api/settings` | Update a setting (`key`, `value`) (requires X-Admin-Token) | 5/min |

## Trends & Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/trends?asset=USDT&window=7d` | Historical trend points (signal, price, supply, depeg, concentration) |
| GET | `/api/trends/chains?asset=USDT&window=7d` | Chain-level trend series |
| GET | `/api/trends/export?asset=USDT&window=7d&format=csv` | CSV export |
| GET | `/api/events?asset=USDT&limit=20` | Signal events feed |
| GET | `/api/events/export?asset=USDT&window=7d&format=csv` | CSV export |
| GET | `/api/compare?assets=USDT,USDC&window=7d` | Cross-asset aligned series (min 2, max 8 assets) |

`window` param: `24h`, `7d` (default), `30d`, `90d`

## Predictive & Analytics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/predictive?asset=USDT` | Predictive bundle (depeg probability, regime state, forecast) |
| GET | `/api/analytics/correlations?asset=USDT&window_days=30` | Pearson correlation matrix across 5 metrics, ranked pairs |
| GET | `/api/analytics/patterns?asset=USDT&window_days=30` | Trend direction, volatility, day-of-week seasonality detection |
| GET | `/api/analytics/regime?asset=USDT&window_hours=48` | Three-state regime classifier (stable/elevated/crisis) with duration and transitions |
| GET | `/api/analytics/rotation?assets=USDT,USDC&window_days=30` | Cross-asset supply rotation signals (correlation + dominance shift) |
| GET | `/api/analytics/stress-leaderboard?asset=USDT` | Chains ranked by 24h/7d supply velocity with direction |
| GET | `/api/analytics/sentiment?text=...` | On-demand LLM sentiment (Ollama Cloud). Legacy alias: `/api/analytics/finbert/sentiment` |
| GET | `/api/analytics/forecast-accuracy?asset=USDT` | Forecast accuracy vs actuals |
| GET | `/api/anomaly/detect?asset=USDT` | Z-score + Isolation Forest anomaly detection |
| GET | `/api/anomaly/change-points?asset=USDT&window_days=14` | CUSUM change-point detection on depeg, supply, concentration |
| GET | `/api/forecasts?asset=USDT` | Latest forecast runs with historical actuals |

## OSINT

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/osint/feed?asset=USDT&limit=20` | Recent news articles with LLM-powered sentiment (Ollama Cloud) |
| GET | `/api/osint/sentiment?asset=USDT&window_days=7` | Daily-aggregated sentiment time-series |
| GET | `/api/osint/attestation` | Issuer report age + DefiLlama supply feed freshness per asset |
| GET | `/api/osint/correlate?asset=USDT&window_hours=24` | Sentiment-depeg event correlation |

## Sources & Alerts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sources/status` | Circuit breaker state for all registered sources |
| GET | `/api/sources/usage` | Per-source API call counts for current day (daily granularity) |
| GET | `/api/sources/{name}/config` | Configuration schema for a source |
| GET | `/api/alerts/config` | Active alert rule definitions |
| GET | `/api/alerts?asset=USDT&severity=warning&limit=100` | Fired signal events (admin token) | 30/min |

## Admin (env-gated)

| Method | Endpoint | Description | Gate |
|--------|----------|-------------|------|
| POST | `/api/admin/backfill?asset=USDT&days=7` | Synthetic historical backfill | `allow_backfill` in Settings UI |
| GET | `/api/admin/diagnostics` | Full system snapshot (version, health, sources, usage, settings, DB stats) | Requires admin token |

## Settings Management

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/settings` | Get all settings (supports `?search=`, `?group=`) | Admin token |
| PUT | `/api/settings` | Update a setting (`key`, `value`) | Admin token |
| GET | `/api/settings/last-prune` | Last retention prune result JSON | Admin token |
| GET | `/api/settings/ops` | Scheduler + sources + quality score summary | Admin token |
| GET | `/api/settings/groups` | Get all setting groups | Admin token |
| GET | `/api/settings/defaults` | Get default values for all settings | Admin token |

## Event Labels (v4.2.0+)

Operator labeling corpus for OSINT and anomaly events. Labels are **append-only** (no delete API).

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/events/{type}/{id}/labels` | List labels (`type`: `osint` \| `anomaly`) | Open |
| POST | `/api/events/{type}/{id}/labels` | Add label (`confirmed`, `rejected`, `noise`, `tagged`) | Admin token |

OSINT `event_id` = article numeric id. Anomaly `event_id` = `ASSET:metric:ISO-timestamp`.

## V4 Series History (v4.2.0+)

Long-range reads use Timescale continuous aggregates on PostgreSQL (≥7d windows); SQLite/dev uses raw snapshots.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/series/funding?days=30&symbol=USDT` | Funding rate history |
| GET | `/api/v1/series/{symbol}/yield?days=30` | Yield-bearing snapshots |
| GET | `/api/v1/series/{symbol}/collateral?days=30` | Collateral snapshots |
| GET | `/api/v1/series/{symbol}/whale?days=30` | Whale activity snapshots |

## Data Quality (v4.1.0+)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/data-quality/summary` | Latest snapshot: overall score, source health, bucket fill-rates, 30d history | Open |
| GET | `/api/data-quality/overview` | Live computed metrics (admin) | Admin token |
| GET | `/api/data-quality/report` | Full quality report (admin) | Admin token |

## Insight Assets (v4.1.0+)

Versioned **deterministic** insight objects. The scheduled refresh job and request path never call the LLM (avoids 504s). Live AI narratives use `/api/ai/*` instead. The optional `ai_narrative` field is only present if a historical row still has it; new writes leave it unset.

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/insights/{kind}?asset=USDT` | Latest insight (`risk_explain`, `market_snapshot`, `anomaly_digest`, `forecast_run`, `dews_explain`) | Open |
| GET | `/api/insights/{kind}/export?format=ndjson` | Historical insights export (NDJSON or CSV) | Open |

Response shape:

```json
{
  "kind": "risk_explain",
  "schema_version": "1.0",
  "asset_scope": "USDT",
  "generated_at": "2026-07-19T12:00:00Z",
  "deterministic_payload": { "signal_score": 42, "rule_sentences": ["..."] },
  "sources": { "engine": "helix_deterministic" },
  "quality_score": 100.0
}
```

## Settings Audit

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/settings/audit` | Settings change audit log (supports `?setting_key=`, `?user_id=`, `?limit=`, `?offset=`) | Admin token |
| GET | `/api/settings/audit/history/{setting_key}` | Full change history for a single setting | Admin token |
| GET | `/api/settings/audit/user/{user_id}` | All changes made by a specific user | Admin token |
| GET | `/api/settings/audit/recent` | Most recent settings changes | Admin token |
| GET | `/api/settings/export/json` | Export all settings as downloadable JSON file | Admin token |
| POST | `/api/settings/import/json` | Import settings from uploaded JSON file | Admin token |

## Data Quality Dashboard (Phase 5)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/data-quality/overview` | Get overall data quality metrics and scores | Admin token |
| GET | `/api/data-quality/report` | Get complete data quality report with detailed metrics | Admin token |
| GET | `/api/data-quality/sources` | Get detailed source quality metrics by provider | Admin token |
| GET | `/api/data-quality/assets` | Get asset-specific data quality metrics | Admin token (supports `?asset=USDT` parameter) |

Data Quality Dashboard provides comprehensive monitoring of:
- Source health and reliability metrics
- Data completeness and consistency scores  
- Freshness and timeliness metrics
- API usage and performance tracking
- Cross-source validation and discrepancy detection

## AI (optional)

| Method | Endpoint | Description | Rate Limit | Gate |
|--------|----------|-------------|------------|------|
| GET | `/api/ai/explain?asset=USDT` | LLM-generated risk explanation | 30/min | `AI_MODE != ai_off` |
| GET | `/api/ai/narrative?asset=USDT` | Market narrative with sentiment + events | 30/min | `AI_MODE != ai_off` |
| GET | `/api/ai/insights?asset=USDT` | Supply, chain, and anomaly insights | 30/min | `AI_MODE != ai_off` |
| GET | `/api/ai/market-overview` | Cross-asset market summary | 20/min | `AI_MODE != ai_off` (returns engine data when off) |
| GET | `/api/ai/usage` | Recent AI usage per feature / provider / model | 30/min | **Admin** session or token |
| GET | `/api/ai/warnings` | Operational AI/source warnings banner | 30/min | Admin |
| GET | `/api/ai/providers` | List AI providers (Ollama Cloud, OpenRouter) | 30/min | Admin |
| GET | `/api/ai/providers/{provider_id}/models` | Models for provider | 30/min | Admin |

AI explain/narrative routes can optionally require admin auth — enable `ai_require_token` in Settings (recommended when internet-facing). Default is open for trusted LAN.

**Models response shape:**

```json
{ "models": [{ "id": "…", "name": "…" }], "error": null, "provider": "ollama_cloud" }
```

`error` is `null` on success, or e.g. `no_api_key`, `provider_http_401`, `provider_error:TimeoutException` so the UI can distinguish empty catalogs from misconfiguration.

## Settings import / export (Admin)

| Method | Endpoint | Notes |
|--------|----------|-------|
| GET | `/api/settings/export` | Secrets exported as `"configured"` only |
| POST | `/api/settings/import` | Skips secret keys when value is a mask sentinel (does not clobber live keys) |
| PUT | `/api/settings` | Admin; secrets never echoed in response (`value: "configured"`) |

## AI Provider Facade (Internal)

External modules (forensics, OSINT, webhooks) call the AI subsystem through the public facade at `services/components/ai/facade.py`:

```python
from services.components.ai.facade import ollama_cloud
```

| Function | Signature | Description |
|----------|-----------|-------------|
| `ollama_cloud` | `(prompt, max_tokens, system=None, model=None, **kwargs)` | Ollama Cloud chat completion; pass `_resolved_api_key` kwarg |

The underscore-prefixed original (`_ollama_cloud`) remains in `services/ai_router` for backward compatibility; new code should import from the facade. Budget helpers have been removed; usage is tracked via `AiUsage`.

## Common Parameters

| Param | Type | Valid Values | Notes |
|-------|------|-------------|-------|
| `asset` | string | `USDT`, `USDC`, `DAI`, `PYUSD` | Uppercase, 2-16 alphanumeric |
| `window` | string | `24h`, `7d`, `30d` | Time window for trend queries |
| `window_days` | integer | 7–90 | Alternative to `window` for analytics |
| `format` | string | `csv`, `json` | Export format |
| `limit` | integer | 1–100 | Row limit for lists |

## Response Format

All endpoints return JSON. Error responses follow:

```json
{"detail": "Error description"}
```

## Health Response

`GET /api/health` returns:

```json
{
  "status": "ok",
  "db": true,
  "db_connected": true,
  "redis_connected": false,
  "last_successful_fetch": "2026-05-27T12:00:00Z",
  "scheduler_running": true,
  "asset_freshness": {
    "USDT": {"age_hours": 0.08, "last_fetch": "2026-05-27T12:00:00Z"},
    "USDC": {"age_hours": 0.17, "last_fetch": "2026-05-27T11:55:00Z"}
  },
  "worst_asset_age_hours": 0.17,
  "version": "4.4.0"
}
```

- `db` / `db_connected` — Database connectivity (`SELECT 1` ping)
- `redis_connected` — Redis reachability (`PING` via `cache._redis.ping()`), false when Redis not configured
- `last_successful_fetch` — DeFiLlama source last OK fetch timestamp
- `scheduler_running` — APScheduler background scheduler state
- `asset_freshness` — Per-asset map of `{symbol: {age_hours, last_fetch}}` from `asset_freshness` table
- `worst_asset_age_hours` — Highest age_hours across all tracked assets (null if none)
- `version` — `HELIX_VERSION` from `backend/services/retention.py`

## Schema

Typed Pydantic response models in `backend/schemas.py`:

| Model | Endpoint |
|-------|----------|
| `DashboardResponse` | `/api/dashboard` |
| `DashboardSummaryItemOut` | `/api/dashboard/summary` |
| `VersionResponse` | `/api/version` |
| `TrendResponseOut` | `/api/trends` |
| `ChainTrendResponseOut` | `/api/trends/chains` |
| `SignalEventsResponseOut` | `/api/events` |
| `SourceStatusOut` | `/api/sources/status` |
 | `SourceUsageResponse` | `/api/sources/usage` (raw dict, not a Pydantic model) |

## V4 — Intelligence & Forensics

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/dews?asset=USDT` | DEWS anomaly scoring — tiered depeg-watch score, z-score, CUSUM, ONNX probability, whale flow, holder concentration | Public |
| GET | `/api/onchain/whale-flow?asset=USDT` | Whale net inflow/outflow (24h) by asset, alert threshold breached | Public |
| GET | `/api/onchain/holder-concentration?asset=USDT` | Top-10 holder share %, mint/burn velocity | Public |
| GET | `/api/v1/blacklist/stats` | Blacklist aggregate stats (total events, frozen USD, by asset/chain, last 30d) | Public |
| GET | `/api/v1/blacklist/events` | Blacklist event list with optional `?asset=`, `?chain=`, `?limit=`, `?offset=` | Admin token |
| GET | `/api/v1/tags/{address}` | Tags for an address (optional `?chain=` filter) | Public |
| POST | `/api/v1/tags` | Create an address tag (body: `address`, `chain?`, `label`, `category`, `confidence`) | Admin token |
| DELETE | `/api/v1/tags/{tag_id}` | Delete a tag by ID | Admin token |
| GET | `/api/v1/tags/export` | CSV export of all address tags | Admin token |
| GET | `/api/v1/assets/{symbol}/yield` | Yield snapshot: `current_apy`, `apy_7d_avg`, `apy_7d_delta`, `yield_source`, `yield_sustainability`, `funding_rate_current/7d_avg`, `insurance_fund_usd/coverage`, `staking_ratio`, `lending_utilization_pct` | Public |
| GET | `/api/v1/assets/{symbol}/collateral` | Collateral snapshot: `collateral_ratio`, `collateral_assets`, `liquidation_threshold`, `liquidation_queue_usd`, `debt_ceiling_utilization_pct`, `largest_vault_usd`, `collateral_health_score` | Public |
| GET | `/api/v1/assets/{symbol}/reserve` | Reserve snapshot: `reserve_usd`, `circulating_supply`, `coverage_ratio`, `reserve_composition`, `attestation_date/source/url`, `attestation_lag_days`, `genius_act_compliant`, `mica_status` | Public |
| POST | `/api/v1/investigate` | Investigation pipeline — peel chain, bridge hops, clustering, blacklist, OSINT, timeline, risk, AI narrative | Admin token |
