"""Add event_labels table for operator labeling corpus (WO-DA-5).

Revision ID: v4_015_event_labels
Revises: v4_014_v4_hypertables_aggregates
Create Date: 2026-07-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v4_015_event_labels"
down_revision: Union[str, None] = "v4_014_v4_hypertables_aggregates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "event_labels",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("user_username", sa.String(64), nullable=True),
        sa.Column("label", sa.String(32), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_event_labels_type_id", "event_labels", ["event_type", "event_id"])
    op.create_index("ix_event_labels_created", "event_labels", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_event_labels_created", table_name="event_labels")
    op.drop_index("ix_event_labels_type_id", table_name="event_labels")
    op.drop_table("event_labels")
