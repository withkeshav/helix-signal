"""Long-range reads for v4 snapshot series — uses Timescale continuous aggregates on PostgreSQL."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database import (
    CollateralSnapshot,
    FundingRateSnapshot,
    WhaleActivitySnapshot,
    YieldBearingSnapshot,
)

AGGREGATE_MIN_DAYS = 7
_LONG_RANGE_WINDOWS = frozenset({"30d", "90d"})


def _is_postgres(db: Session) -> bool:
    bind = db.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _score_band(score: float) -> str:
    if score >= 70:
        return "risk"
    if score >= 40:
        return "watch"
    return "normal"


def fetch_asset_trend_history(
    db: Session,
    *,
    asset_symbol: str,
    window: str,
) -> list[dict[str, Any]] | None:
    """Return hourly aggregate trend rows for long windows on PostgreSQL."""
    wl = window.strip().lower()
    if wl not in _LONG_RANGE_WINDOWS or not _is_postgres(db):
        return None
    from utils import window_delta

    cutoff = datetime.now(timezone.utc) - window_delta(wl)
    sym = asset_symbol.upper()
    rows = db.execute(
        text(
            """
            SELECT bucket, avg_signal_score, max_signal_score, sample_count
            FROM asset_signal_1h
            WHERE asset_symbol = :sym AND bucket >= :cutoff
            ORDER BY bucket ASC
            """
        ),
        {"sym": sym, "cutoff": cutoff},
    ).mappings().all()
    if not rows:
        return None
    return [
        {
            "timestamp": r["bucket"],
            "total_supply": None,
            "price": None,
            "depeg_index": 0,
            "signal_score": int(round(float(r["avg_signal_score"] or 0))),
            "signal_band": _score_band(float(r["avg_signal_score"] or 0)),
            "concentration_score": 0,
            "data_confidence_label": "Low",
            "source": "aggregate",
            "sample_count": r["sample_count"],
        }
        for r in rows
    ]


def fetch_funding_rate_history(
    db: Session,
    *,
    days: int,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    cutoff = _cutoff(days)
    if days >= AGGREGATE_MIN_DAYS and _is_postgres(db):
        stmt = """
            SELECT bucket, exchange, symbol, avg_funding_rate, avg_annualized_rate, sample_count
            FROM funding_rate_hourly
            WHERE bucket >= :cutoff
        """
        params: dict[str, Any] = {"cutoff": cutoff}
        if symbol:
            stmt += " AND symbol = :symbol"
            params["symbol"] = symbol.upper()
        stmt += " ORDER BY bucket ASC"
        rows = db.execute(text(stmt), params).mappings().all()
        return [
            {
                "timestamp": r["bucket"],
                "exchange": r["exchange"],
                "symbol": r["symbol"],
                "funding_rate": r["avg_funding_rate"],
                "annualized_rate": r["avg_annualized_rate"],
                "sample_count": r["sample_count"],
                "source": "aggregate",
            }
            for r in rows
        ]

    stmt = select(FundingRateSnapshot).where(FundingRateSnapshot.timestamp >= cutoff)
    if symbol:
        stmt = stmt.where(FundingRateSnapshot.symbol == symbol.upper())
    stmt = stmt.order_by(FundingRateSnapshot.timestamp.asc())
    return [
        {
            "timestamp": r.timestamp,
            "exchange": r.exchange,
            "symbol": r.symbol,
            "funding_rate": r.funding_rate,
            "annualized_rate": r.annualized_rate,
            "sample_count": 1,
            "source": "raw",
        }
        for r in db.execute(stmt).scalars().all()
    ]


def fetch_yield_bearing_history(db: Session, *, asset_symbol: str, days: int) -> list[dict[str, Any]]:
    sym = asset_symbol.upper()
    cutoff = _cutoff(days)
    if days >= AGGREGATE_MIN_DAYS and _is_postgres(db):
        rows = db.execute(
            text(
                """
                SELECT bucket, asset_symbol, avg_current_apy, avg_apy_7d_avg,
                       avg_funding_rate_current, avg_insurance_fund_usd, sample_count
                FROM yield_bearing_daily
                WHERE bucket >= :cutoff AND asset_symbol = :sym
                ORDER BY bucket ASC
                """
            ),
            {"cutoff": cutoff, "sym": sym},
        ).mappings().all()
        return [
            {
                "timestamp": r["bucket"],
                "asset_symbol": r["asset_symbol"],
                "current_apy": r["avg_current_apy"],
                "apy_7d_avg": r["avg_apy_7d_avg"],
                "funding_rate_current": r["avg_funding_rate_current"],
                "insurance_fund_usd": r["avg_insurance_fund_usd"],
                "sample_count": r["sample_count"],
                "source": "aggregate",
            }
            for r in rows
        ]

    rows = db.execute(
        select(YieldBearingSnapshot)
        .where(YieldBearingSnapshot.asset_symbol == sym, YieldBearingSnapshot.timestamp >= cutoff)
        .order_by(YieldBearingSnapshot.timestamp.asc())
    ).scalars().all()
    return [
        {
            "timestamp": r.timestamp,
            "asset_symbol": r.asset_symbol,
            "current_apy": r.current_apy,
            "apy_7d_avg": r.apy_7d_avg,
            "funding_rate_current": r.funding_rate_current,
            "insurance_fund_usd": r.insurance_fund_usd,
            "sample_count": 1,
            "source": "raw",
        }
        for r in rows
    ]


def fetch_collateral_history(db: Session, *, asset_symbol: str, days: int) -> list[dict[str, Any]]:
    sym = asset_symbol.upper()
    cutoff = _cutoff(days)
    if days >= AGGREGATE_MIN_DAYS and _is_postgres(db):
        rows = db.execute(
            text(
                """
                SELECT bucket, asset_symbol, avg_collateral_ratio, avg_liquidation_queue_usd,
                       avg_collateral_health_score, sample_count
                FROM collateral_daily
                WHERE bucket >= :cutoff AND asset_symbol = :sym
                ORDER BY bucket ASC
                """
            ),
            {"cutoff": cutoff, "sym": sym},
        ).mappings().all()
        return [
            {
                "timestamp": r["bucket"],
                "asset_symbol": r["asset_symbol"],
                "collateral_ratio": r["avg_collateral_ratio"],
                "liquidation_queue_usd": r["avg_liquidation_queue_usd"],
                "collateral_health_score": r["avg_collateral_health_score"],
                "sample_count": r["sample_count"],
                "source": "aggregate",
            }
            for r in rows
        ]

    rows = db.execute(
        select(CollateralSnapshot)
        .where(CollateralSnapshot.asset_symbol == sym, CollateralSnapshot.timestamp >= cutoff)
        .order_by(CollateralSnapshot.timestamp.asc())
    ).scalars().all()
    return [
        {
            "timestamp": r.timestamp,
            "asset_symbol": r.asset_symbol,
            "collateral_ratio": r.collateral_ratio,
            "liquidation_queue_usd": r.liquidation_queue_usd,
            "collateral_health_score": r.collateral_health_score,
            "sample_count": 1,
            "source": "raw",
        }
        for r in rows
    ]


def fetch_whale_activity_history(db: Session, *, asset_symbol: str, days: int) -> list[dict[str, Any]]:
    sym = asset_symbol.upper()
    cutoff = _cutoff(days)
    if days >= AGGREGATE_MIN_DAYS and _is_postgres(db):
        rows = db.execute(
            text(
                """
                SELECT bucket, asset_symbol, chain, avg_top10_holder_pct,
                       avg_exchange_inflow_usd_24h, total_large_transfers, sample_count
                FROM whale_activity_daily
                WHERE bucket >= :cutoff AND asset_symbol = :sym
                ORDER BY bucket ASC
                """
            ),
            {"cutoff": cutoff, "sym": sym},
        ).mappings().all()
        return [
            {
                "timestamp": r["bucket"],
                "asset_symbol": r["asset_symbol"],
                "chain": r["chain"],
                "top10_holder_pct": r["avg_top10_holder_pct"],
                "exchange_inflow_usd_24h": r["avg_exchange_inflow_usd_24h"],
                "large_transfer_count_24h": r["total_large_transfers"],
                "sample_count": r["sample_count"],
                "source": "aggregate",
            }
            for r in rows
        ]

    rows = db.execute(
        select(WhaleActivitySnapshot)
        .where(WhaleActivitySnapshot.asset_symbol == sym, WhaleActivitySnapshot.timestamp >= cutoff)
        .order_by(WhaleActivitySnapshot.timestamp.asc())
    ).scalars().all()
    return [
        {
            "timestamp": r.timestamp,
            "asset_symbol": r.asset_symbol,
            "chain": r.chain,
            "top10_holder_pct": r.top10_holder_pct,
            "exchange_inflow_usd_24h": r.exchange_inflow_usd_24h,
            "large_transfer_count_24h": r.large_transfer_count_24h,
            "sample_count": 1,
            "source": "raw",
        }
        for r in rows
    ]
