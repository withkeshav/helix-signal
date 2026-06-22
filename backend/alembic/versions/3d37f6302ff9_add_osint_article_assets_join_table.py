"""add osint_article_assets join table

Revision ID: 3d37f6302ff9
Revises: d4e5f6a7b8c9
Create Date: 2026-06-22 12:31:52.995383

"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3d37f6302ff9'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('osint_article_assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=False),
        sa.Column('asset_symbol', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['osint_articles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('article_id', 'asset_symbol', name='uq_article_asset'),
    )
    op.create_index('ix_article_asset_article_id', 'osint_article_assets', ['article_id'], unique=False)
    op.create_index('ix_article_asset_asset_symbol', 'osint_article_assets', ['asset_symbol'], unique=False)

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, asset_symbols FROM osint_articles WHERE asset_symbols IS NOT NULL AND asset_symbols != ''")
    ).fetchall()
    now = datetime.now(timezone.utc)
    for row in rows:
        symbols = [s.strip().upper() for s in row.asset_symbols.split(',') if s.strip()]
        for sym in symbols:
            conn.execute(
                sa.text(
                    "INSERT INTO osint_article_assets (article_id, asset_symbol, created_at) "
                    "VALUES (:aid, :sym, :now)"
                ),
                {"aid": row.id, "sym": sym, "now": now},
            )

    op.drop_column('osint_articles', 'asset_symbols')


def downgrade() -> None:
    op.add_column('osint_articles', sa.Column('asset_symbols', sa.String(length=128), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT article_id, asset_symbol FROM osint_article_assets ORDER BY article_id, asset_symbol")
    ).fetchall()
    from collections import defaultdict
    by_article: dict[int, list[str]] = defaultdict(list)
    for r in rows:
        by_article[r.article_id].append(r.asset_symbol)
    for aid, symbols in by_article.items():
        conn.execute(
            sa.text("UPDATE osint_articles SET asset_symbols = :syms WHERE id = :id"),
            {"syms": ",".join(symbols), "id": aid},
        )

    op.drop_table('osint_article_assets')
