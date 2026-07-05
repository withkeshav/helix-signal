"""Add whale_activity_snapshots table.

Revision ID: v4_005_whale_activity
Revises: v4_004_funding_rate
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "v4_005_whale_activity"
down_revision = "v4_004_funding_rate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whale_activity_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("asset_symbol", sa.String(20), nullable=False, index=True),
        sa.Column("chain", sa.String(50), nullable=True),
        sa.Column("top10_holder_pct", sa.Float(), nullable=True),
        sa.Column("top10_holder_pct_delta_24h", sa.Float(), nullable=True),
        sa.Column("large_transfer_count_24h", sa.Integer(), nullable=True),
        sa.Column("exchange_inflow_usd_24h", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, index=True),
    )
    op.create_index("ix_whale_asset_ts", "whale_activity_snapshots",
                    ["asset_symbol", "timestamp"])


def downgrade() -> None:
    op.drop_table("whale_activity_snapshots")
