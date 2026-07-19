"""Add data_quality_snapshots and insight_assets tables.

Revision ID: v4_013_data_quality_insight_assets
Revises: v4_012_timescale_compression
Create Date: 2026-07-19
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "v4_013_data_quality_insight_assets"
down_revision: Union[str, None] = "v4_012_timescale_compression"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_quality_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("overall_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_health", sa.JSON(), nullable=False),
        sa.Column("bucket_fill_rates", sa.JSON(), nullable=False),
        sa.Column("asset_metrics", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dq_snapshot_generated", "data_quality_snapshots", ["generated_at"])

    op.create_table(
        "insight_assets",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("asset_scope", sa.String(32), nullable=False, server_default="*"),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deterministic_payload", sa.JSON(), nullable=False),
        sa.Column("ai_narrative", sa.JSON(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
    )
    op.create_index("ix_insight_asset_kind", "insight_assets", ["kind"])
    op.create_index("ix_insight_asset_scope", "insight_assets", ["asset_scope"])
    op.create_index("ix_insight_asset_kind_scope_ts", "insight_assets", ["kind", "asset_scope", "generated_at"])


def downgrade() -> None:
    op.drop_index("ix_insight_asset_kind_scope_ts", table_name="insight_assets")
    op.drop_index("ix_insight_asset_scope", table_name="insight_assets")
    op.drop_index("ix_insight_asset_kind", table_name="insight_assets")
    op.drop_table("insight_assets")
    op.drop_index("ix_dq_snapshot_generated", table_name="data_quality_snapshots")
    op.drop_table("data_quality_snapshots")
