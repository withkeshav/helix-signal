"""Add event classification columns to osint_articles.

Revision ID: v4_008_osint_classification
Revises: v4_007_add_stablecoin_type
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "v4_008_osint_classification"
down_revision = "v4_007_add_stablecoin_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("osint_articles",
        sa.Column("event_type", sa.String(50), nullable=True, index=True)
    )
    op.add_column("osint_articles",
        sa.Column("driver_category", sa.String(50), nullable=True)
    )
    op.add_column("osint_articles",
        sa.Column("source_authority", sa.Float(), nullable=True)
    )
    op.add_column("osint_articles",
        sa.Column("is_leading_indicator", sa.Boolean(), nullable=True)
    )
    op.add_column("osint_articles",
        sa.Column("extracted_numbers_json", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("osint_articles", "extracted_numbers_json")
    op.drop_column("osint_articles", "is_leading_indicator")
    op.drop_column("osint_articles", "source_authority")
    op.drop_column("osint_articles", "driver_category")
    op.drop_column("osint_articles", "event_type")
