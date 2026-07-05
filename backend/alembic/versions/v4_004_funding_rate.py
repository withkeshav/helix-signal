"""Add funding_rate_snapshots table.

Revision ID: v4_004_funding_rate
Revises: v4_003_yield_bearing
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "v4_004_funding_rate"
down_revision = "v4_003_yield_bearing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "funding_rate_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("exchange", sa.String(50), nullable=True),
        sa.Column("symbol", sa.String(30), nullable=True),
        sa.Column("funding_rate", sa.Float(), nullable=True),
        sa.Column("annualized_rate", sa.Float(), nullable=True),
        sa.Column("next_funding_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, index=True),
    )
    op.create_index("ix_funding_rate_exchange_ts", "funding_rate_snapshots",
                    ["exchange", "timestamp"])


def downgrade() -> None:
    op.drop_table("funding_rate_snapshots")
