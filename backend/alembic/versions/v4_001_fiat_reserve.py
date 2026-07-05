"""Add fiat_reserve_snapshots table.

Revision ID: v4_001_fiat_reserve
Revises: a1b2c3d4e5f8
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v4_001_fiat_reserve"
down_revision = "a1b2c3d4e5f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fiat_reserve_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("asset_symbol", sa.String(20), nullable=False, index=True),
        sa.Column("attestation_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reserve_usd", sa.Float(), nullable=True),
        sa.Column("circulating_supply", sa.Float(), nullable=True),
        sa.Column("coverage_ratio", sa.Float(), nullable=True),
        sa.Column("reserve_composition", postgresql.JSON, nullable=True),
        sa.Column("attestation_url", sa.String(500), nullable=True),
        sa.Column("attestation_source", sa.String(100), nullable=True),
        sa.Column("attestation_lag_days", sa.Integer(), nullable=True),
        sa.Column("genius_act_compliant", sa.Boolean(), nullable=True),
        sa.Column("mica_status", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_fiat_reserve_asset_ts", "fiat_reserve_snapshots",
                    ["asset_symbol", "attestation_date"])
    op.create_index("ix_fiat_reserve_created", "fiat_reserve_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_table("fiat_reserve_snapshots")
