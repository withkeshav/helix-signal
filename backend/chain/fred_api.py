from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from structlog import get_logger

from core.olap import get_duckdb

log = get_logger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred"

SERIES_MAP: dict[str, str] = {
    "DGS1MO": "1-Month Treasury Bill Yield",
    "DGS3MO": "3-Month Treasury Bill Yield",
}


def _fred_api_key() -> str:
    """DB-first via get_setting; env FRED_API_KEY fallback (fresh SessionLocal)."""
    try:
        from database import SessionLocal
        from providers.settings import get_setting

        with SessionLocal() as db:
            val = get_setting("fred_api_key", db)
            if val:
                return str(val).strip()
    except Exception:
        log.debug("fred.api_key_lookup_failed", exc_info=True)
    return os.getenv("FRED_API_KEY", "").strip()


def _poll_interval_seconds() -> int:
    return int(os.getenv("FRED_POLL_INTERVAL_SECONDS", "3600"))


def _init_fred_schema() -> None:
    con = get_duckdb()
    con.execute("""
        CREATE TABLE IF NOT EXISTS fred_yields (
            series_id VARCHAR,
            series_name VARCHAR,
            date DATE,
            value DOUBLE,
            fetched_at TIMESTAMP WITH TIME ZONE
        )
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_fred_yields_series_date
        ON fred_yields (series_id, date)
    """)


async def fetch_series(series_id: str) -> list[dict[str, Any]]:
    if not _fred_api_key():
        log.warning("fred.api_key_missing")
        return []

    url = f"{FRED_BASE}/series/observations"
    params = {
        "series_id": series_id,
        "api_key": _fred_api_key(),
        "file_type": "json",
        "sort_order": "desc",
        "limit": 100,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        log.warning("fred.fetch_failed", series=series_id, exc_info=True)
        return []

    observations = data.get("observations", [])
    results: list[dict[str, Any]] = []
    for obs in observations:
        val_str = obs.get("value", "").strip()
        if val_str in ("", "."):
            continue
        try:
            value = float(val_str)
        except ValueError:
            continue
        results.append({
            "series_id": series_id,
            "series_name": SERIES_MAP.get(series_id, series_id),
            "date": obs["date"],
            "value": value,
            "fetched_at": datetime.now(timezone.utc),
        })
    return results


def _store_yields(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    # DuckDB (legacy mirror — kept until cutover verified)
    try:
        con = get_duckdb()
        con.execute("DELETE FROM fred_yields WHERE series_id = ?", [rows[0]["series_id"]])
        for row in rows:
            con.execute(
                "INSERT INTO fred_yields (series_id, series_name, date, value, fetched_at) VALUES (?, ?, ?, ?, ?)",
                [row["series_id"], row["series_name"], row["date"], row["value"], row["fetched_at"]],
            )
    except Exception:
        log.warning("fred.duckdb_store_failed", exc_info=True)

    # Postgres SoT
    try:
        from database import FredYield, SessionLocal
        from sqlalchemy import delete

        with SessionLocal() as db:
            series_id = rows[0]["series_id"]
            db.execute(delete(FredYield).where(FredYield.series_id == series_id))
            for row in rows:
                db.add(
                    FredYield(
                        series_id=row["series_id"],
                        series_name=row.get("series_name"),
                        date=str(row["date"]),
                        value=row.get("value"),
                        fetched_at=row.get("fetched_at") or datetime.now(timezone.utc),
                    )
                )
            db.commit()
    except Exception:
        log.warning("fred.postgres_store_failed", exc_info=True)

    return len(rows)


def read_fred_yields_pg(
    db: Any,
    *,
    series_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Read FRED yields from Postgres (preferred SoT)."""
    from database import FredYield
    from sqlalchemy import desc, select

    q = select(FredYield).order_by(desc(FredYield.date)).limit(limit)
    if series_id:
        q = q.where(FredYield.series_id == series_id)
    rows = db.execute(q).scalars().all()
    return [
        {
            "series_id": r.series_id,
            "series_name": r.series_name,
            "date": r.date,
            "value": r.value,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
        }
        for r in rows
    ]


async def refresh_fred_yields() -> dict[str, int]:
    _init_fred_schema()
    counts: dict[str, int] = {}
    for series_id in SERIES_MAP:
        rows = await fetch_series(series_id)
        stored = _store_yields(rows)
        counts[series_id] = stored
        log.info("fred.yields_stored", series=series_id, count=stored)
    return counts


async def start_fred_poller() -> None:
    if not _fred_api_key():
        log.warning("fred.poller_disabled", reason="FRED_API_KEY not set")
        return
    _init_fred_schema()
    log.info("fred.poller.start", interval_seconds=_poll_interval_seconds())
    while True:
        try:
            await refresh_fred_yields()
        except Exception as exc:
            log.warning("fred.poller.error", exc_info=True)
        await asyncio.sleep(_poll_interval_seconds())
