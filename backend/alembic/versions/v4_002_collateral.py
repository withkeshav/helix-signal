"""Add collateral_snapshots table.

Revision ID: v4_002_collateral
Revises: v4_001_fiat_reserve
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v4_002_collateral"
down_revision = "v4_001_fiat_reserve"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collateral_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("asset_symbol", sa.String(20), nullable=False, index=True),
        sa.Column("collateral_ratio", sa.Float(), nullable=True),
        sa.Column("collateral_assets_json", postgresql.JSON, nullable=True),
        sa.Column("liquidation_threshold", sa.Float(), nullable=True),
        sa.Column("liquidation_queue_usd", sa.Float(), nullable=True),
        sa.Column("debt_ceiling_utilization_pct", sa.Float(), nullable=True),
        sa.Column("largest_vault_usd", sa.Float(), nullable=True),
        sa.Column("collateral_health_score", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_collateral_asset_ts", "collateral_snapshots",
                    ["asset_symbol", "timestamp"])


def downgrade() -> None:
    op.drop_table("collateral_snapshots")
