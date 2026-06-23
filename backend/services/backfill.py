"""Optional bounded historical backfill (synthetic, env-gated)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from database import AssetTrendSnapshot
from signal_engine.core import get_asset_by_symbol
from sources.defillama import DefiLlamaError, fetch_stablecoin_chart_points

SYNTHETIC_SOURCE = "synthetic_backfill"
MAX_BACKFILL_DAYS = 30
MIN_BACKFILL_DAYS = 7


def _day_start(dt: datetime) -> datetime:
    """Return the start of the day (midnight UTC) for the given datetime."""
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def run_backfill(db: Session, *, asset: str, days: int, _internal: bool = False) -> dict[str, Any]:
    if not _internal:
        from providers.settings import get_setting
        if not get_setting("allow_backfill", db):
            raise HTTPException(status_code=403, detail="Backfill is disabled. Enable in Settings (Features group).")

    sym = asset.strip().upper()
    selected = get_asset_by_symbol(sym)
    if selected is None or not bool(selected.get("enabled")):
        raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")

    days = max(MIN_BACKFILL_DAYS, min(days, MAX_BACKFILL_DAYS))

    try:
        chart_points = fetch_stablecoin_chart_points(symbol=sym, days=days)
    except DefiLlamaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    inserted = 0
    skipped_live = 0
    skipped_existing = 0

    for point in chart_points:
        ts = point["timestamp"]
        if ts < cutoff:
            continue
        day = _day_start(ts)

        live_exists = (
            db.query(AssetTrendSnapshot)
            .filter(
                AssetTrendSnapshot.asset_symbol == sym,
                AssetTrendSnapshot.timestamp >= day,
                AssetTrendSnapshot.timestamp < day + timedelta(days=1),
                AssetTrendSnapshot.source_status != SYNTHETIC_SOURCE,
            )
            .first()
        )
        if live_exists:
            skipped_live += 1
            continue

        bucket_id = int(day.timestamp() // 86400)
        existing_synth = (
            db.query(AssetTrendSnapshot)
            .filter(
                AssetTrendSnapshot.asset_symbol == sym,
                AssetTrendSnapshot.bucket_id == bucket_id,
                AssetTrendSnapshot.source_status == SYNTHETIC_SOURCE,
            )
            .first()
        )
        if existing_synth:
            skipped_existing += 1
            continue

        db.add(
            AssetTrendSnapshot(
                asset_symbol=sym,
                timestamp=day,
                bucket_id=bucket_id,
                total_supply=point.get("total_supply"),
                price=point.get("price"),
                depeg_index=int(point.get("depeg_index", 0)),
                signal_score=int(point.get("signal_score", 0)),
                signal_band=str(point.get("signal_band", "Normal")),
                concentration_score=int(point.get("concentration_score", 0)),
                data_confidence_label="Low",
                source_status=SYNTHETIC_SOURCE,
            )
        )
        inserted += 1

    db.commit()
    return {
        "ok": True,
        "asset": sym,
        "days_requested": days,
        "inserted": inserted,
        "skipped_live_day": skipped_live,
        "skipped_existing_synthetic": skipped_existing,
        "metadata": {"synthetic_backfill": True},
    }
