"""Data retention pruning — OLTP aware."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session
from structlog import get_logger

from database import (
    AssetTrendSnapshot,
    ChainTrendSnapshot,
    OsintArticle,
    SignalEvent,
)

log = get_logger(__name__)

HELIX_VERSION = "3.9.1"

RETENTION_DEFAULTS: dict[str, int] = {
    "asset_trend_snapshots": 90,
    "chain_trend_snapshots": 90,
    "signal_events": 180,
    "osint_articles": 30,
}


def _retention_days(table: str) -> int:
    env_map = {
        "asset_trend_snapshots": "TREND_RETENTION_DAYS",
        "chain_trend_snapshots": "CHAIN_TREND_RETENTION_DAYS",
        "signal_events": "EVENT_RETENTION_DAYS",
        "osint_articles": "OSINT_RETENTION_DAYS",
    }
    env_key = env_map.get(table, f"RETENTION_{table.upper()}")
    default = RETENTION_DEFAULTS.get(table, 90)
    raw = os.getenv(env_key, str(default))
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def prune_old_history(db: Session) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    trend_cutoff = now - timedelta(days=_retention_days("asset_trend_snapshots"))
    event_cutoff = now - timedelta(days=_retention_days("signal_events"))
    osint_cutoff = now - timedelta(days=_retention_days("osint_articles"))

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
        db.query(SignalEvent)
        .filter(SignalEvent.timestamp < event_cutoff)
        .delete(synchronize_session=False)
    )
    osint_deleted = (
        db.query(OsintArticle)
        .filter(OsintArticle.fetched_at < osint_cutoff)
        .delete(synchronize_session=False)
    )

    db.commit()

    result = {
        "asset_trend_rows": asset_deleted,
        "chain_trend_rows": chain_deleted,
        "signal_event_rows": events_deleted,
        "osint_article_rows": osint_deleted,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
    }

    log.info("retention_pruned", **result)
    return result


def prune_all(db: Session) -> dict[str, Any]:
    return prune_old_history(db)
