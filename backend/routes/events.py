from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session
from database import SignalEvent, get_db
from schemas import SignalEventsResponseOut
from services.exports import events_export
from signal_engine.core import get_asset_by_symbol
from utils import signal_event_rows_to_out

from core.limiter import limiter

router = APIRouter()


@router.get("/events", response_model=SignalEventsResponseOut)
@limiter.limit("60/minute")
def events(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    asset: str | None = None,
    db: Session = Depends(get_db),
) -> SignalEventsResponseOut:
    now = datetime.now(timezone.utc)
    stmt = select(SignalEvent)
    if asset:
        sym = asset.strip().upper()
        selected = get_asset_by_symbol(sym)
        if selected is None or not bool(selected.get("enabled")):
            raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")
        stmt = stmt.where(or_(SignalEvent.asset_symbol == sym, SignalEvent.asset_symbol == "ALL"))
    rows = db.execute(stmt.order_by(desc(SignalEvent.timestamp)).limit(limit)).scalars().all()
    return SignalEventsResponseOut(generated_at=now, events=signal_event_rows_to_out(rows))


@router.get("/events/export")
@limiter.limit("30/minute")
def events_export_route(
    request: Request,
    limit: int = Query(500, ge=1, le=10000),
    asset: str | None = None,
    format: str = Query("csv", alias="format"),
    db: Session = Depends(get_db),
):
    return events_export(db, asset=asset, limit=limit, fmt=format)
