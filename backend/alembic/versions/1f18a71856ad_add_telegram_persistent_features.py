"""add_telegram_persistent_features

Revision ID: 1f18a71856ad
Revises: 8344a415ccb7
Create Date: 2026-06-02 17:45:32.603823

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f18a71856ad'
down_revision: Union[str, Sequence[str], None] = '8344a415ccb7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add persistent Telegram features tables."""
    # Create review items table
    op.create_table('telegram_review_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('review_id', sa.String(64), nullable=False),
        sa.Column('alert_data', sa.Text(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('reviewed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('approved', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_telegram_review_items_review_id'), 'telegram_review_items', ['review_id'], unique=True)
    op.create_index(op.f('ix_telegram_review_items_id'), 'telegram_review_items', ['id'], unique=False)
    
    # Create rate limits table
    op.create_table('telegram_rate_limits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('telegram_id', sa.Integer(), nullable=False),
        sa.Column('command_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_reset', sa.DateTime(), nullable=False),
        sa.Column('window_seconds', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('max_commands', sa.Integer(), nullable=False, server_default='10'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_telegram_rate_limits_telegram_id'), 'telegram_rate_limits', ['telegram_id'], unique=True)
    op.create_index(op.f('ix_telegram_rate_limits_id'), 'telegram_rate_limits', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema - remove persistent Telegram features tables."""
    # Drop rate limits table
    op.drop_index(op.f('ix_telegram_rate_limits_id'), table_name='telegram_rate_limits')
    op.drop_index(op.f('ix_telegram_rate_limits_telegram_id'), table_name='telegram_rate_limits')
    op.drop_table('telegram_rate_limits')
    
    # Drop review items table
    op.drop_index(op.f('ix_telegram_review_items_id'), table_name='telegram_review_items')
    op.drop_index(op.f('ix_telegram_review_items_review_id'), table_name='telegram_review_items')
    op.drop_table('telegram_review_items')
