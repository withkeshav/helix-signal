"""Persistent database models for Telegram bot features."""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import Base

class TelegramReviewItem(Base):
    """Model for Telegram bot review queue items."""
    
    __tablename__ = "telegram_review_items"
    
    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(String(64), unique=True, index=True, nullable=False)
    alert_data = Column(Text, nullable=False)  # JSON serialized alert data
    score = Column(Float, nullable=False)  # Review priority score
    reviewed = Column(Boolean, default=False, nullable=False)
    approved = Column(Boolean, nullable=True)  # None = pending, True = approved, False = rejected
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<TelegramReviewItem(review_id='{self.review_id}', score={self.score}, reviewed={self.reviewed})>"

class TelegramRateLimit(Base):
    """Model for Telegram bot rate limiting state."""
    
    __tablename__ = "telegram_rate_limits"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    command_count = Column(Integer, default=0, nullable=False)
    last_reset = Column(DateTime, default=datetime.utcnow, nullable=False)
    window_seconds = Column(Integer, default=60, nullable=False)  # Rate limit window
    max_commands = Column(Integer, default=10, nullable=False)    # Max commands per window
    
    def __repr__(self):
        return f"<TelegramRateLimit(telegram_id={self.telegram_id}, count={self.command_count})>"