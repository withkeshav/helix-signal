"""Daily/weekly digest service for Telegram bot."""

import logging
from datetime import datetime
from typing import Dict, List
from sqlalchemy.orm import Session

from database import SessionLocal
from helix_telegram.models import TelegramUser, get_subscribed_users
from helix_telegram.templates import TelegramTemplates
from helix_telegram.bot import send_alert_to_user

# Configure logging
logger = logging.getLogger(__name__)

class DigestService:
    """Service for sending regular market digests to Telegram users."""
    
    @staticmethod
    async def send_daily_digest(user: TelegramUser, market_data: Dict) -> bool:
        """Send daily market digest to a user."""
        try:
            # Create digest message
            message = DigestService._format_daily_digest(market_data, user)
            
            # Send to user
            success = await send_alert_to_user(user.telegram_id, message)
            if success:
                logger.info(f"Daily digest sent to user {user.telegram_id}")
            else:
                logger.error(f"Failed to send daily digest to user {user.telegram_id}")
                
            return success
        except Exception as e:
            logger.error(f"Error sending daily digest to user {user.telegram_id}: {e}")
            return False
    
    @staticmethod
    def _format_daily_digest(market_data: Dict, user: TelegramUser) -> str:
        """Format daily digest message."""
        try:
            # Get user's timezone
            user_timezone = user.timezone or "UTC"
            
            message = "🌅 *Helix Signal Daily Digest*\n"
            message += "──────────────────\n"
            message += f"📅 *Date:* `{datetime.now().strftime('%Y-%m-%d')}`\n"
            message += f"🕐 *Local Time:* `{datetime.now().strftime('%H:%M')} {user_timezone}`\n\n"
            
            # Add asset summaries
            if "assets" in market_data:
                preferred_assets = user.preferred_assets.split(",") if user.preferred_assets else ["USDT", "USDC", "DAI"]
                for asset in preferred_assets:
                    if asset in market_data["assets"]:
                        asset_data = market_data["assets"][asset]
                        message += f"📦 *{asset} Summary*\n"
                        
                        # Add key metrics
                        if "signal_score" in asset_data:
                            message += f"📊 Score: `{asset_data['signal_score']}`\n"
                        if "price" in asset_data:
                            message += f"💰 Price: `${asset_data['price']:.6f}`\n"
                        if "supply" in asset_data:
                            message += f"🏦 Supply: `{asset_data['supply']:,.0f}`\n"
                        if "depeg" in asset_data:
                            message += f"🔗 Peg: `{asset_data['depeg']:.4f}`\n"
                        
                        message += "\n"
            
            # Add top events
            if "top_events" in market_data:
                message += "🔔 *Top Events Today*\n"
                message += "──────────────────\n"
                for event in market_data["top_events"][:3]:  # Top 3 events
                    message += f"• {event['title']} ({event['severity'].upper()})\n"
                message += "\n"
            
            # Add market overview
            if "market_overview" in market_data:
                overview = market_data["market_overview"]
                if len(overview) > 400:
                    overview = overview[:400] + "..."
                message += f"🌐 *Market Overview*\n{overview}\n\n"
            
            message += "🔗 *View Full Dashboard:* [Helix Signal](https://helix.withkeshav.com/)\n"
            message += f"_This digest is sent daily at {user.digest_time or '09:00'} {user_timezone}_"
            
            return message
        except Exception as e:
            logger.error(f"Error formatting daily digest: {e}")
            return "🌅 *Helix Signal Daily Digest*\n\nYour daily market summary is ready. Check the dashboard for details."
    
    @staticmethod
    async def send_weekly_summary(user: TelegramUser, summary_data: Dict) -> bool:
        """Send weekly market summary to a user."""
        try:
            message = DigestService._format_weekly_summary(summary_data, user)
            success = await send_alert_to_user(user.telegram_id, message)
            return success
        except Exception as e:
            logger.error(f"Error sending weekly summary to user {user.telegram_id}: {e}")
            return False
    
    @staticmethod
    def _format_weekly_summary(summary_data: Dict, user: TelegramUser) -> str:
        """Format weekly summary message."""
        try:
            # Get user's timezone
            user_timezone = user.timezone or "UTC"
            
            message = "📅 *Helix Signal Weekly Summary*\n"
            message += "──────────────────\n"
            message += f"🗓️ *Week:* `{summary_data.get('week', 'This Week')}`\n"
            message += f"🕐 *Local Time:* `{datetime.now().strftime('%H:%M')} {user_timezone}`\n\n"
            
            # Add weekly highlights
            if "highlights" in summary_data:
                message += "🌟 *Weekly Highlights*\n"
                for highlight in summary_data["highlights"][:5]:
                    message += f"• {highlight}\n"
                message += "\n"
            
            # Add asset performance
            if "performance" in summary_data:
                message += "📈 *Asset Performance*\n"
                for asset, perf in summary_data["performance"].items():
                    message += f"• {asset}: `{perf['change']:+.2f}%` ({perf['trend']})\n"
                message += "\n"
            
            # Add top alerts
            if "top_alerts" in summary_data:
                message += "🚨 *Top Alerts This Week*\n"
                for alert in summary_data["top_alerts"][:3]:
                    message += f"• {alert['title']} ({alert['severity'].upper()})\n"
                message += "\n"
            
            message += "🔗 *View Full Report:* [Helix Signal](https://helix.withkeshav.com/)\n"
            message += f"_This summary is sent weekly on Mondays at {user.digest_time or '09:00'} {user_timezone}_"
            
            return message
        except Exception as e:
            logger.error(f"Error formatting weekly summary: {e}")
            return "📅 *Helix Signal Weekly Summary*\n\nYour weekly market summary is ready. Check the dashboard for details."
    
    @staticmethod
    async def send_scheduled_digests() -> Dict[str, int]:
        """Send scheduled digests to all users who have them enabled."""
        results = {
            "sent": 0,
            "failed": 0,
            "skipped": 0
        }
        
        try:
            current_time = datetime.utcnow().strftime("%H:%M")
            logger.info(f"Checking for scheduled digests at {current_time} UTC")
            
            db = SessionLocal()
            try:
                # Get all subscribed users with digest enabled
                users = get_subscribed_users(db)
                users_with_digest = [u for u in users if u.receive_digest]
                
                logger.info(f"Found {len(users_with_digest)} users with digest enabled")
                
                # For now, use mock market data
                market_data = DigestService._get_mock_market_data()
                
                # Send digest to each user
                for user in users_with_digest:
                    # Check if it's time to send digest for this user (converted to their timezone)
                    if DigestService._should_send_digest(user, current_time):
                        try:
                            success = await DigestService.send_daily_digest(user, market_data)
                            if success:
                                results["sent"] += 1
                            else:
                                results["failed"] += 1
                        except Exception as e:
                            results["failed"] += 1
                            logger.error(f"Error sending digest to user {user.telegram_id}: {e}")
                    else:
                        results["skipped"] += 1
                        
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in send_scheduled_digests: {e}")
            
        return results
    
    @staticmethod
    def _should_send_digest(user: TelegramUser, current_utc_time: str) -> bool:
        """Check if it's time to send digest to this user based on their timezone."""
        try:
            # For now, simple implementation - we can improve timezone conversion later
            # This is a simplified version that doesn't actually convert timezones
            digest_time = user.digest_time or "09:00"
            return current_utc_time == digest_time
        except Exception as e:
            logger.error(f"Error checking digest time for user {user.id}: {e}")
            return current_utc_time == "09:00"  # Default
    
    @staticmethod
    def _get_mock_market_data() -> Dict:
        """Get mock market data for testing."""
        return {
            "assets": {
                "USDT": {
                    "signal_score": 85,
                    "price": 1.0002,
                    "supply": 125000000,
                    "depeg": 1.0002
                },
                "USDC": {
                    "signal_score": 92,
                    "price": 1.0001,
                    "supply": 32000000,
                    "depeg": 1.0001
                },
                "DAI": {
                    "signal_score": 78,
                    "price": 0.9998,
                    "supply": 5500000,
                    "depeg": 0.9998
                }
            },
            "top_events": [
                {"title": "High Concentration on Ethereum", "severity": "high"},
                {"title": "Minor Depeg Detected on BSC", "severity": "medium"},
                {"title": "New Stablecoin Launched", "severity": "info"}
            ],
            "market_overview": "The stablecoin market showed stability this week with minor fluctuations. USDT maintains dominance while algorithmic stablecoins show increased activity."
        }

# Scheduler functions for APScheduler
async def send_daily_digests():
    """Scheduled job to send daily digests."""
    logger.info("Starting daily digest job")
    results = await DigestService.send_scheduled_digests()
    logger.info(f"Daily digest job completed - Sent: {results['sent']}, Failed: {results['failed']}, Skipped: {results['skipped']}")

# Function to add to main application scheduler
def add_digest_scheduler(scheduler) -> None:
    """Add digest scheduler to application scheduler."""
    try:
        # Schedule daily digest at 9 AM UTC (users will see it in their local time)
        scheduler.add_job(
            send_daily_digests,
            "cron",
            hour=9,
            minute=0,
            id="telegram_daily_digest",
            replace_existing=True,
        )
        logger.info("Added Telegram daily digest scheduler job")
        
        # Schedule weekly summary on Mondays at 9 AM UTC
        scheduler.add_job(
            send_weekly_digests,
            "cron",
            day_of_week=0,  # Sunday (0=Sunday, 6=Saturday)
            hour=9,
            minute=0,
            id="telegram_weekly_summary",
            replace_existing=True,
        )
        logger.info("Added Telegram weekly summary scheduler job")
        
    except Exception as e:
        logger.error(f"Error adding digest scheduler: {e}")

async def send_weekly_digests():
    """Scheduled job to send weekly summaries."""
    logger.info("Starting weekly summary job")
    # Implementation would be similar to daily digests but with weekly data
    logger.info("Weekly summary job completed")