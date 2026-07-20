# Operator authentication (single-admin)

Helix is a **single-operator** console, not a multi-user SaaS product.

## What you get

| Piece | Role |
|-------|------|
| Seeded admin user | Created once from `HELIX_ADMIN_USERNAME` + `HELIX_ADMIN_PASSWORD` (`backend/scripts/seed_admin.py`) |
| `POST /api/auth/login` | Username/password → HMAC session token (~30 min) + httpOnly cookie `helix_session` |
| Settings → **Admin login** | Control Room gate for AI, retention, API keys, registry |
| SQLAdmin `/admin` | Same admin user; rare table/registry ops (Tier 2) |
| `HELIX_ADMIN_TOKEN` | Optional **legacy** static token for `X-Admin-Token` (rollout/automation only) |

There is **no** self-service registration. Extra accounts are not required; if you ever enable `feature_multi_user`, user CRUD is admin-only and still not the product default.

## Browser session flow

1. Open **Settings** → enter admin username/password → **Sign in**.
2. Server sets `helix_session` (httpOnly) and returns `access_token` in JSON.
3. UI keeps a mirror in `localStorage` (`helix_admin_token`) for `X-Admin-Token` on `adminFetch`.
4. Badge shows **Operator: &lt;username&gt;** when `isAuthenticated` is true.
5. After refresh, `restoreSession()` calls `GET /api/auth/me` with cookie ± header and re-hydrates auth state.
6. Session TTL ≈ **30 minutes**. On 401/403 the UI clears local state and prompts re-login.

Cross-tab: `storage` events sync the token mirror when another tab logs in/out.

## API clients

```http
POST /api/auth/login
Content-Type: application/x-www-form-urlencoded

username=admin&password=...
```

Then either:

- Cookie session with `credentials: include`, or  
- Header: `X-Admin-Token: <access_token>`

## Production checklist

| Env | Required | Notes |
|-----|----------|--------|
| `SESSION_SIGNING_KEY` | **Yes** | `openssl rand -hex 32` — blank ⇒ login returns **503** |
| `HELIX_ADMIN_USERNAME` / `HELIX_ADMIN_PASSWORD` | First deploy | Seeds the only operator account |
| `HELIX_COOKIE_SECURE=1` | HTTPS | Sets Secure on `helix_session` |
| `CORS_ORIGINS` | If cross-origin UI | Must not be `*` when using credentials |
| `HELIX_ADMIN_TOKEN` | Optional | Legacy static token; prefer signed sessions |

## Multi-user flag

`feature_multi_user` (settings registry) gates `/api/users*` CRUD. Leave **off** unless you deliberately run multiple operators. Product docs and Control Room assume one admin.
