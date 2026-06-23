"""Outbound webhook alert dispatcher for external automation (Zapier, n8n, Pabbly, etc.)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from structlog import get_logger

from database import SignalEvent

log = get_logger(__name__)

SCHEMA_VERSION = "1.0"
SIGNATURE_HEADER = "X-Webhook-Signature-256"

_SEVERITY_ORDER = {
    "debug": 0,
    "info": 1,
    "warning": 2,
    "critical": 3,
}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _severity_meets_minimum(event_severity: str, min_severity: str) -> bool:
    ev = _SEVERITY_ORDER.get((event_severity or "info").lower(), 1)
    mn = _SEVERITY_ORDER.get((min_severity or "warning").lower(), 2)
    return ev >= mn


def build_alert_payload(
    event: SignalEvent,
    *,
    signal_score: int | None = None,
    depeg_index: int | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stable versioned JSON schema for alert events."""
    meta: dict[str, Any] = {}
    if event.metadata_json:
        try:
            meta = json.loads(event.metadata_json)
        except json.JSONDecodeError:
            meta = {"raw": event.metadata_json}

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "timestamp": (event.timestamp or datetime.now(timezone.utc)).isoformat(),
        "asset_symbol": event.asset_symbol,
        "chain_key": event.chain_key,
        "severity": event.severity,
        "event_type": event.event_type,
        "title": event.title,
        "summary": event.summary,
        "old_value": event.old_value,
        "new_value": event.new_value,
        "delta": event.delta,
        "threshold": event.threshold,
        "metrics": {
            "signal_score": signal_score,
            "depeg_index": depeg_index,
            **(metrics or {}),
        },
        "metadata": meta,
        "links": {
            "dashboard": f"https://helix.withkeshav.com/?asset={event.asset_symbol}",
        },
    }


def compute_signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _validate_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


class WebhookDispatcher:
    """Deliver qualifying SignalEvents to a configured webhook endpoint."""

    def __init__(self, db: Any) -> None:
        self.db = db
        from providers.settings import get_setting

        self.enabled = _coerce_bool(get_setting("webhook_enabled", db))
        self.url = str(get_setting("webhook_url", db) or "").strip()
        self.secret = str(get_setting("webhook_signing_secret", db) or "").strip()
        self.min_severity = str(get_setting("webhook_min_severity", db) or "warning")
        timeout = get_setting("webhook_timeout_seconds", db)
        try:
            self.timeout = int(timeout) if timeout not in (None, "") else 10
        except (TypeError, ValueError):
            self.timeout = 10

    def should_dispatch(self, event: SignalEvent) -> bool:
        if not self.enabled:
            return False
        if not _validate_url(self.url):
            return False
        if not self.secret:
            return False
        return _severity_meets_minimum(event.severity, self.min_severity)

    def deliver_event(
        self,
        event: SignalEvent,
        *,
        signal_score: int | None = None,
        depeg_index: int | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.should_dispatch(event):
            return {"dispatched": False, "reason": "disabled_or_filtered"}

        payload = build_alert_payload(
            event,
            signal_score=signal_score,
            depeg_index=depeg_index,
            metrics=metrics,
        )
        body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Helix-Signal-Webhook/1.0",
            SIGNATURE_HEADER: compute_signature(body, self.secret),
        }

        max_attempts = 3
        backoff = [1.0, 2.0]
        last_error: str | None = None

        for attempt in range(max_attempts):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(self.url, content=body, headers=headers)
                if 200 <= resp.status_code < 300:
                    log.info(
                        "webhook.delivered",
                        event_type=event.event_type,
                        asset=event.asset_symbol,
                        status=resp.status_code,
                        attempt=attempt + 1,
                    )
                    return {"dispatched": True, "status_code": resp.status_code, "attempt": attempt + 1}
                last_error = f"HTTP {resp.status_code}"
            except Exception as exc:
                last_error = str(exc)

            if attempt < max_attempts - 1:
                time.sleep(backoff[min(attempt, len(backoff) - 1)])

        log.warning(
            "webhook.failed",
            event_type=event.event_type,
            asset=event.asset_symbol,
            error=last_error,
        )
        return {"dispatched": False, "reason": last_error or "unknown"}


def dispatch_events(
    db: Any,
    events: list[SignalEvent],
    *,
    metrics_by_asset: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Non-blocking-style batch dispatch after events are persisted."""
    dispatcher = WebhookDispatcher(db)
    if not dispatcher.enabled:
        return []
    results: list[dict[str, Any]] = []
    for event in events:
        asset_metrics = (metrics_by_asset or {}).get(event.asset_symbol or "", {})
        results.append(
            dispatcher.deliver_event(
                event,
                signal_score=asset_metrics.get("signal_score"),
                depeg_index=asset_metrics.get("depeg_index"),
                metrics=asset_metrics,
            )
        )
    return results
