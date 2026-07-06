"""CSV/JSON export helpers for trends and events."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from fastapi.responses import Response
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from database import AssetTrendSnapshot, SignalEvent
from schemas import SignalEventOut, TrendPointOut
from signal_engine.core import get_asset_by_symbol
from utils import window_delta, signal_event_rows_to_out

MAX_EXPORT_ROWS = 10_000

_ALLOWED_WINDOWS = frozenset({"24h", "7d", "30d"})


def fetch_trend_export_rows(db: Session, *, asset: str, window: str) -> list[TrendPointOut]:
    w = window.strip().lower()
    if w not in _ALLOWED_WINDOWS:
        raise HTTPException(status_code=400, detail="Invalid window. Use 24h, 7d, or 30d.")
    sym = asset.strip().upper()
    selected = get_asset_by_symbol(sym)
    if selected is None or not bool(selected.get("enabled")):
        raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")

    now = datetime.now(timezone.utc)
    cutoff = now - window_delta(w)
    rows = (
        db.execute(
            select(AssetTrendSnapshot)
            .where(AssetTrendSnapshot.asset_symbol == sym, AssetTrendSnapshot.timestamp >= cutoff)
            .order_by(AssetTrendSnapshot.timestamp.asc())
            .limit(MAX_EXPORT_ROWS)
        )
        .scalars()
        .all()
    )
    return [
        TrendPointOut(
            timestamp=r.timestamp,
            total_supply=r.total_supply,
            price=r.price,
            depeg_index=int(r.depeg_index),
            signal_score=int(r.signal_score),
            signal_band=str(r.signal_band),
            concentration_score=int(r.concentration_score),
            data_confidence=str(r.data_confidence_label),
        )
        for r in rows
    ]


def fetch_event_export_rows(
    db: Session,
    *,
    asset: str | None,
    limit: int,
) -> list[SignalEventOut]:
    lim = min(max(1, limit), MAX_EXPORT_ROWS)
    stmt = select(SignalEvent)
    if asset:
        sym = asset.strip().upper()
        selected = get_asset_by_symbol(sym)
        if selected is None or not bool(selected.get("enabled")):
            raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")
        stmt = stmt.where(or_(SignalEvent.asset_symbol == sym, SignalEvent.asset_symbol == "ALL"))
    rows = db.execute(stmt.order_by(desc(SignalEvent.timestamp)).limit(lim)).scalars().all()
    return signal_event_rows_to_out(rows)


def _trend_rows_as_dicts(points: list[TrendPointOut]) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": p.timestamp.isoformat(),
            "total_supply": p.total_supply,
            "price": p.price,
            "depeg_index": p.depeg_index,
            "signal_score": p.signal_score,
            "signal_band": p.signal_band,
            "concentration_score": p.concentration_score,
            "data_confidence": p.data_confidence,
        }
        for p in points
    ]


def _event_rows_as_dicts(events: list[SignalEventOut]) -> list[dict[str, Any]]:
    return [
        {
            "id": e.id,
            "asset_symbol": e.asset_symbol,
            "chain_key": e.chain_key,
            "event_type": e.event_type,
            "severity": e.severity,
            "title": e.title,
            "summary": e.summary,
            "old_value": e.old_value,
            "new_value": e.new_value,
            "delta": e.delta,
            "threshold": e.threshold,
            "timestamp": e.timestamp.isoformat(),
            "metadata": e.metadata,
        }
        for e in events
    ]


def export_response(
    *,
    rows: list[dict[str, Any]],
    fmt: str,
    filename_stem: str,
) -> Response:
    f = fmt.strip().lower()
    if f == "json":
        body = json.dumps({"rows": rows, "count": len(rows)}, indent=2)
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename_stem}.json"'},
        )
    if f != "csv":
        raise HTTPException(status_code=400, detail="Invalid format. Use csv or json.")

    if not rows:
        csv_body = ""
    else:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        csv_body = buf.getvalue()

    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename_stem}.csv"'},
    )


def trends_export(db: Session, *, asset: str, window: str, fmt: str) -> Response:
    points = fetch_trend_export_rows(db, asset=asset, window=window)
    rows = _trend_rows_as_dicts(points)
    sym = asset.strip().upper()
    return export_response(rows=rows, fmt=fmt, filename_stem=f"helix-trends-{sym}-{window.strip().lower()}")


def events_export(db: Session, *, asset: str | None, limit: int, fmt: str) -> Response:
    events = fetch_event_export_rows(db, asset=asset, limit=limit)
    rows = _event_rows_as_dicts(events)
    stem = f"helix-events-{asset.strip().upper()}" if asset else "helix-events-all"
    return export_response(rows=rows, fmt=fmt, filename_stem=stem)
