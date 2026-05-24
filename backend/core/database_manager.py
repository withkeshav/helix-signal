"""Dual-database manager — OLTP (Postgres/SQLite) + OLAP (ClickHouse).

Routes time-series queries to ClickHouse when available, falls back to OLTP
for local dev and CI environments. Batch writes use LZ4 compression.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session


class DatabaseManager:
    """Manages both OLTP (Postgres/SQLite) and OLAP (ClickHouse) connections."""

    def __init__(self):
        self.olap_host = os.getenv("CLICKHOUSE_HOST", "")
        self.olap_user = os.getenv("CLICKHOUSE_USER", "default")
        self.olap_password = os.getenv("CLICKHOUSE_PASSWORD", "")
        self.olap_port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
        self._olap_client = None

    def _get_olap_client(self):
        if not self.olap_host:
            return None
        if self._olap_client is None:
            try:
                import clickhouse_connect
                self._olap_client = clickhouse_connect.get_client(
                    host=self.olap_host,
                    port=self.olap_port,
                    username=self.olap_user,
                    password=self.olap_password,
                    compress="lz4",
                )
            except Exception:
                return None
        return self._olap_client

    @property
    def has_olap(self) -> bool:
        return bool(self.olap_host)

    def olap_query(self, query: str, params: dict | None = None) -> list[dict[str, Any]]:
        client = self._get_olap_client()
        if not client:
            return []
        try:
            result = client.query(query, parameters=params)
            columns = result.column_names
            return [dict(zip(columns, row)) for row in result.result_rows]
        except Exception:
            return []

    def write_snapshot_batch(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        client = self._get_olap_client()
        if not client:
            return
        try:
            client.insert(table, rows)
        except Exception:
            pass

    def get_trend_history(
        self, db: Session, *, asset_symbol: str, window_days: int = 30
    ) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

        if self.has_olap:
            rows = self.olap_query(
                "SELECT * FROM asset_trend_snapshots FINAL "
                "WHERE asset_symbol = {symbol:String} AND timestamp >= {cutoff:DateTime64(3)} "
                "ORDER BY timestamp ASC",
                params={"symbol": asset_symbol, "cutoff": cutoff},
            )
            if rows:
                return rows

        from database import AssetTrendSnapshot

        rows = (
            db.query(AssetTrendSnapshot)
            .filter(
                AssetTrendSnapshot.asset_symbol == asset_symbol,
                AssetTrendSnapshot.timestamp >= cutoff,
            )
            .order_by(AssetTrendSnapshot.timestamp.asc())
            .all()
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

        if self.has_olap:
            rows = self.olap_query(
                "SELECT * FROM chain_trend_snapshots FINAL "
                "WHERE asset_symbol = {symbol:String} AND timestamp >= {cutoff:DateTime64(3)} "
                "ORDER BY timestamp ASC",
                params={"symbol": asset_symbol, "cutoff": cutoff},
            )
            if rows:
                return rows

        from database import ChainTrendSnapshot

        rows = (
            db.query(ChainTrendSnapshot)
            .filter(
                ChainTrendSnapshot.asset_symbol == asset_symbol,
                ChainTrendSnapshot.timestamp >= cutoff,
            )
            .order_by(ChainTrendSnapshot.timestamp.asc())
            .all()
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
