"""Telegram bot middleware for rate limiting and other protections."""

import logging
from typing import Callable, Any

from telegram import Update
from telegram.ext import ContextTypes

from helix_telegram.ratelimit import rate_limiter

logger = logging.getLogger(__name__)

class RateLimitMiddleware:
    """Middleware to handle rate limiting for Telegram bot commands."""
    
    @staticmethod
    async def check_rate_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Check if user is rate limited.
        
        Args:
            update: Telegram update
            context: Telegram context
            
        Returns:
            bool: True if allowed, False if rate limited
        """
        # Only check for message updates with user
        if not update.effective_user:
            return True
            
        telegram_id = update.effective_user.id
        
        # Check rate limit
        if not rate_limiter.is_allowed(telegram_id):
            # User is rate limited, send message
            remaining = rate_limiter.get_remaining(telegram_id)
            reset_time = rate_limiter.get_reset_time(telegram_id)
            
            if reset_time:
                reset_str = reset_time.strftime("%H:%M:%S UTC")
                message = f"⏳ Rate limit exceeded. Please wait until {reset_str} to try again."
            else:
                message = "⏳ Rate limit exceeded. Please wait a moment and try again."
                
            try:
                await update.message.reply_text(message)
            except Exception as e:
                logger.warning(f"Could not send rate limit message: {e}")
            
            return False
            
        return True

# Global middleware instance
telegram_middleware = RateLimitMiddleware()