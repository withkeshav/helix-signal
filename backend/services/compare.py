"""Cross-asset trend comparison."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import AssetTrendSnapshot
from signal_engine.core import get_asset_by_symbol
from utils import window_delta

_ALLOWED_WINDOWS = frozenset({"24h", "7d", "30d", "90d"})


def build_compare_payload(db: Session, *, assets_csv: str, window: str) -> dict[str, Any]:
    w = window.strip().lower()
    if w not in _ALLOWED_WINDOWS:
        raise HTTPException(status_code=400, detail="Invalid window. Use 24h, 7d, 30d, or 90d.")

    symbols = [s.strip().upper() for s in assets_csv.split(",") if s.strip()]
    if len(symbols) < 2:
        raise HTTPException(status_code=400, detail="Provide at least two assets, e.g. assets=USDT,USDC")
    if len(symbols) > 8:
        raise HTTPException(status_code=400, detail="At most eight assets per compare request.")

    for sym in symbols:
        selected = get_asset_by_symbol(sym)
        if selected is None or not bool(selected.get("enabled")):
            raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")

    now = datetime.now(timezone.utc)
    cutoff = now - window_delta(w)

    series: dict[str, list[dict[str, Any]]] = {}
    all_timestamps: set[datetime] = set()

    for sym in symbols:
        rows = (
            db.execute(
                select(AssetTrendSnapshot)
                .where(
                    AssetTrendSnapshot.asset_symbol == sym,
                    AssetTrendSnapshot.timestamp >= cutoff,
                    AssetTrendSnapshot.source_status != "synthetic_backfill",
                )
                .order_by(AssetTrendSnapshot.timestamp.asc())
            )
            .scalars()
            .all()
        )
        points: list[dict[str, Any]] = []
        for r in rows:
            ts = r.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            all_timestamps.add(ts)
            points.append(
                {
                    "timestamp": ts.isoformat().replace("+00:00", "Z"),
                    "signal_score": int(r.signal_score),
                    "depeg_index": int(r.depeg_index),
                    "total_supply": r.total_supply,
                    "signal_band": str(r.signal_band),
                }
            )
        series[sym] = points

    aligned_axis = sorted(all_timestamps)
    alignment_note = (
        "Series use stored snapshot timestamps; gaps mean missing buckets for that asset in the window."
    )

    return {
        "window": w,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "assets": symbols,
        "series": series,
        "aligned_timestamps": [t.isoformat().replace("+00:00", "Z") for t in aligned_axis],
        "alignment_note": alignment_note,
    }
