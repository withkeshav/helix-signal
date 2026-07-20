"""Add webhook_endpoints, ai_providers, api_keys.access_policy, fred_yields.

Revision ID: v4_017_platform_tables
Revises: v4_016_web_search_snapshots
Create Date: 2026-07-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v4_017_platform_tables"
down_revision: Union[str, None] = "v4_016_web_search_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("signing_secret_enc", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true()),
        sa.Column("min_severity", sa.String(16), server_default="warning"),
        sa.Column("event_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("assets", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("timeout_seconds", sa.Integer(), server_default="10"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "ai_providers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("api_key_enc", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true()),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_error", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "fred_yields",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("series_id", sa.String(32), nullable=False),
        sa.Column("series_name", sa.String(128), nullable=True),
        sa.Column("date", sa.String(16), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_fred_yields_series_id", "fred_yields", ["series_id"])
    op.create_index("ix_fred_yields_series_date", "fred_yields", ["series_id", "date"])
    with op.batch_alter_table("api_keys") as batch:
        batch.add_column(sa.Column("access_policy", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("api_keys") as batch:
        batch.drop_column("access_policy")
    op.drop_index("ix_fred_yields_series_date", table_name="fred_yields")
    op.drop_index("ix_fred_yields_series_id", table_name="fred_yields")
    op.drop_table("fred_yields")
    op.drop_table("ai_providers")
    op.drop_table("webhook_endpoints")
