"""Hypertables + continuous aggregates for v4 snapshot series (PostgreSQL only).

Revision ID: v4_014_v4_hypertables_aggregates
Revises: v4_013_data_quality_insight_assets
Create Date: 2026-07-19
"""

from typing import Sequence, Union

from alembic import op

revision: str = "v4_014_v4_hypertables_aggregates"
down_revision: Union[str, None] = "v4_013_data_quality_insight_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_V4_TABLES = (
    "funding_rate_snapshots",
    "yield_bearing_snapshots",
    "collateral_snapshots",
    "whale_activity_snapshots",
)


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def _prepare_hypertable(table: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_pkey")
    op.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (timestamp, id)")


def upgrade() -> None:
    if not _is_postgres():
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
    for table in _V4_TABLES:
        _prepare_hypertable(table)
        op.execute(
            f"""
            SELECT create_hypertable('{table}', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE)
            """
        )
        segmentby = "asset_symbol" if table != "funding_rate_snapshots" else "exchange, symbol"
        op.execute(
            f"""
            ALTER TABLE {table} SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = '{segmentby}'
            )
            """
        )
        op.execute(
            f"""
            SELECT add_compression_policy('{table}', INTERVAL '7 days', if_not_exists => TRUE)
            """
        )

    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS funding_rate_hourly
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 hour', timestamp) AS bucket,
            exchange,
            symbol,
            avg(funding_rate) AS avg_funding_rate,
            avg(annualized_rate) AS avg_annualized_rate,
            count(*) AS sample_count
        FROM funding_rate_snapshots
        GROUP BY 1, 2, 3
        WITH NO DATA
        """
    )
    op.execute(
        """
        SELECT add_continuous_aggregate_policy(
            'funding_rate_hourly',
            start_offset => INTERVAL '3 hours',
            end_offset => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour',
            if_not_exists => TRUE
        )
        """
    )

    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS yield_bearing_daily
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 day', timestamp) AS bucket,
            asset_symbol,
            avg(current_apy) AS avg_current_apy,
            avg(apy_7d_avg) AS avg_apy_7d_avg,
            avg(funding_rate_current) AS avg_funding_rate_current,
            avg(insurance_fund_usd) AS avg_insurance_fund_usd,
            count(*) AS sample_count
        FROM yield_bearing_snapshots
        GROUP BY 1, 2
        WITH NO DATA
        """
    )
    op.execute(
        """
        SELECT add_continuous_aggregate_policy(
            'yield_bearing_daily',
            start_offset => INTERVAL '3 days',
            end_offset => INTERVAL '1 day',
            schedule_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        )
        """
    )

    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS collateral_daily
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 day', timestamp) AS bucket,
            asset_symbol,
            avg(collateral_ratio) AS avg_collateral_ratio,
            avg(liquidation_queue_usd) AS avg_liquidation_queue_usd,
            avg(collateral_health_score) AS avg_collateral_health_score,
            count(*) AS sample_count
        FROM collateral_snapshots
        GROUP BY 1, 2
        WITH NO DATA
        """
    )
    op.execute(
        """
        SELECT add_continuous_aggregate_policy(
            'collateral_daily',
            start_offset => INTERVAL '3 days',
            end_offset => INTERVAL '1 day',
            schedule_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        )
        """
    )

    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS whale_activity_daily
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 day', timestamp) AS bucket,
            asset_symbol,
            chain,
            avg(top10_holder_pct) AS avg_top10_holder_pct,
            avg(exchange_inflow_usd_24h) AS avg_exchange_inflow_usd_24h,
            sum(large_transfer_count_24h) AS total_large_transfers,
            count(*) AS sample_count
        FROM whale_activity_snapshots
        GROUP BY 1, 2, 3
        WITH NO DATA
        """
    )
    op.execute(
        """
        SELECT add_continuous_aggregate_policy(
            'whale_activity_daily',
            start_offset => INTERVAL '3 days',
            end_offset => INTERVAL '1 day',
            schedule_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        )
        """
    )


def downgrade() -> None:
    if not _is_postgres():
        return
    for view in (
        "whale_activity_daily",
        "collateral_daily",
        "yield_bearing_daily",
        "funding_rate_hourly",
    ):
        op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {view} CASCADE")
    for table in _V4_TABLES:
        op.execute(f"SELECT remove_compression_policy('{table}', if_exists => TRUE)")
