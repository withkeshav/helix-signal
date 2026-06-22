"""add settings_audit_log table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-21 12:00:03.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add settings_audit_log table."""
    op.create_table('settings_audit_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('setting_key', sa.String(128), nullable=False),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('user_username', sa.String(64), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(512), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_settings_audit_log_id'), 'settings_audit_log', ['id'])
    op.create_index(op.f('ix_settings_audit_log_setting_key'), 'settings_audit_log', ['setting_key'])
    op.create_index(op.f('ix_settings_audit_log_created_at'), 'settings_audit_log', ['created_at'])


def downgrade() -> None:
    """Downgrade schema - drop settings_audit_log table."""
    op.drop_index(op.f('ix_settings_audit_log_created_at'), table_name='settings_audit_log')
    op.drop_index(op.f('ix_settings_audit_log_setting_key'), table_name='settings_audit_log')
    op.drop_index(op.f('ix_settings_audit_log_id'), table_name='settings_audit_log')
    op.drop_table('settings_audit_log')
