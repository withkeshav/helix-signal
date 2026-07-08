"""Alerts API endpoints — fired-event inbox + rule config."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from core.limiter import limiter
from database import SignalEvent, get_db
from schemas import SignalEventsResponseOut
from services.alerts import load_alert_rules, load_all_alert_rules, save_alert_rules
from utils import signal_event_rows_to_out

router = APIRouter()


class AlertRulesUpdate(BaseModel):
    rules: list[dict[str, Any]]


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
    stmt = select(SignalEvent)
    if asset:
        sym = asset.strip().upper()
        stmt = stmt.where(or_(SignalEvent.asset_symbol == sym, SignalEvent.asset_symbol == "ALL"))
    if severity:
        sev = severity.strip().lower()
        stmt = stmt.where(SignalEvent.severity == sev)
    rows = db.execute(stmt.order_by(desc(SignalEvent.timestamp)).limit(limit)).scalars().all()
    return SignalEventsResponseOut(generated_at=now, events=signal_event_rows_to_out(rows))


@router.get("/alerts/config")
@limiter.limit("10/minute")
def get_alert_config(
    request: Request,
    include_disabled: bool = Query(False),
    _auth=Depends(require_admin_token),
) -> list[dict[str, Any]]:
    if include_disabled:
        return load_all_alert_rules()
    return load_alert_rules()


@router.put("/alerts/config")
@limiter.limit("10/minute")
def put_alert_config(
    request: Request,
    body: AlertRulesUpdate,
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    try:
        save_alert_rules(body.rules)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "count": len(body.rules)}
