"""add osint_article indexes

Revision ID: a1b2c3d4e5f8
Revises: 84e91206bd26
Create Date: 2026-06-24 10:00:00.000000

Adds indexes for common query patterns on osint_articles:
- ix_osint_articles_published_at (published_at)
- ix_osint_articles_source_title (source, title)
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a1b2c3d4e5f8"
down_revision: Union[str, Sequence[str], None] = "84e91206bd26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_osint_articles_published_at", "osint_articles", ["published_at"])
    op.create_index("ix_osint_articles_source_title", "osint_articles", ["source", "title"])


def downgrade() -> None:
    op.drop_index("ix_osint_articles_source_title")
    op.drop_index("ix_osint_articles_published_at")
