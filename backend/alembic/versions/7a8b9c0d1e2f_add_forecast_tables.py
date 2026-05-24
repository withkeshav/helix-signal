"""add_forecast_tables

Revision ID: 7a8b9c0d1e2f
Revises: fe5793facbbb
Create Date: 2026-05-23 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a8b9c0d1e2f"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        'forecast_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('model_name', sa.String(64), nullable=False),
        sa.Column('model_version', sa.String(32), nullable=False),
        sa.Column('target_metric', sa.String(32), nullable=False),
        sa.Column('asset_symbol', sa.String(16), nullable=False),
        sa.Column('chain_key', sa.String(64), nullable=True),
        sa.Column('input_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('input_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('horizon', sa.Integer(), nullable=False),
        sa.Column('frequency', sa.String(16), nullable=False),
        sa.Column('status', sa.String(16), server_default='completed'),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('input_points', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_forecast_runs_asset', 'forecast_runs', ['asset_symbol'])
    op.create_index('ix_forecast_runs_model', 'forecast_runs', ['model_name'])

    op.create_table(
        'forecast_points',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('run_id', sa.Integer(), sa.ForeignKey('forecast_runs.id'), nullable=False),
        sa.Column('asset_symbol', sa.String(16), nullable=False),
        sa.Column('chain_key', sa.String(64), nullable=True),
        sa.Column('target_metric', sa.String(32), nullable=False),
        sa.Column('horizon_step', sa.Integer(), nullable=False),
        sa.Column('forecast_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('point_forecast', sa.Float(), nullable=True),
        sa.Column('q10', sa.Float(), nullable=True),
        sa.Column('q50', sa.Float(), nullable=True),
        sa.Column('q90', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_forecast_points_run', 'forecast_points', ['run_id'])
    op.create_index('ix_forecast_points_asset_metric', 'forecast_points', ['asset_symbol', 'target_metric'])


def downgrade():
    op.drop_table('forecast_points')
    op.drop_table('forecast_runs')
