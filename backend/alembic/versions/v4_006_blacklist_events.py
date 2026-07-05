"""Add blacklist_events table.

Revision ID: v4_006_blacklist_events
Revises: v4_005_whale_activity
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v4_006_blacklist_events"
down_revision = "v4_005_whale_activity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blacklist_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("asset_symbol", sa.String(20), nullable=False, index=True),
        sa.Column("chain", sa.String(50), nullable=True),
        sa.Column("frozen_address", sa.String(100), index=True),
        sa.Column("frozen_balance_usd", sa.Float(), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=True),
        sa.Column("tx_hash", sa.String(100), nullable=True),
        sa.Column("block_number", sa.BigInteger(), nullable=True),
        sa.Column("intelligence_note", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_blacklist_asset_ts", "blacklist_events",
                    ["asset_symbol", "timestamp"])
    op.create_index("ix_blacklist_frozen_addr", "blacklist_events", ["frozen_address"])


def downgrade() -> None:
    op.drop_table("blacklist_events")
