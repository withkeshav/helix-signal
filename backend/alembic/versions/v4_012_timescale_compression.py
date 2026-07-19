"""Timescale compression policies for trend hypertables (PostgreSQL only).

Revision ID: v4_012_timescale_compression
Revises: v4_011_api_keys
Create Date: 2026-07-19
"""

from typing import Sequence, Union

from alembic import op


revision: str = "v4_012_timescale_compression"
down_revision: Union[str, None] = "v4_011_api_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return
    for table, segmentby in (
        ("asset_trend_snapshots", "asset_symbol"),
        ("chain_trend_snapshots", "asset_symbol, chain_key"),
    ):
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


def downgrade() -> None:
    if not _is_postgres():
        return
    for table in ("asset_trend_snapshots", "chain_trend_snapshots"):
        op.execute(
            f"""
            SELECT remove_compression_policy('{table}', if_exists => TRUE)
            """
        )
