"""Persist and read data-quality snapshots (WO-BE-6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session
from structlog import get_logger

from data_quality.metrics import DataQualityMetrics, get_all_data_quality_metrics
from database import AssetTrendSnapshot, DataQualitySnapshot

log = get_logger(__name__)

BUCKET_SECONDS = 300  # 5-minute buckets


def compute_bucket_fill_rates(db: Session, *, window_hours: int = 24) -> dict[str, Any]:
    """Actual vs expected 5-min buckets per asset over the lookback window."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    expected_buckets = max(1, int((window_hours * 3600) / BUCKET_SECONDS))

    rows = db.execute(
        select(
            AssetTrendSnapshot.asset_symbol,
            func.count(func.distinct(AssetTrendSnapshot.bucket_id)).label("actual"),
        )
        .where(AssetTrendSnapshot.timestamp >= cutoff)
        .group_by(AssetTrendSnapshot.asset_symbol)
    ).all()

    by_asset: dict[str, dict[str, Any]] = {}
    for asset_symbol, actual in rows:
        actual = int(actual or 0)
        fill_pct = round(min(100.0, (actual / expected_buckets) * 100.0), 2)
        by_asset[asset_symbol] = {
            "actual_buckets": actual,
            "expected_buckets": expected_buckets,
            "fill_rate_pct": fill_pct,
        }

    return {
        "window_hours": window_hours,
        "expected_buckets_per_asset": expected_buckets,
        "by_asset": by_asset,
    }


def build_snapshot_payload(db: Session) -> dict[str, Any]:
    """Compute full snapshot body (used by daily job and fallback)."""
    overall = get_all_data_quality_metrics(db)
    source_metrics = DataQualityMetrics.get_source_quality_metrics(db)
    asset_metrics = DataQualityMetrics.get_asset_data_quality(db)
    bucket_fill = compute_bucket_fill_rates(db)

    return {
        "overall_score": overall.get("overall_score", 0),
        "source_health": source_metrics,
        "bucket_fill_rates": bucket_fill,
        "asset_metrics": asset_metrics,
        "components": overall.get("components", {}),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_data_quality_snapshot(db: Session) -> DataQualitySnapshot:
    payload = build_snapshot_payload(db)
    row = DataQualitySnapshot(
        overall_score=float(payload["overall_score"]),
        source_health=payload["source_health"],
        bucket_fill_rates=payload["bucket_fill_rates"],
        asset_metrics=payload["asset_metrics"],
        generated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log.info("data_quality.snapshot_written", overall_score=row.overall_score, id=row.id)
    return row


def get_latest_snapshot(db: Session) -> DataQualitySnapshot | None:
    return db.execute(
        select(DataQualitySnapshot).order_by(desc(DataQualitySnapshot.generated_at)).limit(1)
    ).scalar_one_or_none()


def get_snapshot_history(db: Session, *, limit: int = 30) -> list[DataQualitySnapshot]:
    return list(
        db.execute(
            select(DataQualitySnapshot)
            .order_by(desc(DataQualitySnapshot.generated_at))
            .limit(min(limit, 90))
        ).scalars().all()
    )


def snapshot_to_summary(row: DataQualitySnapshot | None, *, live_fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    """Public summary shape for GET /api/data-quality/summary."""
    if row is None:
        if live_fallback is None:
            return {
                "available": False,
                "overall_score": 0,
                "generated_at": None,
                "source_health": {},
                "bucket_fill_rates": {},
                "asset_metrics": {},
                "history": [],
            }
        return {**live_fallback, "available": True, "from_snapshot": False}

    history_rows = []
    return {
        "available": True,
        "from_snapshot": True,
        "overall_score": row.overall_score,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "source_health": row.source_health,
        "bucket_fill_rates": row.bucket_fill_rates,
        "asset_metrics": row.asset_metrics,
        "history": history_rows,
    }


def get_quality_summary(db: Session) -> dict[str, Any]:
    """Read-open summary: prefer latest snapshot; compute live if none."""
    row = get_latest_snapshot(db)
    if row is not None:
        history = [
            {"generated_at": s.generated_at.isoformat(), "overall_score": s.overall_score}
            for s in get_snapshot_history(db, limit=30)
        ]
        out = snapshot_to_summary(row)
        out["history"] = history
        return out

    payload = build_snapshot_payload(db)
    history = []
    return {
        "available": True,
        "from_snapshot": False,
        "overall_score": payload["overall_score"],
        "generated_at": payload["generated_at"],
        "source_health": payload["source_health"],
        "bucket_fill_rates": payload["bucket_fill_rates"],
        "asset_metrics": payload["asset_metrics"],
        "history": history,
    }


def run_data_quality_snapshot_job(db: Session) -> dict[str, Any]:
    row = write_data_quality_snapshot(db)
    return {
        "id": row.id,
        "overall_score": row.overall_score,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
    }
