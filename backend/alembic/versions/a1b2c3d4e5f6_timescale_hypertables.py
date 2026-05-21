"""Timescale hypertables for trend snapshots (PostgreSQL only).

Revision ID: a1b2c3d4e5f6
Revises: fe5793facbbb
Create Date: 2026-05-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "fe5793facbbb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def _prepare_hypertable(table: str, unique_constraint: str, unique_cols: str) -> None:
    """Timescale requires partition column in PK and unique constraints."""
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_pkey")
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {unique_constraint}")
    op.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (timestamp, id)")
    op.execute(
        f"ALTER TABLE {table} ADD CONSTRAINT {unique_constraint} UNIQUE (timestamp, {unique_cols})"
    )


def upgrade() -> None:
    if not _is_postgres():
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
    _prepare_hypertable(
        "asset_trend_snapshots",
        "uq_asset_trend_bucket",
        "asset_symbol, bucket_id",
    )
    _prepare_hypertable(
        "chain_trend_snapshots",
        "uq_chain_trend_bucket",
        "asset_symbol, chain_key, bucket_id",
    )
    for table in ("asset_trend_snapshots", "chain_trend_snapshots"):
        op.execute(
            f"""
            SELECT create_hypertable('{table}', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE)
            """
        )
    # Rolling 1h signal mean — refreshed by scheduler/worker on VPS
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS asset_signal_1h
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 hour', timestamp) AS bucket,
            asset_symbol,
            avg(signal_score) AS avg_signal_score,
            max(signal_score) AS max_signal_score,
            count(*) AS sample_count
        FROM asset_trend_snapshots
        GROUP BY 1, 2
        WITH NO DATA
        """
    )
    op.execute(
        """
        SELECT add_continuous_aggregate_policy(
            'asset_signal_1h',
            start_offset => INTERVAL '3 hours',
            end_offset => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour',
            if_not_exists => TRUE
        )
        """
    )


def downgrade() -> None:
    if not _is_postgres():
        return
    op.execute("DROP MATERIALIZED VIEW IF EXISTS asset_signal_1h CASCADE")
