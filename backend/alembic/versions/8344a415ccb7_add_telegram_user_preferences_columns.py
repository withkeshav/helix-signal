"""add_telegram_user_preferences_columns

Revision ID: 8344a415ccb7
Revises: a9409ead8fc4
Create Date: 2026-06-02 17:39:43.625404

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8344a415ccb7'
down_revision: Union[str, Sequence[str], None] = 'a9409ead8fc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add Telegram user preference columns."""
    # Add preference columns
    op.add_column('telegram_users', sa.Column('preferred_assets', sa.String(512), nullable=True, server_default="USDT,USDC,DAI"))
    op.add_column('telegram_users', sa.Column('alert_types', sa.String(512), nullable=True, server_default="signal,anomaly,osint"))
    op.add_column('telegram_users', sa.Column('min_severity', sa.String(20), nullable=True, server_default="medium"))
    op.add_column('telegram_users', sa.Column('timezone', sa.String(50), nullable=True, server_default="UTC"))
    op.add_column('telegram_users', sa.Column('quiet_hours_start', sa.String(5), nullable=True))
    op.add_column('telegram_users', sa.Column('quiet_hours_end', sa.String(5), nullable=True))
    op.add_column('telegram_users', sa.Column('receive_digest', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('telegram_users', sa.Column('digest_time', sa.String(5), nullable=True, server_default="09:00"))
    
    # Update existing users with default values
    op.execute("UPDATE telegram_users SET preferred_assets = 'USDT,USDC,DAI' WHERE preferred_assets IS NULL")
    op.execute("UPDATE telegram_users SET alert_types = 'signal,anomaly,osint' WHERE alert_types IS NULL")
    op.execute("UPDATE telegram_users SET min_severity = 'medium' WHERE min_severity IS NULL")
    op.execute("UPDATE telegram_users SET timezone = 'UTC' WHERE timezone IS NULL")
    op.execute("UPDATE telegram_users SET receive_digest = TRUE WHERE receive_digest IS NULL")
    op.execute("UPDATE telegram_users SET digest_time = '09:00' WHERE digest_time IS NULL")


def downgrade() -> None:
    """Downgrade schema - remove Telegram user preference columns."""
    # Remove preference columns
    op.drop_column('telegram_users', 'digest_time')
    op.drop_column('telegram_users', 'receive_digest')
    op.drop_column('telegram_users', 'quiet_hours_end')
    op.drop_column('telegram_users', 'quiet_hours_start')
    op.drop_column('telegram_users', 'timezone')
    op.drop_column('telegram_users', 'min_severity')
    op.drop_column('telegram_users', 'alert_types')
    op.drop_column('telegram_users', 'preferred_assets')
