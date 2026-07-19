from __future__ import annotations

import os
from pathlib import Path

import duckdb

_con: duckdb.DuckDBPyConnection | None = None


def get_duckdb() -> duckdb.DuckDBPyConnection:
    """Return the shared DuckDB connection.

    Only ``fred_yields`` is maintained (see ``chain/fred_api.py``).
    Dead OLAP mirror schemas were removed in v4.0.7 (WO-BE-7a).
    """
    global _con
    if _con is None:
        db_path = os.getenv("DUCKDB_PATH", "/data/helix.duckdb")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _con = duckdb.connect(db_path, read_only=False)
    return _con


def close_duckdb() -> None:
    global _con
    if _con is not None:
        _con.close()
        _con = None
