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

### Authentication

Helix-Signal uses `X-Admin-Token` header-based auth for admin routes (settings, refresh, backfill, alerts config, governance, metrics). Set `HELIX_ADMIN_TOKEN` in `.env` to enable. Unset tokens fail closed (503). Mismatched tokens return 403.

Public endpoints (dashboard, health, trends, events, OSINT, forecasts, sources, AI explain) remain accessible. For additional edge protection, place a reverse proxy with basic-auth or OAuth in front.

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

### Settings and API keys

- API keys saved via the Settings UI are stored in the `settings` database table as **plaintext** (not encrypted at rest). Protection relies on admin authentication and server/database access control.
- `GET /api/settings` never returns raw secret values — only `"configured"` or `null`.
- Settings audit log entries for secret-type keys store `[REDACTED]` instead of the actual value (v4.0.4+).
