"""add_cross_source_discrepancy_column

Revision ID: a9409ead8fc3
Revises: 9165d9ea77cb
Create Date: 2026-06-01 14:27:48.580669

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9409ead8fc3'
down_revision: Union[str, Sequence[str], None] = '9165d9ea77cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add cross_source_discrepancy column to asset_trend_snapshots table
    op.add_column('asset_trend_snapshots', sa.Column('cross_source_discrepancy', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Drop cross_source_discrepancy column from asset_trend_snapshots table
    op.drop_column('asset_trend_snapshots', 'cross_source_discrepancy')
