"""Data quality models."""

from datetime import datetime
from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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
        default=lambda: datetime.now(datetime.timezone.utc),
    )


class AssetFreshness(Base):
    """Per-asset last-successful-fetch tracking."""

    __tablename__ = "asset_freshness"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    last_successful_fetch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
    )