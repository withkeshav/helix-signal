from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session
from structlog import get_logger

from core.olap import get_duckdb

log = get_logger(__name__)


def _table_columns(table: str) -> list[str]:
    con = get_duckdb()
    cols = con.execute(f"DESCRIBE {table}").fetchall()
    return [row[0] for row in cols]


def compute_yield_capital_flight_correlations(asset_symbol: str | None = None) -> list[dict[str, Any]]:
    con = get_duckdb()
    try:
        con.execute("SELECT 1 FROM fred_yields LIMIT 1")
    except Exception:
        return []

    asset_filter = "AND t.asset_symbol = ?" if asset_symbol else ""
    params = [asset_symbol] if asset_symbol else []

    rows = con.execute(
        f"""
        SELECT
            t.asset_symbol,
            f.series_id AS yield_series,
            f.series_name AS yield_name,
            corr(t.total_supply, f.value) AS supply_yield_corr,
            corr(t.price, f.value) AS price_yield_corr,
            corr(t.depeg_index, f.value) AS depeg_yield_corr,
            count(*) AS sample_count
        FROM asset_trend_snapshots t
        JOIN fred_yields f
            ON f.date = CAST(t.timestamp AS DATE)
        WHERE f.value IS NOT NULL
          AND t.total_supply IS NOT NULL
          {asset_filter}
        GROUP BY t.asset_symbol, f.series_id, f.series_name
        ORDER BY t.asset_symbol, f.series_id
        """,
        params,
    ).fetchall()

    return [
        {
            "asset_symbol": r[0],
            "yield_series": r[1],
            "yield_name": r[2],
            "supply_yield_correlation": r[3],
            "price_yield_correlation": r[4],
            "depeg_yield_correlation": r[5],
            "sample_count": r[6],
        }
        for r in rows
    ]


def sync_sqlite_to_duckdb(db: Session) -> dict[str, int]:
    con = get_duckdb()
    counts: dict[str, int] = {}

    tables = {
        "asset_chain_snapshots": "SELECT * FROM asset_chain_snapshots",
        "source_status": "SELECT * FROM source_status",
        "asset_trend_snapshots": "SELECT * FROM asset_trend_snapshots WHERE timestamp >= :cutoff",
        "signal_events": "SELECT * FROM signal_events WHERE timestamp >= :cutoff",
    }

    cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    for table, query in tables.items():
        duck_cols = _table_columns(table)
        sql_cols = ", ".join(f'"{c}"' for c in duck_cols)
        placeholders = ", ".join(f":{c}" for c in duck_cols)

        if ":cutoff" in query:
            rows = db.execute(text(query), {"cutoff": cutoff}).mappings().all()
        else:
            rows = db.execute(text(query)).mappings().all()

        if not rows:
            counts[table] = 0
            continue

        con.execute(f"DELETE FROM {table}")
        for row in rows:
            row_dict = dict(row)
            filtered = {c: row_dict.get(c) for c in duck_cols if c in row_dict}
            con.execute(
                f"INSERT INTO {table} ({sql_cols}) VALUES ({placeholders})",
                filtered,
            )
        counts[table] = len(rows)

    log.info("olap_sync_complete", tables=counts)
    return counts


def compute_duckdb_correlations(asset_symbol: str | None = None) -> list[dict[str, Any]]:
    con = get_duckdb()
    where = "WHERE asset_symbol = ?" if asset_symbol else ""
    params = [asset_symbol] if asset_symbol else []

    rows = con.execute(
        f"""
        SELECT
            asset_symbol,
            corr(price, total_supply) AS price_supply_corr,
            corr(price, depeg_index) AS price_depeg_corr,
            corr(total_supply, depeg_index) AS supply_depeg_corr,
            corr(price, concentration_score) AS price_concentration_corr,
            count(*) AS sample_count
        FROM asset_trend_snapshots
        {where}
        GROUP BY asset_symbol
        ORDER BY sample_count DESC
        """,
        params,
    ).fetchall()

    return [
        {
            "asset_symbol": r[0],
            "price_supply_correlation": r[1],
            "price_depeg_correlation": r[2],
            "supply_depeg_correlation": r[3],
            "price_concentration_correlation": r[4],
            "sample_count": r[5],
        }
        for r in rows
    ]


def compute_cross_chain_correlations(asset_symbol: str | None = None) -> list[dict[str, Any]]:
    con = get_duckdb()
    where = "WHERE asset_symbol = ?" if asset_symbol else ""
    params = [asset_symbol] if asset_symbol else []

    rows = con.execute(
        f"""
        SELECT
            a.asset_symbol,
            a.chain_name,
            b.chain_name AS other_chain,
            corr(a.supply_current, b.supply_current) AS supply_corr,
            corr(a.price, b.price) AS price_corr
        FROM asset_chain_snapshots a
        JOIN asset_chain_snapshots b
            ON a.asset_symbol = b.asset_symbol
            AND a.chain_name < b.chain_name
        {where}
        GROUP BY a.asset_symbol, a.chain_name, b.chain_name
        ORDER BY a.asset_symbol, a.chain_name
        """,
        params,
    ).fetchall()

    return [
        {
            "asset_symbol": r[0],
            "chain": r[1],
            "other_chain": r[2],
            "supply_correlation": r[3],
            "price_correlation": r[4],
        }
        for r in rows
    ]
