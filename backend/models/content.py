"""Content models for OSINT and signals."""

from datetime import datetime
from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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
        default=lambda: datetime.now(datetime.timezone.utc),
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
        default=lambda: datetime.now(datetime.timezone.utc),
    )