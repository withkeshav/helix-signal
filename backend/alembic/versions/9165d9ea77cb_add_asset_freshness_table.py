"""add_asset_freshness_table

Revision ID: 9165d9ea77cb
Revises: 78ff48300ff2
Create Date: 2026-06-01 14:25:09.869219

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9165d9ea77cb'
down_revision: Union[str, Sequence[str], None] = '78ff48300ff2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create asset_freshness table
    op.create_table(
        'asset_freshness',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_symbol', sa.String(length=16), nullable=False),
        sa.Column('last_successful_fetch', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_symbol')
    )
    op.create_index('ix_asset_freshness_asset_symbol', 'asset_freshness', ['asset_symbol'])
    op.create_index('ix_asset_freshness_id', 'asset_freshness', ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop asset_freshness table
    op.drop_index('ix_asset_freshness_id', table_name='asset_freshness')
    op.drop_index('ix_asset_freshness_asset_symbol', table_name='asset_freshness')
    op.drop_table('asset_freshness')
