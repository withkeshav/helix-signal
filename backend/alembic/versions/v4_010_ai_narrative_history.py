"""Add ai_narrative_history table.

Revision ID: v4_010_ai_narrative_history
Revises: v4_009_address_tags
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

revision = "v4_010_ai_narrative_history"
down_revision = "v4_009_address_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_narrative_history",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("asset_symbol", sa.String(16), nullable=False),
        sa.Column("feature", sa.String(48), server_default="market_narrative"),
        sa.Column("narrative_text", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("mode", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_narrative_asset", "ai_narrative_history", ["asset_symbol"])
    op.create_index("ix_ai_narrative_created", "ai_narrative_history", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_narrative_created", table_name="ai_narrative_history")
    op.drop_index("ix_ai_narrative_asset", table_name="ai_narrative_history")
    op.drop_table("ai_narrative_history")
