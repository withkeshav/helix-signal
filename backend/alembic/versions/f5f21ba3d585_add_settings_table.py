"""add_settings_table

Revision ID: f5f21ba3d585
Revises: da39a3ee5e6b
Create Date: 2026-05-25 17:59:30.395094

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f5f21ba3d585'
down_revision: Union[str, Sequence[str], None] = 'da39a3ee5e6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    tables = _existing_tables()
    if "settings" not in tables:
        op.create_table(
            "settings",
            sa.Column("key", sa.String(length=128), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("key"),
        )


def downgrade() -> None:
    tables = _existing_tables()
    if "settings" in tables:
        op.drop_table("settings")
