"""add playbooks table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-21 12:00:02.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add playbooks table."""
    op.create_table('playbooks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('label', sa.String(128), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('settings', sa.JSON(), nullable=False),
        sa.Column('is_builtin', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_playbooks_id'), 'playbooks', ['id'])
    op.create_index(op.f('ix_playbooks_name'), 'playbooks', ['name'], unique=True)


def downgrade() -> None:
    """Downgrade schema - drop playbooks table."""
    op.drop_index(op.f('ix_playbooks_name'), table_name='playbooks')
    op.drop_index(op.f('ix_playbooks_id'), table_name='playbooks')
    op.drop_table('playbooks')
