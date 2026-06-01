"""Telegram bot rate limiting middleware."""

import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class RateLimitEntry:
    """Rate limit entry for a user."""
    count: int = 0
    last_reset: float = field(default_factory=time.time)
    
    def should_reset(self, window_seconds: int) -> bool:
        """Check if the rate limit window should be reset."""
        return time.time() - self.last_reset > window_seconds

class TelegramRateLimiter:
    """In-memory rate limiter for Telegram bot commands."""
    
    def __init__(self, max_commands: int = 10, window_seconds: int = 60):
        """
        Initialize rate limiter.
        
        Args:
            max_commands: Maximum commands allowed per window
            window_seconds: Time window in seconds
        """
        self.max_commands = max_commands
        self.window_seconds = window_seconds
        self.limits: Dict[int, RateLimitEntry] = {}  # telegram_id -> RateLimitEntry
    
    def is_allowed(self, telegram_id: int) -> bool:
        """
        Check if a user is allowed to execute a command.
        
        Args:
            telegram_id: Telegram user ID
            
        Returns:
            bool: True if allowed, False if rate limited
        """
        now = time.time()
        
        # Get or create rate limit entry
        entry = self.limits.get(telegram_id)
        if not entry:
            entry = RateLimitEntry(count=1, last_reset=now)
            self.limits[telegram_id] = entry
            return True
        
        # Check if window should be reset
        if entry.should_reset(self.window_seconds):
            entry.count = 1
            entry.last_reset = now
            return True
        
        # Check if within limit
        if entry.count < self.max_commands:
            entry.count += 1
            return True
        
        # Rate limited
        return False
    
    def get_remaining(self, telegram_id: int) -> int:
        """
        Get remaining commands for a user.
        
        Args:
            telegram_id: Telegram user ID
            
        Returns:
            int: Number of remaining commands in current window
        """
        entry = self.limits.get(telegram_id)
        if not entry:
            return self.max_commands
        
        if entry.should_reset(self.window_seconds):
            return self.max_commands
            
        return max(0, self.max_commands - entry.count)
    
    def get_reset_time(self, telegram_id: int) -> Optional[datetime]:
        """
        Get when the rate limit will reset for a user.
        
        Args:
            telegram_id: Telegram user ID
            
        Returns:
            datetime: When rate limit will reset, or None if not rate limited
        """
        entry = self.limits.get(telegram_id)
        if not entry:
            return None
            
        if entry.should_reset(self.window_seconds):
            return None
            
        reset_timestamp = entry.last_reset + self.window_seconds
        return datetime.fromtimestamp(reset_timestamp)
    
    def cleanup(self) -> None:
        """Remove expired rate limit entries."""
        now = time.time()
        expired_users = [
            user_id for user_id, entry in self.limits.items()
            if now - entry.last_reset > self.window_seconds * 2  # Keep for 2 windows
        ]
        for user_id in expired_users:
            del self.limits[user_id]

# Global rate limiter instance
rate_limiter = TelegramRateLimiter(max_commands=10, window_seconds=60)