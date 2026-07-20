"""Add web_search_snapshots for cached AI web context.

Revision ID: v4_016_web_search_snapshots
Revises: v4_015_event_labels
Create Date: 2026-07-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v4_016_web_search_snapshots"
down_revision: Union[str, None] = "v4_015_event_labels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "web_search_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("query_key", sa.String(64), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("raw_meta", sa.JSON(), nullable=True),
    )
    op.create_index("ix_web_search_snapshots_query_key", "web_search_snapshots", ["query_key"])
    op.create_index("ix_web_search_snapshots_fetched_at", "web_search_snapshots", ["fetched_at"])
    op.create_index("ix_web_search_snapshots_expires_at", "web_search_snapshots", ["expires_at"])
    op.create_index("ix_web_search_key_fetched", "web_search_snapshots", ["query_key", "fetched_at"])


def downgrade() -> None:
    op.drop_index("ix_web_search_key_fetched", table_name="web_search_snapshots")
    op.drop_index("ix_web_search_snapshots_expires_at", table_name="web_search_snapshots")
    op.drop_index("ix_web_search_snapshots_fetched_at", table_name="web_search_snapshots")
    op.drop_index("ix_web_search_snapshots_query_key", table_name="web_search_snapshots")
    op.drop_table("web_search_snapshots")
