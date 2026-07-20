"""Unified alert router — multi-webhook + SMTP subscriptions."""

from __future__ import annotations

import json
import smtplib
from email.mime.text import MIMEText
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from structlog import get_logger

from database import SignalEvent, WebhookEndpoint
from services.event_catalog import event_category
from services.webhook_dispatcher import (
    _SEVERITY_ORDER,
    _validate_url,
    build_alert_payload,
    compute_signature,
    SIGNATURE_HEADER,
)

log = get_logger(__name__)


def _severity_meets(event_severity: str, min_severity: str) -> bool:
    ev = _SEVERITY_ORDER.get((event_severity or "info").lower(), 1)
    mn = _SEVERITY_ORDER.get((min_severity or "warning").lower(), 2)
    return ev >= mn


def _endpoint_matches(ep: WebhookEndpoint, event: SignalEvent) -> bool:
    if not ep.enabled:
        return False
    if not _severity_meets(event.severity or "info", ep.min_severity or "warning"):
        return False
    types = list(ep.event_types or [])
    if types:
        cat = event_category(event.event_type)
        if cat not in types and (event.event_type or "") not in types:
            return False
    assets = list(ep.assets or [])
    if assets:
        sym = (event.asset_symbol or "").upper()
        if sym and sym not in [a.upper() for a in assets]:
            return False
    return True


def _decrypt_secret(enc: str) -> str:
    from providers.settings_crypto import decrypt_secret

    return decrypt_secret(enc) or enc


def deliver_to_endpoint(
    ep: WebhookEndpoint,
    event: SignalEvent,
    *,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import httpx
    import time

    if not _validate_url(ep.url):
        return {"dispatched": False, "endpoint_id": ep.id, "reason": "invalid_url"}
    secret = _decrypt_secret(ep.signing_secret_enc)
    if not secret:
        return {"dispatched": False, "endpoint_id": ep.id, "reason": "no_secret"}
    payload = build_alert_payload(
        event,
        signal_score=(metrics or {}).get("signal_score"),
        depeg_index=(metrics or {}).get("depeg_index"),
        metrics=metrics,
    )
    payload["event_category"] = event_category(event.event_type)
    body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Helix-Signal-Webhook/1.0",
        SIGNATURE_HEADER: compute_signature(body, secret),
    }
    timeout = int(ep.timeout_seconds or 10)
    last_error: str | None = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(ep.url, content=body, headers=headers)
            if 200 <= resp.status_code < 300:
                return {"dispatched": True, "endpoint_id": ep.id, "status_code": resp.status_code, "attempt": attempt + 1}
            last_error = f"HTTP {resp.status_code}"
        except Exception as exc:
            last_error = str(exc)
        if attempt < 2:
            time.sleep(1.0 * (attempt + 1))
    log.warning("alert_router.webhook_failed", endpoint_id=ep.id, error=last_error)
    return {"dispatched": False, "endpoint_id": ep.id, "reason": last_error}


def _email_subscribed(db: Session, event: SignalEvent) -> bool:
    from providers.settings import get_setting

    if not get_setting("alert_email_enabled", db):
        return False
    min_sev = str(get_setting("alert_email_min_severity", db) or "warning")
    if not _severity_meets(event.severity or "info", min_sev):
        return False
    raw = get_setting("alert_email_event_types", db) or "[]"
    try:
        types = json.loads(raw) if isinstance(raw, str) else list(raw or [])
    except Exception:
        types = []
    if not types:
        return False
    cat = event_category(event.event_type)
    return cat in types or (event.event_type or "") in types


def deliver_email(db: Session, event: SignalEvent) -> dict[str, Any]:
    from providers.settings import get_setting

    if not _email_subscribed(db, event):
        return {"dispatched": False, "channel": "email", "reason": "not_subscribed"}
    smtp_host = get_setting("alert_smtp_host", db) or ""
    smtp_port = int(get_setting("alert_smtp_port", db) or "587")
    smtp_user = get_setting("alert_smtp_user", db) or ""
    smtp_pass = get_setting("alert_smtp_pass", db) or ""
    mail_to = get_setting("alert_email_to", db) or ""
    mail_from = (get_setting("alert_email_from", db) or "").strip() or smtp_user
    if not smtp_host or not smtp_user or not smtp_pass or not mail_to:
        return {"dispatched": False, "channel": "email", "reason": "missing_smtp_config"}
    try:
        msg = MIMEText(
            f"Helix Signal Alert\n\n"
            f"Asset: {event.asset_symbol}\n"
            f"Type: {event.event_type}\n"
            f"Severity: {event.severity}\n"
            f"Title: {event.title}\n"
            f"Summary: {event.summary}\n"
        )
        msg["Subject"] = f"[Helix] {(event.severity or '').upper()} - {event.asset_symbol} {event.event_type}"
        msg["From"] = mail_from
        msg["To"] = mail_to
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        return {"dispatched": True, "channel": "email"}
    except Exception as exc:
        log.warning("alert_router.email_failed", error=str(exc), exc_info=True)
        return {"dispatched": False, "channel": "email", "reason": str(exc)}


def deliver_event(
    db: Session,
    event: SignalEvent,
    *,
    metrics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    endpoints = db.execute(select(WebhookEndpoint).where(WebhookEndpoint.enabled.is_(True))).scalars().all()
    for ep in endpoints:
        if _endpoint_matches(ep, event):
            results.append(deliver_to_endpoint(ep, event, metrics=metrics))
    # Legacy single-webhook settings if no endpoints configured
    if not endpoints:
        results.extend(_legacy_single_webhook(db, event, metrics=metrics))
    results.append(deliver_email(db, event))
    return results


def _legacy_single_webhook(
    db: Session,
    event: SignalEvent,
    *,
    metrics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Fallback to global webhook_* settings until migrated to endpoints table."""
    from providers.settings import get_setting, get_secret
    from services.webhook_dispatcher import WebhookDispatcher

    if not get_setting("webhook_enabled", db):
        return []
    dispatcher = WebhookDispatcher(db)
    return [dispatcher.deliver_event(event, metrics=metrics or {})]


def deliver_events(
    db: Session,
    events: list[SignalEvent],
    *,
    metrics_by_asset: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for event in events:
        asset_metrics = (metrics_by_asset or {}).get(event.asset_symbol or "", {})
        out.extend(deliver_event(db, event, metrics=asset_metrics))
    return out


def migrate_legacy_webhook_settings(db: Session) -> WebhookEndpoint | None:
    """Create one endpoint from global webhook_* settings if table empty and configured."""
    from providers.settings import get_setting, get_secret
    from providers.settings_crypto import encrypt_secret

    existing = db.execute(select(WebhookEndpoint).limit(1)).scalars().first()
    if existing:
        return None
    if not get_setting("webhook_enabled", db):
        return None
    url = str(get_setting("webhook_url", db) or "").strip()
    secret = str(get_secret("webhook_signing_secret", db) or "").strip()
    if not url or not secret:
        return None
    ep = WebhookEndpoint(
        name="Migrated default",
        url=url,
        signing_secret_enc=encrypt_secret(secret),
        enabled=True,
        min_severity=str(get_setting("webhook_min_severity", db) or "warning"),
        event_types=[],
        assets=[],
        timeout_seconds=int(get_setting("webhook_timeout_seconds", db) or 10),
    )
    db.add(ep)
    db.commit()
    db.refresh(ep)
    return ep
