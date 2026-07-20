# Alert routing (webhooks + SMTP)

Helix delivers outbound alerts through **`alert_router`** when signal events are flushed (and optionally from health degradation hooks).

## Channels

1. **Multi-webhook endpoints** - table `webhook_endpoints`; each has its own URL, HMAC signing secret, min severity, event types, and asset filter.
2. **SMTP email** - settings `alert_email_*` / `alert_smtp_*` plus `alert_email_event_types` (JSON array of catalog ids) and `alert_email_min_severity`.

There is **no** Discord or Telegram adapter.

## Admin API

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/webhook-endpoints` | List (migrates legacy single webhook settings once) |
| POST | `/api/v1/webhook-endpoints` | Create |
| PUT | `/api/v1/webhook-endpoints/{id}` | Update |
| DELETE | `/api/v1/webhook-endpoints/{id}` | Delete |
| POST | `/api/v1/webhook-endpoints/{id}/test` | Send sample signed POST |
| GET | `/api/v1/alert-event-catalog` | Checkbox catalog |
| POST | `/api/v1/alerts/test-email` | SMTP connectivity test |

All require admin session / token.

## Matching rules

An endpoint receives an event when:

- `enabled`
- event severity ≥ `min_severity`
- `event_types` empty **or** contains the event category (see `services/event_catalog.py`)
- `assets` empty **or** contains the asset symbol

Email uses the same category matching via `alert_email_event_types`.

## Legacy settings

Global `webhook_enabled` / `webhook_url` / `webhook_signing_secret` still work as a **fallback** when the endpoints table is empty. Prefer creating endpoints in Control Room → Alerts.

Signature header remains `X-Webhook-Signature-256` (`sha256=<hex>`). See `docs/guides/webhook-alerts.md`.
