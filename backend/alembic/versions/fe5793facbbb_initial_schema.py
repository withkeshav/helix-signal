"""initial_schema

Revision ID: fe5793facbbb
Revises:
Create Date: 2026-05-20 18:51:25.061343

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "fe5793facbbb"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    tables = _existing_tables()

    if "source_status" not in tables:
        op.create_table(
            "source_status",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("source_name", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=True),
            sa.Column("last_attempted_fetch", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_successful_fetch", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.String(length=1024), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source_name"),
        )
        op.create_index(op.f("ix_source_status_id"), "source_status", ["id"], unique=False)
        op.create_index(op.f("ix_source_status_source_name"), "source_status", ["source_name"], unique=True)

    if "asset_chain_snapshots" not in tables:
        op.create_table(
            "asset_chain_snapshots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("asset_symbol", sa.String(length=16), nullable=False),
            sa.Column("asset_name", sa.String(length=64), nullable=True),
            sa.Column("chain_name", sa.String(length=64), nullable=False),
            sa.Column("supply_current", sa.Float(), nullable=True),
            sa.Column("supply_prev_day", sa.Float(), nullable=True),
            sa.Column("supply_prev_week", sa.Float(), nullable=True),
            sa.Column("supply_prev_month", sa.Float(), nullable=True),
            sa.Column("tvl", sa.Float(), nullable=True),
            sa.Column("price", sa.Float(), nullable=True),
            sa.Column("price_coingecko", sa.Float(), nullable=True),
            sa.Column("price_dexscreener", sa.Float(), nullable=True),
            sa.Column("market_cap", sa.Float(), nullable=True),
            sa.Column("volume_24h", sa.Float(), nullable=True),
            sa.Column("total_liquidity_usd", sa.Float(), nullable=True),
            sa.Column("top3_pool_share_pct", sa.Float(), nullable=True),
            sa.Column("pool_count", sa.Integer(), nullable=True),
            sa.Column("peg_type", sa.String(length=32), nullable=True),
            sa.Column("source_name", sa.String(length=64), nullable=True),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("asset_symbol", "chain_name", name="uq_asset_chain_snapshot"),
        )
        op.create_index(op.f("ix_asset_chain_snapshots_id"), "asset_chain_snapshots", ["id"], unique=False)
        op.create_index(op.f("ix_asset_chain_snapshots_asset_symbol"), "asset_chain_snapshots", ["asset_symbol"], unique=False)
        op.create_index(op.f("ix_asset_chain_snapshots_chain_name"), "asset_chain_snapshots", ["chain_name"], unique=False)
    else:
        for col, col_type in (
            ("price_coingecko", sa.Float()),
            ("price_dexscreener", sa.Float()),
            ("market_cap", sa.Float()),
            ("volume_24h", sa.Float()),
            ("total_liquidity_usd", sa.Float()),
            ("top3_pool_share_pct", sa.Float()),
            ("pool_count", sa.Integer()),
        ):
            if not _has_column("asset_chain_snapshots", col):
                op.add_column("asset_chain_snapshots", sa.Column(col, col_type, nullable=True))

    if "asset_trend_snapshots" not in tables:
        op.create_table(
            "asset_trend_snapshots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("asset_symbol", sa.String(length=16), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("bucket_id", sa.Integer(), nullable=False),
            sa.Column("total_supply", sa.Float(), nullable=True),
            sa.Column("price", sa.Float(), nullable=True),
            sa.Column("depeg_index", sa.Integer(), nullable=True),
            sa.Column("signal_score", sa.Integer(), nullable=True),
            sa.Column("signal_band", sa.String(length=16), nullable=True),
            sa.Column("concentration_score", sa.Integer(), nullable=True),
            sa.Column("data_confidence_label", sa.String(length=16), nullable=True),
            sa.Column("source_status", sa.String(length=32), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("asset_symbol", "bucket_id", name="uq_asset_trend_bucket"),
        )
        op.create_index(op.f("ix_asset_trend_snapshots_id"), "asset_trend_snapshots", ["id"], unique=False)
        op.create_index(op.f("ix_asset_trend_snapshots_asset_symbol"), "asset_trend_snapshots", ["asset_symbol"], unique=False)
        op.create_index(op.f("ix_asset_trend_snapshots_timestamp"), "asset_trend_snapshots", ["timestamp"], unique=False)
        op.create_index(op.f("ix_asset_trend_snapshots_bucket_id"), "asset_trend_snapshots", ["bucket_id"], unique=False)

    if "chain_trend_snapshots" not in tables:
        op.create_table(
            "chain_trend_snapshots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("asset_symbol", sa.String(length=16), nullable=False),
            sa.Column("chain_key", sa.String(length=64), nullable=False),
            sa.Column("chain_name", sa.String(length=64), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("bucket_id", sa.Integer(), nullable=False),
            sa.Column("supply", sa.Float(), nullable=True),
            sa.Column("supply_share_pct", sa.Float(), nullable=True),
            sa.Column("chain_tvl", sa.Float(), nullable=True),
            sa.Column("chain_signal_score", sa.Integer(), nullable=True),
            sa.Column("chain_signal_band", sa.String(length=16), nullable=True),
            sa.Column("data_confidence_score", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("asset_symbol", "chain_key", "bucket_id", name="uq_chain_trend_bucket"),
        )
        op.create_index(op.f("ix_chain_trend_snapshots_id"), "chain_trend_snapshots", ["id"], unique=False)
        op.create_index(op.f("ix_chain_trend_snapshots_asset_symbol"), "chain_trend_snapshots", ["asset_symbol"], unique=False)
        op.create_index(op.f("ix_chain_trend_snapshots_chain_key"), "chain_trend_snapshots", ["chain_key"], unique=False)
        op.create_index(op.f("ix_chain_trend_snapshots_timestamp"), "chain_trend_snapshots", ["timestamp"], unique=False)
        op.create_index(op.f("ix_chain_trend_snapshots_bucket_id"), "chain_trend_snapshots", ["bucket_id"], unique=False)

    if "signal_events" not in tables:
        op.create_table(
            "signal_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("asset_symbol", sa.String(length=16), nullable=False),
            sa.Column("chain_key", sa.String(length=64), nullable=True),
            sa.Column("event_type", sa.String(length=48), nullable=False),
            sa.Column("severity", sa.String(length=16), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("summary", sa.String(length=500), nullable=False),
            sa.Column("old_value", sa.String(length=256), nullable=True),
            sa.Column("new_value", sa.String(length=256), nullable=True),
            sa.Column("delta", sa.String(length=128), nullable=True),
            sa.Column("threshold", sa.String(length=128), nullable=True),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_signal_events_id"), "signal_events", ["id"], unique=False)
        op.create_index(op.f("ix_signal_events_asset_symbol"), "signal_events", ["asset_symbol"], unique=False)
        op.create_index(op.f("ix_signal_events_chain_key"), "signal_events", ["chain_key"], unique=False)
        op.create_index(op.f("ix_signal_events_event_type"), "signal_events", ["event_type"], unique=False)
        op.create_index(op.f("ix_signal_events_severity"), "signal_events", ["severity"], unique=False)
        op.create_index(op.f("ix_signal_events_timestamp"), "signal_events", ["timestamp"], unique=False)

    if "osint_articles" not in tables:
        op.create_table(
            "osint_articles",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("asset_symbols", sa.String(length=128), nullable=True),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("url", sa.String(length=1024), nullable=True),
            sa.Column("summary", sa.String(length=2000), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("sentiment_score", sa.Float(), nullable=True),
            sa.Column("sentiment_label", sa.String(length=16), nullable=True),
            sa.Column("entities", sa.Text(), nullable=True),
            sa.Column("topics", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_osint_articles_id"), "osint_articles", ["id"], unique=False)
        op.create_index(op.f("ix_osint_articles_source"), "osint_articles", ["source"], unique=False)

    tables = _existing_tables()
    if "chain_data" in tables:
        try:
            op.drop_index(op.f("ix_chain_data_chain_name"), table_name="chain_data")
        except Exception:
            pass
        try:
            op.drop_index(op.f("ix_chain_data_id"), table_name="chain_data")
        except Exception:
            pass
        op.drop_table("chain_data")


def downgrade() -> None:
    tables = _existing_tables()
    if "chain_data" not in tables:
        op.create_table(
            "chain_data",
            sa.Column("id", sa.INTEGER(), nullable=False),
            sa.Column("chain_name", sa.VARCHAR(length=64), nullable=False),
            sa.Column("usdt_supply", sa.FLOAT(), nullable=False),
            sa.Column("tvl", sa.FLOAT(), nullable=True),
            sa.Column("price", sa.FLOAT(), nullable=True),
            sa.Column("fetched_at", sa.DATETIME(), nullable=False),
            sa.Column("updated_at", sa.DATETIME(), nullable=False),
            sa.Column("usdt_supply_prev_day", sa.FLOAT(), nullable=True),
            sa.Column("usdt_supply_prev_week", sa.FLOAT(), nullable=True),
            sa.Column("usdt_supply_prev_month", sa.FLOAT(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_chain_data_id"), "chain_data", ["id"], unique=False)
        op.create_index(op.f("ix_chain_data_chain_name"), "chain_data", ["chain_name"], unique=True)

    for col in (
        "pool_count",
        "top3_pool_share_pct",
        "total_liquidity_usd",
        "volume_24h",
        "market_cap",
        "price_dexscreener",
        "price_coingecko",
    ):
        if "asset_chain_snapshots" in tables and _has_column("asset_chain_snapshots", col):
            op.drop_column("asset_chain_snapshots", col)

    if "osint_articles" in tables:
        op.drop_index(op.f("ix_osint_articles_source"), table_name="osint_articles")
        op.drop_index(op.f("ix_osint_articles_id"), table_name="osint_articles")
        op.drop_table("osint_articles")
