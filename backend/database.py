import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
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
engine = create_engine(DATABASE_URL, connect_args=connect_args, **_pool_kw)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


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
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class SourceStatus(Base):
    __tablename__ = "source_status"

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


class AssetTrendSnapshot(Base):
    """One asset-level aggregate row per successful refresh bucket (5-minute UTC bucket)."""

    __tablename__ = "asset_trend_snapshots"
    __table_args__ = (UniqueConstraint("asset_symbol", "bucket_id", name="uq_asset_trend_bucket"),)

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class ChainTrendSnapshot(Base):
    """One chain-level row per asset per refresh bucket."""

    __tablename__ = "chain_trend_snapshots"
    __table_args__ = (UniqueConstraint("asset_symbol", "chain_key", "bucket_id", name="uq_chain_trend_bucket"),)

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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_symbols: Mapped[str | None] = mapped_column(String(128), nullable=True)
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


class SignalEvent(Base):
    """Local, explainable monitoring events (not external alerts)."""

    __tablename__ = "signal_events"

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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
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
