# Webhook Alerts

Helix Signal can POST signed JSON alert events to any HTTPS webhook when signal events are persisted (band changes, depeg pressure, supply moves, etc.).

## Configuration (Settings UI)

| Setting | Description |
|---------|-------------|
| `webhook_enabled` | Master toggle |
| `webhook_url` | Target HTTPS endpoint |
| `webhook_signing_secret` | HMAC SHA-256 secret (required when enabled) |
| `webhook_min_severity` | Minimum severity: `info`, `warning`, or `critical` |
| `webhook_timeout_seconds` | HTTP timeout (default 10s) |

Direct Telegram, email, Discord, and Slack adapters are **not** built in — connect those via Zapier, Make, n8n, or Pabbly using this webhook.

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

Matches `webhook_dispatcher.build_alert_payload` exactly (additional fields may be present):

```json
{
  "schema_version": "1.0",
  "event_id": "uuid",
  "timestamp": "2026-06-23T12:00:00+00:00",
  "asset_symbol": "USDT",
  "chain_key": "ethereum",
  "severity": "warning",
  "event_type": "signal_band_change",
  "title": "USDT signal moved to Watch",
  "summary": "...",
  "old_value": "...",
  "new_value": "...",
  "delta": 0.123,
  "threshold": 50,
  "metrics": {
    "signal_score": 45,
    "depeg_index": 12,
    "supply_change_7d_pct": -1.2
  },
  "metadata": {},
  "links": { "dashboard": "https://helix.withkeshav.com/?asset=USDT" }
}
```

Use `severity`, `event_type`, `metrics.signal_score` etc. for routing.

## Retry Behavior

Up to 3 delivery attempts with 1s then 2s backoff on network errors or non-2xx responses. Delivery is best-effort; there is no persistent delivery audit log yet.

## Automation Examples

- **Zapier / Make**: Webhooks → Catch Hook → route to Slack, email, Telegram bot
- **n8n**: Webhook node → verify HMAC → branch on `severity`
- **Pabbly Connect**: Incoming webhook trigger → multi-step workflow
