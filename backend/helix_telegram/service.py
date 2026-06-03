"""Telegram service for Helix Signal - integrates with alerting system."""

import logging
import os
from typing import List
from sqlalchemy.orm import Session

from database import SessionLocal
from helix_telegram.models import get_subscribed_users
from helix_telegram.bot import send_alert_to_user, send_alert_to_channel

# Configure logging
logger = logging.getLogger(__name__)

# Get channel name from settings
TELEGRAM_CHANNEL = ""
try:
    from providers.settings import get_setting
    TELEGRAM_CHANNEL = get_setting("telegram_channel") or ""
except Exception:
    TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL", "").strip()

def format_alert_message(alert_data: dict) -> str:
    """Format an alert into a readable Telegram message."""
    try:
        # Extract alert information
        asset = alert_data.get("asset", "Unknown")
        severity = alert_data.get("severity", "info").upper()
        title = alert_data.get("title", "Alert")
        summary = alert_data.get("summary", "")
        
        # Create emoji based on severity
        severity_emojis = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
            "info": "ℹ️"
        }
        emoji = severity_emojis.get(severity.lower(), "ℹ️")
        
        # Build the message
        message = f"{emoji} *{title}*\n\n"
        message += f"*Asset:* {asset}\n"
        message += f"*Severity:* {severity}\n\n"
        
        if summary:
            # Truncate summary if too long for Telegram
            if len(summary) > 800:
                summary = summary[:800] + "..."
            message += f"{summary}\n\n"
            
        # Add timestamp if available
        if "timestamp" in alert_data:
            message += f"_Timestamp: {alert_data['timestamp']}_"
            
        return message
    except Exception as e:
        logger.error(f"Error formatting alert message: {e}")
        return "🔔 *New Alert*\n\nAn alert has been triggered."

async def send_alert_to_subscribers(alert_data: dict) -> dict:
    """Send an alert to all subscribed Telegram users."""
    results = {
        "sent": 0,
        "failed": 0,
        "errors": []
    }
    
    try:
        # Format the message
        message = format_alert_message(alert_data)
        
        # Get all subscribed users
        db = SessionLocal()
        try:
            users = get_subscribed_users(db)
            logger.info(f"Sending alert to {len(users)} subscribed users")
            
            # Send to each user
            for user in users:
                try:
                    success = await send_alert_to_user(user.telegram_id, message)
                    if success:
                        results["sent"] += 1
                    else:
                        results["failed"] += 1
                        results["errors"].append(f"Failed to send to user {user.telegram_id}")
                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append(f"Exception sending to user {user.telegram_id}: {str(e)}")
                    logger.error(f"Error sending alert to user {user.telegram_id}: {e}")
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error sending alert to subscribers: {e}")
        results["errors"].append(f"General error: {str(e)}")
        
    return results

async def send_alert_to_telegram_channel(alert_data: dict) -> bool:
    """Send an alert to the configured Telegram channel."""
    if not TELEGRAM_CHANNEL:
        logger.info("TELEGRAM_CHANNEL not configured. Skipping channel notification.")
        return False
        
    try:
        message = format_alert_message(alert_data)
        success = await send_alert_to_channel(TELEGRAM_CHANNEL, message)
        return success
    except Exception as e:
        logger.error(f"Error sending alert to Telegram channel: {e}")
        return False

def is_telegram_enabled() -> bool:
    """Check if Telegram integration is enabled."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    return bool(token)

def get_telegram_stats() -> dict:
    """Get statistics about Telegram users."""
    try:
        db = SessionLocal()
        try:
            from helix_telegram.models import get_all_users
            all_users = get_all_users(db)
            subscribed_users = [u for u in all_users if u.is_subscribed]
            
            return {
                "total_users": len(all_users),
                "subscribed_users": len(subscribed_users),
                "unsubscribed_users": len(all_users) - len(subscribed_users)
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error getting Telegram stats: {e}")
        return {
            "total_users": 0,
            "subscribed_users": 0,
            "unsubscribed_users": 0,
            "error": str(e)
        }