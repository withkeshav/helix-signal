from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from structlog import get_logger

from database import AssetTrendSnapshot, SignalEvent

log = get_logger(__name__)


def generate_summary_report(db: Session, *, asset_symbol: str, days: int = 7) -> dict[str, Any]:
    asset_key = asset_symbol.upper()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    snapshots = (
        db.execute(
            select(AssetTrendSnapshot)
            .where(
                AssetTrendSnapshot.asset_symbol == asset_key,
                AssetTrendSnapshot.timestamp >= cutoff,
            )
            .order_by(AssetTrendSnapshot.timestamp.asc())
        )
        .scalars()
        .all()
    )

    events = (
        db.execute(
            select(SignalEvent)
            .where(
                SignalEvent.asset_symbol == asset_key,
                SignalEvent.timestamp >= cutoff,
            )
            .order_by(SignalEvent.timestamp.desc())
        )
        .scalars()
        .all()
    )

    if not snapshots:
        return {
            "asset": asset_key,
            "days": days,
            "status": "insufficient_data",
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    first = snapshots[0]
    last = snapshots[-1]

    start_score = first.signal_score or 0
    end_score = last.signal_score or 0
    score_change = end_score - start_score

    start_supply = first.total_supply or 0
    end_supply = last.total_supply or 0
    supply_change_pct = ((end_supply - start_supply) / start_supply * 100) if start_supply > 0 else 0

    scores = [s.signal_score or 0 for s in snapshots]
    avg_score = sum(scores) / len(scores) if scores else 0
    min_score = min(scores) if scores else 0
    max_score = max(scores) if scores else 0

    low_count = sum(1 for s in scores if s <= 33)
    mid_count = sum(1 for s in scores if 33 < s <= 66)
    high_count = sum(1 for s in scores if s > 66)

    by_severity: dict[str, int] = {}
    for e in events:
        sev = e.severity or "info"
        by_severity[sev] = by_severity.get(sev, 0) + 1

    by_type: dict[str, int] = {}
    for e in events:
        et = e.event_type or "unknown"
        by_type[et] = by_type.get(et, 0) + 1

    return {
        "asset": asset_key,
        "days": days,
        "status": "ok",
        "period": {
            "start": first.timestamp.isoformat() if first.timestamp else None,
            "end": last.timestamp.isoformat() if last.timestamp else None,
            "snapshot_count": len(snapshots),
            "event_count": len(events),
        },
        "signal_summary": {
            "start_score": start_score,
            "end_score": end_score,
            "change": round(score_change, 1),
            "avg": round(avg_score, 1),
            "min": min_score,
            "max": max_score,
            "low_band_duration_pct": round(low_count / len(scores) * 100, 1) if scores else 0,
            "mid_band_duration_pct": round(mid_count / len(scores) * 100, 1) if scores else 0,
            "high_band_duration_pct": round(high_count / len(scores) * 100, 1) if scores else 0,
        },
        "supply_summary": {
            "start": round(start_supply, 2),
            "end": round(end_supply, 2),
            "change_pct": round(supply_change_pct, 2),
        },
        "events_by_severity": by_severity,
        "events_by_type": by_type,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }