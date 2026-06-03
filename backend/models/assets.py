"""Core asset models."""

from datetime import datetime
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AssetChainSnapshot(Base):
    __tablename__ = "asset_chain_snapshots"
    __table_args__ = (UniqueConstraint("asset_symbol", "chain_name", name="uq_asset_chain_snapshot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_symbol: Mapped[str] = mapped_column(String(16), index=True)
    asset_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chain_name: Mapped[str] = mapped_column(String(64), index=True)
    supply_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    supply_prev_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    supply_prev_week: Mapped[float | None] = mapped_column(Float, nullable=True)
    supply_prev_month: Mapped[float | None] = mapped_column(Float, nullable=True)
    tvl: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_coingecko: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_dexscreener: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_24h: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_liquidity_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    top3_pool_share_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    pool_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peg_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_name: Mapped[str] = mapped_column(String(64), default="multi")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
    )


class AssetTrendSnapshot(Base):
    """One asset-level aggregate row per successful refresh bucket (5-minute UTC bucket)."""

    __tablename__ = "asset_trend_snapshots"
    __table_args__ = (
        UniqueConstraint("asset_symbol", "bucket_id", name="uq_asset_trend_bucket"),
        Index("ix_asset_trend_asset_ts", "asset_symbol", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_symbol: Mapped[str] = mapped_column(String(16), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    bucket_id: Mapped[int] = mapped_column(Integer, index=True)
    total_supply: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    depeg_index: Mapped[int] = mapped_column(Integer, default=0)
    signal_score: Mapped[int] = mapped_column(Integer, default=0)
    signal_band: Mapped[str] = mapped_column(String(16), default="Normal")
    concentration_score: Mapped[int] = mapped_column(Integer, default=0)
    data_confidence_label: Mapped[str] = mapped_column(String(16), default="Unknown")
    source_status: Mapped[str] = mapped_column(String(32), default="unknown")
    cross_source_discrepancy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
    )


class ChainTrendSnapshot(Base):
    """One chain-level row per asset per refresh bucket."""

    __tablename__ = "chain_trend_snapshots"
    __table_args__ = (
        UniqueConstraint("asset_symbol", "chain_key", "bucket_id", name="uq_chain_trend_bucket"),
        Index("ix_chain_trend_asset_chain_ts", "asset_symbol", "chain_key", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_symbol: Mapped[str] = mapped_column(String(16), index=True)
    chain_key: Mapped[str] = mapped_column(String(64), index=True)
    chain_name: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    bucket_id: Mapped[int] = mapped_column(Integer, index=True)
    supply: Mapped[float | None] = mapped_column(Float, nullable=True)
    supply_share_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    chain_tvl: Mapped[float | None] = mapped_column(Float, nullable=True)
    chain_signal_score: Mapped[int] = mapped_column(Integer, default=0)
    chain_signal_band: Mapped[str] = mapped_column(String(16), default="Normal")
    data_confidence_score: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
    )