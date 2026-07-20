"""Admin CRUD for multi-webhook endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from core.limiter import limiter
from database import SignalEvent, WebhookEndpoint, get_db
from providers.settings_crypto import encrypt_secret
from services.alert_router import deliver_to_endpoint, migrate_legacy_webhook_settings
from services.event_catalog import catalog_for_api

router = APIRouter()


class WebhookEndpointCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    url: str = Field(..., min_length=8, max_length=1024)
    signing_secret: str = Field(..., min_length=8)
    enabled: bool = True
    min_severity: str = "warning"
    event_types: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=10, ge=3, le=60)


class WebhookEndpointUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    signing_secret: str | None = None
    enabled: bool | None = None
    min_severity: str | None = None
    event_types: list[str] | None = None
    assets: list[str] | None = None
    timeout_seconds: int | None = None


def _serialize(ep: WebhookEndpoint) -> dict[str, Any]:
    return {
        "id": ep.id,
        "name": ep.name,
        "url": ep.url,
        "enabled": ep.enabled,
        "min_severity": ep.min_severity,
        "event_types": list(ep.event_types or []),
        "assets": list(ep.assets or []),
        "timeout_seconds": ep.timeout_seconds,
        "secret_configured": bool(ep.signing_secret_enc),
        "created_at": ep.created_at.isoformat() if ep.created_at else None,
        "updated_at": ep.updated_at.isoformat() if ep.updated_at else None,
    }


@router.get("/v1/webhook-endpoints")
@limiter.limit("30/minute")
def list_endpoints(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> list[dict[str, Any]]:
    migrate_legacy_webhook_settings(db)
    rows = db.execute(select(WebhookEndpoint).order_by(WebhookEndpoint.id.asc())).scalars().all()
    return [_serialize(r) for r in rows]


@router.get("/v1/alert-event-catalog")
@limiter.limit("30/minute")
def alert_event_catalog(
    request: Request,
    _auth=Depends(require_admin_token),
) -> list[dict[str, Any]]:
    return catalog_for_api()


@router.post("/v1/webhook-endpoints")
@limiter.limit("10/minute")
def create_endpoint(
    request: Request,
    body: WebhookEndpointCreate,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    ep = WebhookEndpoint(
        name=body.name.strip(),
        url=body.url.strip(),
        signing_secret_enc=encrypt_secret(body.signing_secret),
        enabled=body.enabled,
        min_severity=body.min_severity,
        event_types=body.event_types,
        assets=[a.upper() for a in body.assets],
        timeout_seconds=body.timeout_seconds,
    )
    db.add(ep)
    db.commit()
    db.refresh(ep)
    return _serialize(ep)


@router.put("/v1/webhook-endpoints/{endpoint_id}")
@limiter.limit("10/minute")
def update_endpoint(
    request: Request,
    endpoint_id: int,
    body: WebhookEndpointUpdate,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    ep = db.get(WebhookEndpoint, endpoint_id)
    if ep is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    if body.name is not None:
        ep.name = body.name.strip()
    if body.url is not None:
        ep.url = body.url.strip()
    if body.signing_secret is not None and body.signing_secret.strip():
        ep.signing_secret_enc = encrypt_secret(body.signing_secret.strip())
    if body.enabled is not None:
        ep.enabled = body.enabled
    if body.min_severity is not None:
        ep.min_severity = body.min_severity
    if body.event_types is not None:
        ep.event_types = body.event_types
    if body.assets is not None:
        ep.assets = [a.upper() for a in body.assets]
    if body.timeout_seconds is not None:
        ep.timeout_seconds = body.timeout_seconds
    ep.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ep)
    return _serialize(ep)


@router.delete("/v1/webhook-endpoints/{endpoint_id}")
@limiter.limit("10/minute")
def delete_endpoint(
    request: Request,
    endpoint_id: int,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    ep = db.get(WebhookEndpoint, endpoint_id)
    if ep is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    db.delete(ep)
    db.commit()
    return {"ok": True, "id": endpoint_id}


@router.post("/v1/webhook-endpoints/{endpoint_id}/test")
@limiter.limit("5/minute")
def test_endpoint(
    request: Request,
    endpoint_id: int,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    ep = db.get(WebhookEndpoint, endpoint_id)
    if ep is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    sample = SignalEvent(
        asset_symbol="USDT",
        chain_key=None,
        event_type="signal_band_change",
        severity="warning",
        title="Helix webhook test",
        summary="Test delivery from Control Room",
        timestamp=datetime.now(timezone.utc),
    )
    result = deliver_to_endpoint(ep, sample, metrics={"signal_score": 42, "depeg_index": 10})
    return result


@router.post("/v1/alerts/test-email")
@limiter.limit("5/minute")
def test_email(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    """Send a test email using current SMTP settings (bypasses event-type filter)."""
    from providers.settings import get_setting
    import smtplib
    from email.mime.text import MIMEText

    smtp_host = get_setting("alert_smtp_host", db) or ""
    smtp_port = int(get_setting("alert_smtp_port", db) or "587")
    smtp_user = get_setting("alert_smtp_user", db) or ""
    smtp_pass = get_setting("alert_smtp_pass", db) or ""
    mail_to = get_setting("alert_email_to", db) or ""
    mail_from = (get_setting("alert_email_from", db) or "").strip() or smtp_user
    if not smtp_host or not smtp_user or not smtp_pass or not mail_to:
        raise HTTPException(
            status_code=400,
            detail="SMTP incomplete: set alert_smtp_host, alert_smtp_user, alert_smtp_pass, and alert_email_to",
        )
    try:
        msg = MIMEText("Helix Signal test email from Control Room.")
        msg["Subject"] = "[Helix] SMTP test"
        msg["From"] = mail_from
        msg["To"] = mail_to
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        return {"ok": True, "to": mail_to}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SMTP send failed: {exc}") from exc
