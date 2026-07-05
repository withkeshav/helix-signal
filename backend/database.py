import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, JSON, UniqueConstraint, create_engine, func, text, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool


def _default_database_url() -> str:
    db_path = Path(__file__).resolve().parent / "helix.db"
    return f"sqlite:///{db_path.as_posix()}"


DATABASE_URL = os.getenv("DATABASE_URL", _default_database_url())

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
_pool_kw: dict = {}
if DATABASE_URL in ("sqlite:///:memory:", "sqlite://"):
    _pool_kw["poolclass"] = StaticPool
elif DATABASE_URL.startswith("postgresql"):
    _pool_kw["pool_pre_ping"] = True
    _pool_kw["pool_recycle"] = 3600
    _pool_kw["pool_size"] = 10
    _pool_kw["max_overflow"] = 20
else:
    # For SQLite, set pool settings for better performance
    _pool_kw["pool_size"] = 5
    _pool_kw["max_overflow"] = 10
    _pool_kw["pool_pre_ping"] = True
    _pool_kw["pool_recycle"] = 3600
engine = create_engine(DATABASE_URL, connect_args=connect_args, **_pool_kw)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class AssetChainSnapshot(Base):
    __tablename__ = "asset_chain_snapshots"
    __table_args__ = (
        UniqueConstraint("asset_symbol", "chain_name", name="uq_asset_chain_snapshot"),
        Index("ix_asset_chain_asset_symbol", "asset_symbol"),
        Index("ix_asset_chain_chain_name", "chain_name"),
        Index("ix_asset_chain_fetched_at", "fetched_at"),
        Index("ix_asset_chain_updated_at", "updated_at"),
    )

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
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class SourceStatus(Base):
    __tablename__ = "source_status"
    __table_args__ = (
        Index("ix_source_status_name", "source_name"),
        Index("ix_source_status_status", "status"),
        Index("ix_source_status_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    previous_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_attempted_fetch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_fetch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class AssetFreshness(Base):
    """Per-asset last-successful-fetch tracking."""

    __tablename__ = "asset_freshness"
    __table_args__ = (
        Index("ix_asset_freshness_asset_symbol", "asset_symbol"),
        Index("ix_asset_freshness_last_fetch", "last_successful_fetch"),
        Index("ix_asset_freshness_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_symbol: Mapped[str] = mapped_column(String(16), unique=True)
    last_successful_fetch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class AssetTrendSnapshot(Base):
    """One asset-level aggregate row per successful refresh bucket (5-minute UTC bucket)."""

    __tablename__ = "asset_trend_snapshots"
    __table_args__ = (
        UniqueConstraint("asset_symbol", "bucket_id", name="uq_asset_trend_bucket"),
        Index("ix_asset_trend_asset_ts", "asset_symbol", "timestamp"),
        Index("ix_asset_trend_asset_symbol", "asset_symbol"),
        Index("ix_asset_trend_timestamp", "timestamp"),
        Index("ix_asset_trend_bucket_id", "bucket_id"),
        Index("ix_asset_trend_signal_band", "signal_band"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_symbol: Mapped[str] = mapped_column(String(16), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    bucket_id: Mapped[int] = mapped_column(Integer, index=True)
    total_supply: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    depeg_index: Mapped[int] = mapped_column(Integer, default=0)
    signal_score: Mapped[int] = mapped_column(Integer, default=0)
    signal_band: Mapped[str] = mapped_column(String(16), default="Normal", index=True)
    concentration_score: Mapped[int] = mapped_column(Integer, default=0)
    data_confidence_label: Mapped[str] = mapped_column(String(16), default="Unknown")
    source_status: Mapped[str] = mapped_column(String(32), default="unknown")
    cross_source_discrepancy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class ChainTrendSnapshot(Base):
    """One chain-level row per asset per refresh bucket."""

    __tablename__ = "chain_trend_snapshots"
    __table_args__ = (
        UniqueConstraint("asset_symbol", "chain_key", "bucket_id", name="uq_chain_trend_bucket"),
        Index("ix_chain_trend_asset_chain_ts", "asset_symbol", "chain_key", "timestamp"),
        Index("ix_chain_trend_asset_symbol", "asset_symbol"),
        Index("ix_chain_trend_chain_key", "chain_key"),
        Index("ix_chain_trend_timestamp", "timestamp"),
        Index("ix_chain_trend_bucket_id", "bucket_id"),
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
        default=lambda: datetime.now(timezone.utc),
    )


class OsintArticle(Base):
    __tablename__ = "osint_articles"
    __table_args__ = (
        Index("ix_osint_articles_published_at", "published_at"),
        Index("ix_osint_articles_source_title", "source", "title"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    entities: Mapped[str | None] = mapped_column(Text, nullable=True)
    topics: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    driver_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_authority: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_leading_indicator: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    extracted_numbers_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    asset_links: Mapped[list["OsintArticleAsset"]] = relationship("OsintArticleAsset", back_populates="article", cascade="all, delete-orphan")


class OsintArticleAsset(Base):
    __tablename__ = "osint_article_assets"
    __table_args__ = (
        UniqueConstraint("article_id", "asset_symbol", name="uq_article_asset"),
        Index("ix_article_asset_article_id", "article_id"),
        Index("ix_article_asset_asset_symbol", "asset_symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    article_id: Mapped[int] = mapped_column(Integer, ForeignKey("osint_articles.id", ondelete="CASCADE"), nullable=False)
    asset_symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    article: Mapped["OsintArticle"] = relationship("OsintArticle", back_populates="asset_links")


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    target_metric: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    chain_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    input_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="completed")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ForecastPoint(Base):
    __tablename__ = "forecast_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("forecast_runs.id"), nullable=False, index=True)
    asset_symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    chain_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_metric: Mapped[str] = mapped_column(String(32), nullable=False)
    horizon_step: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    point_forecast: Mapped[float | None] = mapped_column(Float, nullable=True)
    q10: Mapped[float | None] = mapped_column(Float, nullable=True)
    q50: Mapped[float | None] = mapped_column(Float, nullable=True)
    q90: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SignalEvent(Base):
    """Local, explainable monitoring events (not external alerts)."""

    __tablename__ = "signal_events"
    __table_args__ = (
        Index("ix_signal_event_asset_symbol", "asset_symbol"),
        Index("ix_signal_event_chain_key", "chain_key"),
        Index("ix_signal_event_event_type", "event_type"),
        Index("ix_signal_event_severity", "severity"),
        Index("ix_signal_event_timestamp", "timestamp"),
        Index("ix_signal_event_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_symbol: Mapped[str] = mapped_column(String(16), index=True)
    chain_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(500))
    old_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    delta: Mapped[str | None] = mapped_column(String(128), nullable=True)
    threshold: Mapped[str | None] = mapped_column(String(128), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class SourceUsage(Base):
    """Per-source daily API call counters for rate limit visibility."""

    __tablename__ = "source_usage"
    __table_args__ = (
        UniqueConstraint("source_name", "usage_date", name="uq_source_usage_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_name: Mapped[str] = mapped_column(String(64), index=True)
    usage_date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    call_count: Mapped[int] = mapped_column(Integer, default=0)
    last_call_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class AiUsage(Base):
    """Per-AI-provider daily usage tracking: calls, tokens, cost."""

    __tablename__ = "ai_usage"
    __table_args__ = (
        UniqueConstraint("provider", "model", "usage_date", name="uq_ai_usage_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(64), default="")
    usage_date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    calls: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class User(Base):
    """User model for multi-user support."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(32), default="user")  # user, admin, viewer
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class Playbook(Base):
    """User-customizable configuration playbooks."""

    __tablename__ = "playbooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(String(500))
    settings: Mapped[dict] = mapped_column(JSON)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class SettingsAuditLog(Base):
    """Audit log for settings changes."""

    __tablename__ = "settings_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    setting_key: Mapped[str] = mapped_column(String(128), index=True)
    old_value: Mapped[str] = mapped_column(Text, nullable=True)
    new_value: Mapped[str] = mapped_column(Text, nullable=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    user_username: Mapped[str] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=True)  # IPv6 max length
    user_agent: Mapped[str] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


# ---- V4 additional models ----

class FiatReserveSnapshot(Base):
    """Fiat reserve attestation snapshots (Tether, Circle, Paxos, etc.)."""

    __tablename__ = "fiat_reserve_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    attestation_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reserve_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    circulating_supply: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    reserve_composition: Mapped[dict | None] = mapped_column(postgresql.JSON, nullable=True)
    attestation_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attestation_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attestation_lag_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    genius_act_compliant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    mica_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_fiat_reserve_asset_ts", "asset_symbol", "attestation_date"),
        Index("ix_fiat_reserve_created", "created_at"),
    )


class CollateralSnapshot(Base):
    """Crypto-collateralization snapshots (DAI, LUSD, GHO, etc.)."""

    __tablename__ = "collateral_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    collateral_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    collateral_assets_json: Mapped[dict | None] = mapped_column(postgresql.JSON, nullable=True)
    liquidation_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidation_queue_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    debt_ceiling_utilization_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    largest_vault_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    collateral_health_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_collateral_asset_ts", "asset_symbol", "timestamp"),
    )


class YieldBearingSnapshot(Base):
    """Yield-bearing stablecoin snapshots (sDAI, sUSDS, USDe, etc.)."""

    __tablename__ = "yield_bearing_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    current_apy: Mapped[float | None] = mapped_column(Float, nullable=True)
    apy_7d_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    apy_7d_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    yield_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    yield_sustainability: Mapped[float | None] = mapped_column(Float, nullable=True)
    funding_rate_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    funding_rate_7d_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    insurance_fund_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    insurance_fund_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    staking_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    lending_utilization_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_yield_bearing_asset_ts", "asset_symbol", "timestamp"),
    )


class FundingRateSnapshot(Base):
    """Per-exchange funding rate snapshots for perpetual swaps."""

    __tablename__ = "funding_rate_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exchange: Mapped[str | None] = mapped_column(String(50), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(30), nullable=True)
    funding_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    annualized_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    next_funding_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        Index("ix_funding_rate_exchange_ts", "exchange", "timestamp"),
    )


class WhaleActivitySnapshot(Base):
    """Holder concentration and large-transfer snapshots."""

    __tablename__ = "whale_activity_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    chain: Mapped[str | None] = mapped_column(String(50), nullable=True)
    top10_holder_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    top10_holder_pct_delta_24h: Mapped[float | None] = mapped_column(Float, nullable=True)
    large_transfer_count_24h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exchange_inflow_usd_24h: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        Index("ix_whale_asset_ts", "asset_symbol", "timestamp"),
    )


class BlacklistEvent(Base):
    """Issuer blacklist/freeze events across chains."""

    __tablename__ = "blacklist_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    chain: Mapped[str | None] = mapped_column(String(50), nullable=True)
    frozen_address: Mapped[str | None] = mapped_column(String(100), index=True)
    frozen_balance_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tx_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    block_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    intelligence_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_blacklist_asset_ts", "asset_symbol", "timestamp"),
        Index("ix_blacklist_frozen_addr", "frozen_address"),
    )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def upgrade_db() -> None:
    """Apply Alembic migrations (required for PostgreSQL/Timescale deployments)."""
    from alembic import command
    from alembic.config import Config

    ini_path = Path(__file__).resolve().parent / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(cfg, "head")


def _should_use_alembic() -> bool:
    explicit = os.getenv("HELIX_USE_ALEMBIC", "").strip().lower() in ("1", "true", "yes")
    return explicit or DATABASE_URL.startswith("postgresql")


def init_db() -> None:
    if _should_use_alembic():
        upgrade_db()
    else:
        Base.metadata.create_all(bind=engine)
    _migrate_legacy_chain_data()
    _seed_builtin_playbooks()


def _seed_builtin_playbooks() -> None:
    """Seed built-in playbooks into the database on first init."""
    try:
        with engine.connect() as conn:
            if not inspect(conn).has_table("playbooks"):
                return
    except Exception:
        return
    from datetime import datetime, timezone
    from providers.settings import PLAYBOOKS

    with SessionLocal() as session:
        existing = {
            pb.name
            for pb in session.query(Playbook).filter(Playbook.is_builtin.is_(True)).all()
        }
        now = datetime.now(timezone.utc)
        for name, data in PLAYBOOKS.items():
            if name not in existing:
                pb = Playbook(
                    name=name,
                    label=data["label"],
                    description=data["description"],
                    settings=dict(data["settings"]),
                    is_builtin=True,
                    created_at=now,
                    updated_at=now,
                )
                session.add(pb)
        session.commit()


def _migrate_legacy_chain_data() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as conn:
        chain_table_exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='chain_data'")
        ).fetchone()
        if not chain_table_exists:
            return

        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO asset_chain_snapshots
                (
                    asset_symbol, asset_name, chain_name, supply_current, supply_prev_day,
                    supply_prev_week, supply_prev_month, tvl, price, peg_type,
                    source_name, fetched_at, updated_at
                )
                SELECT
                    'USDT', 'Tether', chain_name, usdt_supply, usdt_supply_prev_day,
                    usdt_supply_prev_week, usdt_supply_prev_month, tvl, price, 'peggedUSD',
                    'defillama', fetched_at, updated_at
                FROM chain_data
                """
            )
        )
