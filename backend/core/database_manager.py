"""Database manager — OLTP (Postgres/SQLite) connection manager."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


class DatabaseManager:
    """Manages OLTP (Postgres/SQLite) connections."""

    def __init__(self):
        pass

    def get_trend_history(
        self, db: Session, *, asset_symbol: str, window_days: int = 30
    ) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

        from database import AssetTrendSnapshot

        rows = (
            db.execute(
                select(AssetTrendSnapshot)
                .where(
                    AssetTrendSnapshot.asset_symbol == asset_symbol,
                    AssetTrendSnapshot.timestamp >= cutoff,
                )
                .order_by(AssetTrendSnapshot.timestamp.asc())
            ).scalars().all()
        )
        return [
            {
                "timestamp": r.timestamp,
                "total_supply": r.total_supply,
                "price": r.price,
                "depeg_index": r.depeg_index,
                "signal_score": r.signal_score,
                "signal_band": r.signal_band,
                "concentration_score": r.concentration_score,
                "data_confidence_label": r.data_confidence_label,
                "source_status": r.source_status,
            }
            for r in rows
        ]

    def get_chain_trend_history(
        self, db: Session, *, asset_symbol: str, window_days: int = 30
    ) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

        from database import ChainTrendSnapshot

        rows = (
            db.execute(
                select(ChainTrendSnapshot)
                .where(
                    ChainTrendSnapshot.asset_symbol == asset_symbol,
                    ChainTrendSnapshot.timestamp >= cutoff,
                )
                .order_by(ChainTrendSnapshot.timestamp.asc())
            ).scalars().all()
        )
        return [
            {
                "chain_key": r.chain_key,
                "chain_name": r.chain_name,
                "timestamp": r.timestamp,
                "supply": r.supply,
                "supply_share_pct": r.supply_share_pct,
                "chain_tvl": r.chain_tvl,
                "chain_signal_score": r.chain_signal_score,
                "chain_signal_band": r.chain_signal_band,
                "data_confidence_score": r.data_confidence_score,
            }
            for r in rows
        ]


dbm = DatabaseManager()
