"""Add address_tags table.

Revision ID: v4_009_address_tags
Revises: v4_008_osint_classification
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v4_009_address_tags"
down_revision = "v4_008_osint_classification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "address_tags",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("address", sa.String(100), nullable=False, index=True),
        sa.Column("chain", sa.String(50), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), server_default=sa.text("1.0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_addrtag_addr_chain", "address_tags", ["address", "chain"])


def downgrade() -> None:
    op.drop_table("address_tags")
