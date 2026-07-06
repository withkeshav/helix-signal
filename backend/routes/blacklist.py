"""GET /api/v1/blacklist/events and /blacklist/stats routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from database import BlacklistEvent, get_db
from datetime import datetime, timedelta, timezone

router = APIRouter()


class BlacklistEventOut(BaseModel):
    id: int
    asset_symbol: str
    chain: str
    frozen_address: str | None = None
    frozen_balance_usd: float | None = None
    event_type: str | None = None
    tx_hash: str | None = None
    block_number: int | None = None
    intelligence_note: str | None = None
    timestamp: str | None = None


class BlacklistStatsOut(BaseModel):
    total_events: int
    total_frozen_usd: float
    by_asset: dict
    by_chain: dict
    last_30d_count: int


@router.get("/blacklist/events", response_model=list[BlacklistEventOut], dependencies=[Depends(require_admin_token)])
def blacklist_events(
    asset: str | None = None,
    chain: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(BlacklistEvent)
    if asset:
        q = q.filter(BlacklistEvent.asset_symbol == asset.upper())
    if chain:
        q = q.filter(BlacklistEvent.chain == chain.lower())
    rows = q.order_by(BlacklistEvent.id.desc()).offset(offset).limit(limit).all()
    return [
        BlacklistEventOut(
            id=r.id, asset_symbol=r.asset_symbol, chain=r.chain,
            frozen_address=r.frozen_address,
            frozen_balance_usd=r.frozen_balance_usd,
            event_type=r.event_type, tx_hash=r.tx_hash,
            block_number=r.block_number,
            intelligence_note=r.intelligence_note,
            timestamp=r.timestamp.isoformat() if r.timestamp else None,
        )
        for r in rows
    ]


@router.get("/blacklist/stats", response_model=BlacklistStatsOut)
def blacklist_stats(db: Session = Depends(get_db)):
    total = db.query(func.count(BlacklistEvent.id)).scalar() or 0
    total_usd = db.query(func.sum(BlacklistEvent.frozen_balance_usd)).scalar() or 0.0

    by_asset_rows = (
        db.query(BlacklistEvent.asset_symbol, func.sum(BlacklistEvent.frozen_balance_usd))
        .group_by(BlacklistEvent.asset_symbol)
        .all()
    )
    by_asset = {r[0]: float(r[1] or 0) for r in by_asset_rows}

    by_chain_rows = (
        db.query(BlacklistEvent.chain, func.sum(BlacklistEvent.frozen_balance_usd))
        .group_by(BlacklistEvent.chain)
        .all()
    )
    by_chain = {r[0]: float(r[1] or 0) for r in by_chain_rows}

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    last_30d = (
        db.query(func.count(BlacklistEvent.id))
        .filter(BlacklistEvent.timestamp >= cutoff)
        .scalar() or 0
    )

    return BlacklistStatsOut(
        total_events=total,
        total_frozen_usd=round(float(total_usd), 2),
        by_asset=by_asset,
        by_chain=by_chain,
        last_30d_count=last_30d,
    )
