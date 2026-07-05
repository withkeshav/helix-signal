"""Add yield_bearing_snapshots table.

Revision ID: v4_003_yield_bearing
Revises: v4_002_collateral
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "v4_003_yield_bearing"
down_revision = "v4_002_collateral"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "yield_bearing_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("asset_symbol", sa.String(20), nullable=False, index=True),
        sa.Column("current_apy", sa.Float(), nullable=True),
        sa.Column("apy_7d_avg", sa.Float(), nullable=True),
        sa.Column("apy_7d_delta", sa.Float(), nullable=True),
        sa.Column("yield_source", sa.String(50), nullable=True),
        sa.Column("yield_sustainability", sa.Float(), nullable=True),
        sa.Column("funding_rate_current", sa.Float(), nullable=True),
        sa.Column("funding_rate_7d_avg", sa.Float(), nullable=True),
        sa.Column("insurance_fund_usd", sa.Float(), nullable=True),
        sa.Column("insurance_fund_coverage", sa.Float(), nullable=True),
        sa.Column("staking_ratio", sa.Float(), nullable=True),
        sa.Column("lending_utilization_pct", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_yield_bearing_asset_ts", "yield_bearing_snapshots",
                    ["asset_symbol", "timestamp"])


def downgrade() -> None:
    op.drop_table("yield_bearing_snapshots")
