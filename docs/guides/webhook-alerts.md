# Webhook Alerts

Helix Signal POSTs signed JSON alert events to configured HTTPS endpoints when signal events are persisted (band changes, depeg pressure, supply moves, etc.).

**Preferred path:** multi-endpoint routing via Control Room → Alerts → **Webhook endpoints** (see `docs/guides/alert-routing.md`). Each endpoint has its own URL, HMAC secret, severity floor, event types, and optional asset filter.

## Legacy single-webhook settings (fallback)

When no rows exist in `webhook_endpoints`, these settings still work:

| Setting | Description |
|---------|-------------|
| `webhook_enabled` | Master toggle |
| `webhook_url` | Target HTTPS endpoint |
| `webhook_signing_secret` | HMAC SHA-256 secret (required when enabled) |
| `webhook_min_severity` | Minimum severity: `info`, `warning`, or `critical` |
| `webhook_timeout_seconds` | HTTP timeout (default 10s) |

On first admin list of endpoints, configured legacy settings are migrated into one default endpoint row.

Email is configured separately via SMTP settings + `alert_email_event_types` (not via Discord/Telegram adapters — those are not built in).

## Signature Verification

Each POST includes header `X-Webhook-Signature-256`:

```
sha256=<hex digest of HMAC-SHA256(request_body, signing_secret)>
```

Example (Python):

```python
import hmac, hashlib

def verify(body: bytes, secret: str, header: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)
```

## Payload Schema (v1.0)

Matches `webhook_dispatcher.build_alert_payload` (plus `event_category` from the router).

## Retry

3 attempts with 1s / 2s backoff. Private / loopback URLs are rejected.

## Automation examples

Zapier, n8n, Make, Pabbly — point at a public HTTPS catch URL and verify the HMAC header.
