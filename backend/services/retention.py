"""Data retention pruning — OLTP + OLAP aware."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session
from structlog import get_logger

from database import (
    AssetTrendSnapshot,
    ChainTrendSnapshot,
    ForecastPoint,
    ForecastRun,
    OsintArticle,
    SignalEvent,
)
from backend.core.database_manager import dbm

log = get_logger(__name__)

HELIX_VERSION = "3.5.1"

RETENTION_DEFAULTS: dict[str, int] = {
    "asset_trend_snapshots": 90,
    "chain_trend_snapshots": 90,
    "forecast_points": 30,
    "signal_events": 180,
    "osint_articles": 30,
}


def _retention_days(table: str) -> int:
    env_map = {
        "asset_trend_snapshots": "TREND_RETENTION_DAYS",
        "chain_trend_snapshots": "CHAIN_TREND_RETENTION_DAYS",
        "forecast_points": "FORECAST_RETENTION_DAYS",
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
    forecast_cutoff = now - timedelta(days=_retention_days("forecast_points"))

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
    forecast_points_deleted = (
        db.query(ForecastPoint)
        .filter(ForecastPoint.created_at < forecast_cutoff)
        .delete(synchronize_session=False)
    )
    db.flush()
    forecast_runs_orphaned = (
        db.query(ForecastRun)
        .filter(
            ForecastRun.id.not_in(
                db.query(ForecastPoint.run_id)
            )
        )
        .delete(synchronize_session=False)
    )

    db.commit()

    result = {
        "asset_trend_rows": asset_deleted,
        "chain_trend_rows": chain_deleted,
        "signal_event_rows": events_deleted,
        "osint_article_rows": osint_deleted,
        "forecast_point_rows": forecast_points_deleted,
        "forecast_run_orphans": forecast_runs_orphaned,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
    }

    if dbm.has_olap:
        result["clickhouse"] = _prune_olap(now)

    log.info("retention_pruned", **result)
    return result


def _prune_olap(now: datetime) -> dict[str, Any]:
    try:
        for table in ("asset_trend_snapshots", "chain_trend_snapshots", "forecast_points"):
            retention = _retention_days(table)
            cutoff = (now - timedelta(days=retention)).strftime("%Y-%m-%d %H:%M:%S")
            dbm.olap_query(
                f"ALTER TABLE {table} DELETE WHERE timestamp < parseDateTime64BestEffort('{cutoff}') NO DELAY",
            )
        return {"status": "pruned"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def prune_all(db: Session) -> dict[str, Any]:
    return prune_old_history(db)
