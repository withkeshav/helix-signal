"""Chain drill-down: snapshot, trend, and filtered events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from database import AssetChainSnapshot, ChainTrendSnapshot, SignalEvent
from schemas import ChainTrendPointOut
from signal_engine.core import get_asset_by_symbol
from utils import utc_normalize, chain_key_from_name, signal_event_rows_to_out


def _resolve_chain_name(db: Session, *, asset: str, chain_key: str) -> str | None:
    needle = chain_key.strip().lower()
    rows = db.execute(select(AssetChainSnapshot).where(AssetChainSnapshot.asset_symbol == asset)).scalars().all()
    for r in rows:
        if chain_key_from_name(r.chain_name) == needle:
            return r.chain_name
    return None


def build_chain_detail(db: Session, *, chain_key: str, asset: str) -> dict[str, Any]:
    sym = asset.strip().upper()
    selected = get_asset_by_symbol(sym)
    if selected is None or not bool(selected.get("enabled")):
        raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")

    ck = chain_key.strip().lower()
    chain_name = _resolve_chain_name(db, asset=sym, chain_key=ck)
    if chain_name is None:
        raise HTTPException(status_code=404, detail=f"Chain '{chain_key}' not found for asset '{sym}'")

    snap = (
        db.execute(
            select(AssetChainSnapshot)
            .where(AssetChainSnapshot.asset_symbol == sym, AssetChainSnapshot.chain_name == chain_name)
        )
        .scalars()
        .first()
    )
    snapshot: dict[str, Any] | None = None
    if snap:
        snapshot = {
            "chain_name": snap.chain_name,
            "chain_key": ck,
            "supply_current": snap.supply_current,
            "chain_tvl": snap.tvl,
            "price": snap.price,
            "fetched_at": utc_normalize(snap.fetched_at).isoformat().replace("+00:00", "Z") if snap.fetched_at else None,
        }

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=7)
    trend_rows = (
        db.execute(
            select(ChainTrendSnapshot)
            .where(
                ChainTrendSnapshot.asset_symbol == sym,
                ChainTrendSnapshot.chain_key == ck,
                ChainTrendSnapshot.timestamp >= cutoff,
            )
            .order_by(ChainTrendSnapshot.timestamp.asc())
        )
        .scalars()
        .all()
    )
    trend_points = [
        ChainTrendPointOut(
            timestamp=r.timestamp,
            supply=r.supply,
            supply_share_pct=r.supply_share_pct,
            chain_tvl=r.chain_tvl,
            chain_signal_score=int(r.chain_signal_score),
            chain_signal_band=str(r.chain_signal_band),
            data_confidence_score=int(r.data_confidence_score),
        )
        for r in trend_rows
    ]

    event_rows = (
        db.execute(
            select(SignalEvent)
            .where(
                or_(SignalEvent.asset_symbol == sym, SignalEvent.asset_symbol == "ALL"),
                or_(SignalEvent.chain_key == ck, SignalEvent.chain_key.is_(None)),
            )
            .order_by(desc(SignalEvent.timestamp))
            .limit(50)
        )
        .scalars()
        .all()
    )

    return {
        "asset": sym,
        "chain_key": ck,
        "chain_name": chain_name,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "snapshot": snapshot,
        "trend_7d": [p.model_dump(mode="json") for p in trend_points],
        "events": [e.model_dump(mode="json") for e in signal_event_rows_to_out(event_rows)],
    }
