"""Database models for Telegram bot."""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import Session

from database import Base

class TelegramUser(Base):
    """Model for Telegram bot users."""
    
    __tablename__ = "telegram_users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String(128), nullable=True)
    first_name = Column(String(128), nullable=True)
    last_name = Column(String(128), nullable=True)
    is_subscribed = Column(Boolean, default=True, nullable=False)
    # Custom preferences
    preferred_assets = Column(String(512), default="USDT,USDC,DAI", nullable=True)  # Comma-separated list
    alert_types = Column(String(512), default="signal,anomaly,osint", nullable=True)  # Comma-separated list
    min_severity = Column(String(20), default="medium", nullable=True)  # critical,high,medium,low,info
    timezone = Column(String(50), default="UTC", nullable=True)  # User's timezone (e.g., "America/New_York")
    quiet_hours_start = Column(String(5), default="", nullable=True)  # Format: "HH:MM"
    quiet_hours_end = Column(String(5), default="", nullable=True)  # Format: "HH:MM"
    receive_digest = Column(Boolean, default=True, nullable=False)  # Daily digest
    digest_time = Column(String(5), default="09:00", nullable=True)  # Local time for digest
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<TelegramUser(telegram_id={self.telegram_id}, username='{self.username}', subscribed={self.is_subscribed})>"

def get_user_by_telegram_id(db: Session, telegram_id: int) -> Optional[TelegramUser]:
    """Get a Telegram user by their Telegram ID."""
    return db.query(TelegramUser).filter(TelegramUser.telegram_id == telegram_id).first()

def get_user_by_id(db: Session, user_id: int) -> Optional[TelegramUser]:
    """Get a Telegram user by their database ID."""
    return db.query(TelegramUser).filter(TelegramUser.id == user_id).first()

def get_all_users(db: Session, skip: int = 0, limit: int = 100) -> list[TelegramUser]:
    """Get all Telegram users."""
    return db.query(TelegramUser).offset(skip).limit(limit).all()

def get_subscribed_users(db: Session) -> list[TelegramUser]:
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