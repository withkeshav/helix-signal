"""Telegram bot models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, Session

from .base import Base


class TelegramUser(Base):
    """Model for Telegram bot users."""
    
    __tablename__ = "telegram_users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=True)
    # Custom preferences
    preferred_assets: Mapped[Optional[str]] = mapped_column(String(512), default="USDT,USDC,DAI")  # Comma-separated list
    alert_types: Mapped[Optional[str]] = mapped_column(String(512), default="signal,anomaly,osint")  # Comma-separated list
    min_severity: Mapped[Optional[str]] = mapped_column(String(20), default="medium")  # critical,high,medium,low,info
    timezone: Mapped[Optional[str]] = mapped_column(String(50), default="UTC")  # User's timezone (e.g., "America/New_York")
    quiet_hours_start: Mapped[Optional[str]] = mapped_column(String(5), default="")  # Format: "HH:MM"
    quiet_hours_end: Mapped[Optional[str]] = mapped_column(String(5), default="")  # Format: "HH:MM"
    receive_digest: Mapped[bool] = mapped_column(Boolean, default=True)  # Daily digest
    digest_time: Mapped[Optional[str]] = mapped_column(String(5), default="09:00")  # Local time for digest
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())
    
    def __repr__(self):
        return f"<TelegramUser(telegram_id={self.telegram_id}, username='{self.username}', subscribed={self.is_subscribed})>"


class TelegramReviewItem(Base):
    """Model for Telegram bot review queue items."""
    
    __tablename__ = "telegram_review_items"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    review_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    alert_data: Mapped[str] = mapped_column(Text)  # JSON serialized alert data
    score: Mapped[float] = mapped_column(Float)  # Review priority score
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    approved: Mapped[Optional[bool]] = mapped_column(Boolean)  # None = pending, True = approved, False = rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<TelegramReviewItem(review_id='{self.review_id}', score={self.score}, reviewed={self.reviewed})>"


class TelegramRateLimit(Base):
    """Model for Telegram bot rate limiting state."""
    
    __tablename__ = "telegram_rate_limits"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    command_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reset: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())
    window_seconds: Mapped[int] = mapped_column(Integer, default=60)  # Rate limit window
    max_commands: Mapped[int] = mapped_column(Integer, default=10)    # Max commands per window
    
    def __repr__(self):
        return f"<TelegramRateLimit(telegram_id={self.telegram_id}, count={self.command_count})>"


# User management functions
def get_user_by_telegram_id(db: Session, telegram_id: int) -> Optional[TelegramUser]:
    """Get a Telegram user by their Telegram ID."""
    return db.query(TelegramUser).filter(TelegramUser.telegram_id == telegram_id).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[TelegramUser]:
    """Get a Telegram user by their database ID."""
    return db.query(TelegramUser).filter(TelegramUser.id == user_id).first()


def get_all_users(db: Session, skip: int = 0, limit: int = 100) -> List[TelegramUser]:
    """Get all Telegram users."""
    return db.query(TelegramUser).offset(skip).limit(limit).all()


def get_subscribed_users(db: Session) -> List[TelegramUser]:
    """Get all subscribed Telegram users."""
    return db.query(TelegramUser).filter(TelegramUser.is_subscribed).all()


def create_user(
    db: Session, 
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    is_subscribed: bool = True
) -> TelegramUser:
    """Create a new Telegram user."""
    db_user = TelegramUser(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        is_subscribed=is_subscribed
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def update_user_subscription(db: Session, telegram_id: int, is_subscribed: bool) -> bool:
    """Update a user's subscription status."""
    user = get_user_by_telegram_id(db, telegram_id)
    if user:
        old_status = user.is_subscribed
        user.is_subscribed = is_subscribed
        user.updated_at = datetime.utcnow()
        db.commit()
        return old_status != is_subscribed  # Return True if status changed
    return False


def delete_user(db: Session, telegram_id: int) -> bool:
    """Delete a Telegram user."""
    user = get_user_by_telegram_id(db, telegram_id)
    if user:
        db.delete(user)
        db.commit()
        return True
    return False


def update_user(
    db: Session,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None
) -> Optional[TelegramUser]:
    """Update a Telegram user's information."""
    user = get_user_by_telegram_id(db, telegram_id)
    if user:
        if username is not None:
            user.username = username
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        return user
    return None