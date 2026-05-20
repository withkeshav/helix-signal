"""SQLite retention pruning for trend and event tables."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from database import AssetTrendSnapshot, ChainTrendSnapshot, SignalEvent

HELIX_VERSION = "2.5.1"


def _retention_days(env_key: str, default: int) -> int:
    raw = os.getenv(env_key, str(default))
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def prune_old_history(db: Session) -> dict[str, int]:
    """Delete trend and event rows older than configured retention windows."""
    now = datetime.now(timezone.utc)
    trend_cutoff = now - timedelta(days=_retention_days("TREND_RETENTION_DAYS", 90))
    event_cutoff = now - timedelta(days=_retention_days("EVENT_RETENTION_DAYS", 30))

    asset_deleted = (
        db.query(AssetTrendSnapshot)
        .filter(AssetTrendSnapshot.timestamp < trend_cutoff)
        .delete(synchronize_session=False)
    )
    chain_deleted = (
        db.query(ChainTrendSnapshot)
        .filter(ChainTrendSnapshot.timestamp < trend_cutoff)
        .delete(synchronize_session=False)
    )
    events_deleted = (
        db.query(SignalEvent).filter(SignalEvent.timestamp < event_cutoff).delete(synchronize_session=False)
    )
    db.commit()
    return {
        "asset_trend_rows": asset_deleted,
        "chain_trend_rows": chain_deleted,
        "signal_event_rows": events_deleted,
    }
