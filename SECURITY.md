# Security Policy

## Reporting a Vulnerability

If you discover a security issue, please report it privately before opening a public issue.

Please include:

- A clear description of the vulnerability
- Steps to reproduce
- Impact assessment
- Any suggested remediation

For now, submit reports to the project maintainers through a private channel you control (email or direct message).
If no private channel is available, open a minimal public issue without exploit details and request a secure contact path.

## Scope Notes

Helix-Signal is a monitoring/data project and does not provide custody, wallet, or transaction signing features in V1.
Security priorities still include:

- Dependency hygiene
- Safe handling of environment variables
- Avoiding accidental secret disclosure in commits/issues
- Defensive error handling for external API failures

### Files that must never be committed

- `.env` and `secrets/` (API keys)
- Internal execution briefs and local research (see `.gitignore`)

### Authentication (single-admin operator)

Helix-Signal is designed for a **single seeded admin**, not multi-tenant SaaS.

| Mechanism | Role |
|-----------|------|
| **Session cookie** (`helix_session`) | Primary: Settings → Admin login with `HELIX_ADMIN_USERNAME` / `HELIX_ADMIN_PASSWORD` |
| **`X-Admin-Token`** | Optional header; `HELIX_ADMIN_TOKEN` if set. Unset token fails closed for header path where required. |
| **API keys** | Optional for intelligence API when `api_auth_mode=key_required` |

Admin-gated routes include settings (read/write/import/export), refresh, backfill, alerts config, governance, metrics, AI usage, and similar operator endpoints.

**Public by default (OSS / trusted LAN):** dashboard, health, trends, events, OSINT, forecasts, sources, and many AI explain/narrative routes when `ai_require_token` is false (default).

**Internet-facing deploys should:**

1. Set Control Room / settings `ai_require_token=true` (or env if wired).
2. Set `api_auth_mode=key_required` and issue API keys for non-admin consumers.
3. Set `HELIX_COOKIE_SECURE=1` behind HTTPS.
4. Set `SESSION_SIGNING_KEY` and `SETTINGS_ENCRYPTION_KEY`.
5. Place a reverse proxy (TLS, optional basic-auth/OAuth) in front.
6. Set `TRUSTED_PROXY_CIDR` correctly (see below).

### X-Forwarded-For Trust

Rate limiting and auth lockout use `X-Forwarded-For` to identify clients behind a reverse proxy.
If your reverse proxy does not strip or validate incoming `X-Forwarded-For` headers, an attacker
can spoof their IP to bypass per-IP limits.

Set `TRUSTED_PROXY_CIDR` in `.env` (e.g., `TRUSTED_PROXY_CIDR=10.0.0.0/8`) to restrict XFF trust
to direct connections from known proxy IPs. When set, clients connecting from outside the CIDR
are identified by their direct connection IP and their XFF header is ignored.

### Content Security Policy

A `Content-Security-Policy` header is applied to all backend responses and nginx static assets. Configure via `CONTENT_SECURITY_POLICY` env var. The default policy restricts scripts to `'self'` + CDN, blocks `frame-ancestors`, and restricts `form-action` and `base-uri`.
For inline scripts, the policy uses SHA-256 hashes to allow specific scripts while maintaining security. This approach avoids using 'unsafe-inline' which would weaken the policy. The importmap script in the frontend is specifically allowed through its SHA-256 hash.

Note: the UI may still use Alpine.js patterns that require careful CSP review (`unsafe-eval` may appear in some configurations). Prefer tightening CSP for public hosts.

### Settings and API keys

- Secret-type settings (provider API keys) are written through `set_setting` and, when `SETTINGS_ENCRYPTION_KEY` is set, stored as **Fernet ciphertext** in Postgres. Without that key (dev), values may be plaintext at rest - rely on DB/host access control.
- `GET /api/settings` never returns raw secret values - only `"configured"` or empty/null.
- `PUT /api/settings` for secret keys returns `"configured"` only; never echoes the submitted plaintext. Masked sentinels (`configured`, blank, `********`) do **not** overwrite an existing secret.
- Settings **export** includes masked secrets; **import** skips secret keys when the value is a mask sentinel so export→import cannot clobber live keys with the string `configured`.
- Settings audit log entries for secret-type keys store `[REDACTED]` instead of the actual value (v4.0.4+).
- SQLAdmin settings edit uses the same secret-skip rules.

### Data volume safety

Compose project name should stay **`helix-signal`**. Never run `docker compose down -v` on upgrade - that deletes `helix-signal_postgres_data`.
