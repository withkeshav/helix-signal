"""Add stablecoin_type column to asset_chain_snapshots.

Revision ID: v4_007_add_stablecoin_type
Revises: v4_006_blacklist_events
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "v4_007_add_stablecoin_type"
down_revision = "v4_006_blacklist_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("asset_chain_snapshots",
        sa.Column("stablecoin_type", sa.String(32), nullable=True, index=True)
    )
    op.add_column("asset_chain_snapshots",
        sa.Column("stablecoin_sub_type", sa.String(32), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("asset_chain_snapshots", "stablecoin_type")
    op.drop_column("asset_chain_snapshots", "stablecoin_sub_type")
