"""add_source_previous_status

Revision ID: da39a3ee5e6b
Revises: 7a8b9c0d1e2f
Create Date: 2026-05-24 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "da39a3ee5e6b"
down_revision: Union[str, None] = "7a8b9c0d1e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("source_status", sa.Column("previous_status", sa.String(32), nullable=True))


def downgrade():
    op.drop_column("source_status", "previous_status")
