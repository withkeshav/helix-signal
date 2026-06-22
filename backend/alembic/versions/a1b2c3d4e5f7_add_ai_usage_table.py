"""add ai_usage table

Revision ID: a1b2c3d4e5f7
Revises: 1f18a71856ad
Create Date: 2026-06-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, Sequence[str], None] = '1f18a71856ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add ai_usage table."""
    op.create_table('ai_usage',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('provider', sa.String(64), nullable=False),
        sa.Column('model', sa.String(64), nullable=False, server_default=''),
        sa.Column('usage_date', sa.String(10), nullable=False),
        sa.Column('calls', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('estimated_cost', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'model', 'usage_date', name='uq_ai_usage_date'),
    )
    op.create_index(op.f('ix_ai_usage_id'), 'ai_usage', ['id'])
    op.create_index(op.f('ix_ai_usage_provider'), 'ai_usage', ['provider'])
    op.create_index(op.f('ix_ai_usage_usage_date'), 'ai_usage', ['usage_date'])


def downgrade() -> None:
    """Downgrade schema - drop ai_usage table."""
    op.drop_index(op.f('ix_ai_usage_usage_date'), table_name='ai_usage')
    op.drop_index(op.f('ix_ai_usage_provider'), table_name='ai_usage')
    op.drop_index(op.f('ix_ai_usage_id'), table_name='ai_usage')
    op.drop_table('ai_usage')
