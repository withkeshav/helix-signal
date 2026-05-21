from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import duckdb


def _get_sqlite_path() -> str:
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("sqlite:///"):
        return db_url[len("sqlite:///"):]
    return str(Path(__file__).resolve().parent / "helix.db")


_duck: duckdb.DuckDBPyConnection | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    global _duck
    if _duck is None:
        _duck = duckdb.connect(":memory:")
        sqlite_path = _get_sqlite_path()
        if os.path.isfile(sqlite_path):
            _duck.execute(f"ATTACH '{sqlite_path}' AS helix_db (TYPE SQLITE, READ_ONLY)")
    return _duck


def run_query(sql: str) -> list[dict[str, Any]]:
    con = get_connection()
    result = con.execute(sql)
    columns = [desc[0] for desc in result.description] if result.description else []
    return [dict(zip(columns, row)) for row in result.fetchall()]


def _rolling_stats_sqlalchemy(asset_symbol: str, window_days: int) -> dict[str, Any]:
    from database import AssetTrendSnapshot, SessionLocal

    limit = window_days * 288
    db = SessionLocal()
    try:
        rows = (
            db.query(AssetTrendSnapshot.total_supply)
            .filter(
                AssetTrendSnapshot.asset_symbol == asset_symbol.upper(),
                AssetTrendSnapshot.total_supply.isnot(None),
            )
            .order_by(AssetTrendSnapshot.timestamp.desc())
            .limit(limit)
            .all()
        )
        values = [r[0] for r in rows]
    finally:
        db.close()
    if len(values) < 2:
        return {"mean": None, "std": None, "count": 0}
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std = variance**0.5
    return {"mean": round(mean, 2), "std": round(std, 2), "count": len(values)}


def compute_supply_rolling_stats(asset_symbol: str, window_days: int = 30) -> dict[str, Any]:
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("postgresql"):
        try:
            return _rolling_stats_sqlalchemy(asset_symbol, window_days)
        except Exception:
            return {"mean": None, "std": None, "count": 0}
    try:
        sym = asset_symbol.replace("'", "")
        rows = run_query(f"""
            SELECT total_supply
            FROM helix_db.asset_trend_snapshots
            WHERE asset_symbol = '{sym}'
              AND total_supply IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT {window_days * 288}
        """)
        values = [r["total_supply"] for r in rows]
        if len(values) < 2:
            return {"mean": None, "std": None, "count": 0}
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std = variance ** 0.5
        return {"mean": round(mean, 2), "std": round(std, 2), "count": len(values)}
    except Exception:
        return {"mean": None, "std": None, "count": 0}
