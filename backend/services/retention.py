"""Data retention pruning — OLTP aware."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session
from structlog import get_logger

from database import (
    AiNarrativeHistory,
    AiUsage,
    AssetTrendSnapshot,
    ChainTrendSnapshot,
    CollateralSnapshot,
    FiatReserveSnapshot,
    ForecastPoint,
    ForecastRun,
    FundingRateSnapshot,
    OsintArticle,
    SettingsAuditLog,
    SignalEvent,
    SourceUsage,
    WhaleActivitySnapshot,
    YieldBearingSnapshot,
)

log = get_logger(__name__)

HELIX_VERSION = "4.2.0"

_LAST_PRUNE_RESULT: dict[str, Any] | None = None

# (result_key, model, timestamp_col, settings_key, env_key, default_days, hypertable)
RETENTION_TABLES: list[tuple[str, Any, str, str, str, int, bool]] = [
    ("asset_trend_rows", AssetTrendSnapshot, "timestamp", "retention_asset_trend_snapshots_days", "TREND_RETENTION_DAYS", 90, True),
    ("chain_trend_rows", ChainTrendSnapshot, "timestamp", "retention_chain_trend_snapshots_days", "CHAIN_TREND_RETENTION_DAYS", 90, True),
    ("signal_event_rows", SignalEvent, "timestamp", "retention_signal_events_days", "EVENT_RETENTION_DAYS", 180, False),
    ("osint_article_rows", OsintArticle, "fetched_at", "retention_osint_articles_days", "OSINT_RETENTION_DAYS", 30, False),
    ("funding_rate_rows", FundingRateSnapshot, "timestamp", "retention_funding_rate_snapshots_days", "RETENTION_FUNDING_RATE_SNAPSHOTS_DAYS", 30, True),
    ("yield_bearing_rows", YieldBearingSnapshot, "timestamp", "retention_yield_bearing_snapshots_days", "RETENTION_YIELD_BEARING_SNAPSHOTS_DAYS", 180, True),
    ("collateral_rows", CollateralSnapshot, "timestamp", "retention_collateral_snapshots_days", "RETENTION_COLLATERAL_SNAPSHOTS_DAYS", 180, True),
    ("whale_activity_rows", WhaleActivitySnapshot, "timestamp", "retention_whale_activity_snapshots_days", "RETENTION_WHALE_ACTIVITY_SNAPSHOTS_DAYS", 180, True),
    ("fiat_reserve_rows", FiatReserveSnapshot, "created_at", "retention_fiat_reserve_snapshots_days", "RETENTION_FIAT_RESERVE_SNAPSHOTS_DAYS", 730, False),
    ("ai_narrative_rows", AiNarrativeHistory, "created_at", "retention_ai_narrative_history_days", "RETENTION_AI_NARRATIVE_HISTORY_DAYS", 90, False),
    ("settings_audit_rows", SettingsAuditLog, "created_at", "retention_settings_audit_log_days", "RETENTION_SETTINGS_AUDIT_LOG_DAYS", 365, False),
    ("source_usage_rows", SourceUsage, "created_at", "retention_source_usage_days", "RETENTION_SOURCE_USAGE_DAYS", 400, False),
    ("ai_usage_rows", AiUsage, "created_at", "retention_ai_usage_days", "RETENTION_AI_USAGE_DAYS", 400, False),
]


def get_last_prune_result() -> dict[str, Any] | None:
    return _LAST_PRUNE_RESULT


def _retention_days(db: Session, settings_key: str, env_key: str, default: int) -> int:
    try:
        from providers.settings import get_setting

        raw = get_setting(settings_key, db)
        if raw is not None:
            return max(1, int(raw))
    except (TypeError, ValueError):
        pass
    raw_env = os.getenv(env_key, str(default))
    try:
        return max(1, int(raw_env))
    except ValueError:
        return default


def _is_postgres(db: Session) -> bool:
    bind = db.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def _prune_table(db: Session, model: Any, ts_col: str, cutoff: datetime, hypertable: bool) -> int:
    col = getattr(model, ts_col)
    if hypertable and _is_postgres(db):
        table = model.__tablename__
        result = db.execute(
            text(f"SELECT count(*) FROM show_chunks('{table}', older_than => :cutoff)"),
            {"cutoff": cutoff},
        )
        chunk_count = int(result.scalar() or 0)
        if chunk_count:
            db.execute(
                text(f"SELECT drop_chunks('{table}', older_than => :cutoff)"),
                {"cutoff": cutoff},
            )
        return chunk_count
    deleted = db.execute(delete(model).where(col < cutoff)).rowcount
    return deleted or 0


def _prune_forecast_runs(db: Session, cutoff: datetime) -> tuple[int, int]:
    old_run_ids = list(
        db.execute(select(ForecastRun.id).where(ForecastRun.generated_at < cutoff)).scalars().all()
    )
    if not old_run_ids:
        return 0, 0
    pts = db.execute(delete(ForecastPoint).where(ForecastPoint.run_id.in_(old_run_ids))).rowcount or 0
    runs = db.execute(delete(ForecastRun).where(ForecastRun.id.in_(old_run_ids))).rowcount or 0
    return runs, pts


def _prune_duckdb_fred(days: int) -> int:
    try:
        from core.olap import get_duckdb

        con = get_duckdb()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        before = con.execute("SELECT COUNT(*) FROM fred_yields WHERE date < ?", [cutoff]).fetchone()[0]
        if before:
            con.execute("DELETE FROM fred_yields WHERE date < ?", [cutoff])
        return int(before or 0)
    except Exception:
        log.debug("retention.duckdb_fred_skipped", exc_info=True)
        return 0


def prune_old_history(db: Session) -> dict[str, Any]:
    global _LAST_PRUNE_RESULT
    now = datetime.now(timezone.utc)
    result: dict[str, Any] = {"generated_at": now.isoformat().replace("+00:00", "Z")}

    for key, model, ts_col, settings_key, env_key, default, hypertable in RETENTION_TABLES:
        days = _retention_days(db, settings_key, env_key, default)
        cutoff = now - timedelta(days=days)
        result[key] = _prune_table(db, model, ts_col, cutoff, hypertable)

    forecast_days = _retention_days(
        db, "retention_forecast_runs_days", "RETENTION_FORECAST_RUNS_DAYS", 180
    )
    fc_cutoff = now - timedelta(days=forecast_days)
    runs, pts = _prune_forecast_runs(db, fc_cutoff)
    result["forecast_run_rows"] = runs
    result["forecast_point_rows"] = pts

    fred_days = _retention_days(db, "retention_fred_yields_days", "RETENTION_FRED_YIELDS_DAYS", 730)
    result["fred_yields_rows"] = _prune_duckdb_fred(fred_days)

    db.commit()
    _LAST_PRUNE_RESULT = result
    log.info("retention_pruned", **result)
    return result


def prune_all(db: Session) -> dict[str, Any]:
    return prune_old_history(db)
