"""add_source_usage_table

Revision ID: 78ff48300ff2
Revises: f5f21ba3d585
Create Date: 2026-06-01 14:22:32.638340

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78ff48300ff2'
down_revision: Union[str, Sequence[str], None] = 'f5f21ba3d585'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create source_usage table
    op.create_table(
        'source_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_name', sa.String(length=64), nullable=False),
        sa.Column('usage_date', sa.String(length=10), nullable=False),
        sa.Column('call_count', sa.Integer(), nullable=False, default=0),
        sa.Column('last_call_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_name', 'usage_date', name='uq_source_usage_date')
    )
    op.create_index('ix_source_usage_source_name', 'source_usage', ['source_name'])
    op.create_index('ix_source_usage_usage_date', 'source_usage', ['usage_date'])
    op.create_index('ix_source_usage_id', 'source_usage', ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop source_usage table
    op.drop_index('ix_source_usage_id', table_name='source_usage')
    op.drop_index('ix_source_usage_usage_date', table_name='source_usage')
    op.drop_index('ix_source_usage_source_name', table_name='source_usage')
    op.drop_table('source_usage')
