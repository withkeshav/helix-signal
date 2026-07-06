"""Alerts API endpoints — fired-event inbox + rule config. CRUD stubs removed (Phase 1.1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from core.limiter import limiter
from database import SignalEvent, get_db
from schemas import SignalEventsResponseOut
from services.alerts import load_alert_rules
from utils import signal_event_rows_to_out

router = APIRouter()


@router.get("/alerts", response_model=SignalEventsResponseOut)
@limiter.limit("30/minute")
def list_fired_alerts(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    asset: str | None = None,
    severity: str | None = None,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> SignalEventsResponseOut:
    """List fired signal events (admin-gated alerts inbox).

    Filters by asset (matches the asset OR 'ALL') and/or severity.
    Ordered by timestamp desc.
    """
    now = datetime.now(timezone.utc)
    q = db.query(SignalEvent)
    if asset:
        sym = asset.strip().upper()
        q = q.filter(or_(SignalEvent.asset_symbol == sym, SignalEvent.asset_symbol == "ALL"))
    if severity:
        sev = severity.strip().lower()
        q = q.filter(SignalEvent.severity == sev)
    rows = q.order_by(desc(SignalEvent.timestamp)).limit(limit).all()
    return SignalEventsResponseOut(generated_at=now, events=signal_event_rows_to_out(rows))


@router.get("/alerts/config")
@limiter.limit("10/minute")
def get_alert_config(
    request: Request,
    _auth=Depends(require_admin_token),
) -> list[dict[str, Any]]:
    return load_alert_rules()
