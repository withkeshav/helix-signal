# Cross-tab authentication & session cookies (P1.5 + P3)

Helix supports **httpOnly session cookies** (`helix_session`) plus optional `X-Admin-Token` header for API clients.

## Operator notes

- Sign in once via **Settings**; the server sets an httpOnly cookie and the UI mirrors the token for header-based admin calls.
- Cross-tab sync uses `localStorage` (`helix_admin_token`) + `storage` events when the token is updated in-tab.
- If a tab shows "Session expired", sign in again — `adminFetch` clears stale state on HTTP 401/403.
- Tokens expire after ~30 minutes (server session TTL).

## API clients

Continue sending `X-Admin-Token: <access_token>` from `POST /api/auth/login` JSON body, or rely on cookie session with `credentials: include` in browser fetch.

## Production

Set explicit `CORS_ORIGINS` (not `*`) when using cookies with `allow_credentials=True`. Optional `HELIX_COOKIE_SECURE=1` behind HTTPS.
