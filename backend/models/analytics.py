"""Analytics models for usage tracking."""

from datetime import datetime
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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
        default=lambda: datetime.now(datetime.timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
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
        default=lambda: datetime.now(datetime.timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
    )