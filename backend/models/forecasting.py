"""Forecasting models."""

from datetime import datetime
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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
        DateTime(timezone=True), default=lambda: datetime.now(datetime.timezone.utc)
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
        DateTime(timezone=True), default=lambda: datetime.now(datetime.timezone.utc)
    )