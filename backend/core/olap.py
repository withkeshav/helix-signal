from __future__ import annotations

import os
from pathlib import Path

import duckdb

_con: duckdb.DuckDBPyConnection | None = None


def get_duckdb() -> duckdb.DuckDBPyConnection:
    global _con
    if _con is None:
        db_path = os.getenv("DUCKDB_PATH", "/data/helix.duckdb")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _con = duckdb.connect(db_path, read_only=False)
        _init_schema(_con)
    return _con


def _init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS asset_chain_snapshots (
            id BIGINT,
            asset_symbol VARCHAR,
            asset_name VARCHAR,
            chain_name VARCHAR,
            supply_current DOUBLE,
            supply_prev_day DOUBLE,
            supply_prev_week DOUBLE,
            supply_prev_month DOUBLE,
            tvl DOUBLE,
            price DOUBLE,
            price_coingecko DOUBLE,
            price_dexscreener DOUBLE,
            market_cap DOUBLE,
            volume_24h DOUBLE,
            total_liquidity_usd DOUBLE,
            top3_pool_share_pct DOUBLE,
            pool_count INTEGER,
            peg_type VARCHAR,
            source_name VARCHAR,
            fetched_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS source_status (
            id BIGINT,
            source_name VARCHAR,
            status VARCHAR,
            previous_status VARCHAR,
            last_attempted_fetch TIMESTAMP WITH TIME ZONE,
            last_successful_fetch TIMESTAMP WITH TIME ZONE,
            last_error VARCHAR,
            updated_at TIMESTAMP WITH TIME ZONE
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS asset_trend_snapshots (
            id BIGINT,
            asset_symbol VARCHAR,
            timestamp TIMESTAMP WITH TIME ZONE,
            bucket_id INTEGER,
            total_supply DOUBLE,
            price DOUBLE,
            depeg_index INTEGER,
            signal_score INTEGER,
            signal_band VARCHAR,
            concentration_score INTEGER,
            data_confidence_label VARCHAR,
            source_status VARCHAR,
            created_at TIMESTAMP WITH TIME ZONE
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS signal_events (
            id BIGINT,
            asset_symbol VARCHAR,
            chain_key VARCHAR,
            event_type VARCHAR,
            severity VARCHAR,
            title VARCHAR,
            summary VARCHAR,
            old_value VARCHAR,
            new_value VARCHAR,
            delta VARCHAR,
            threshold VARCHAR,
            timestamp TIMESTAMP WITH TIME ZONE,
            metadata_json VARCHAR,
            created_at TIMESTAMP WITH TIME ZONE
        )
    """)


def close_duckdb() -> None:
    global _con
    if _con is not None:
        _con.close()
        _con = None
