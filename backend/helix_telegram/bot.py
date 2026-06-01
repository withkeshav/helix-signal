"""Telegram bot implementation for Helix Signal."""

import logging
import os
from typing import Optional

from telegram import Update as TelegramUpdate, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Aliases for convenience
Update = TelegramUpdate

from database import SessionLocal
from helix_telegram.models import TelegramUser, get_user_by_telegram_id, create_user, update_user_subscription
from helix_telegram.commands import signal_command, brief_command, price_command, refer_command
from helix_telegram.middleware import telegram_middleware

# Configure logging
logger = logging.getLogger(__name__)

# Get bot token from environment
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

async def start_command(update: TelegramUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    try:
        telegram_id = update.effective_user.id
        username = update.effective_user.username or "Anonymous"
        first_name = update.effective_user.first_name or ""
        last_name = update.effective_user.last_name or ""
        full_name = f"{first_name} {last_name}".strip() or username

        # Create or update user in database
        db = SessionLocal()
        try:
            user = get_user_by_telegram_id(db, telegram_id)
            if not user:
                user = create_user(
                    db, 
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    is_subscribed=True
                )
                welcome_message = f"👋 Welcome to Helix Signal, {full_name}!\n\n"
                welcome_message += "You're now subscribed to receive alerts about stablecoin risks and anomalies.\n\n"
                welcome_message += "Use /help to see available commands.\n"
                welcome_message += "Use /settings to customize your alerts."
            else:
                welcome_message = f"👋 Welcome back, {full_name}!\n\n"
                welcome_message += "You're subscribed to receive alerts.\n\n"
                welcome_message += "Use /help to see available commands.\n"
                welcome_message += "Use /settings to customize your alerts."
        finally:
            db.close()

        await update.message.reply_text(welcome_message)
    except Exception as e:
        logger.error(f"Error in start_command: {e}")
        await update.message.reply_text("❌ Sorry, something went wrong. Please try again later.")

async def help_command(update: TelegramUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = """
🤖 *Helix Signal Bot Commands*

/start - Start the bot and subscribe to alerts
/help - Show this help message
/subscribe - Subscribe to receive alerts
/unsubscribe - Unsubscribe from alerts
/status - Check your subscription status
/settings - Customize your alert preferences
/digest - Enable/disable daily digest
/alerts - List recent alerts (last 5)

📝 *What this bot does:*
This bot sends you alerts about stablecoin risks, anomalies, and important events from Helix Signal.

🔔 You're currently subscribed to receive alerts.
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def subscribe_command(update: TelegramUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /subscribe command."""
    try:
        telegram_id = update.effective_user.id
        db = SessionLocal()
        try:
            user = get_user_by_telegram_id(db, telegram_id)
            if user:
                if update_user_subscription(db, telegram_id, is_subscribed=True):
                    message = "✅ You are now subscribed to receive alerts!"
                else:
                    message = "✅ You were already subscribed to alerts!"
            else:
                message = "❌ Please use /start first to register with the bot."
        finally:
            db.close()
            
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error in subscribe_command: {e}")
        await update.message.reply_text("❌ Sorry, something went wrong. Please try again later.")

async def unsubscribe_command(update: TelegramUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /unsubscribe command."""
    try:
        telegram_id = update.effective_user.id
        db = SessionLocal()
        try:
            user = get_user_by_telegram_id(db, telegram_id)
            if user:
                if update_user_subscription(db, telegram_id, is_subscribed=False):
                    message = "🔕 You have been unsubscribed from alerts."
                else:
                    message = "🔕 You were already unsubscribed from alerts."
            else:
                message = "❌ Please use /start first to register with the bot."
        finally:
            db.close()
            
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error in unsubscribe_command: {e}")
        await update.message.reply_text("❌ Sorry, something went wrong. Please try again later.")

async def status_command(update: TelegramUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command."""
    try:
        telegram_id = update.effective_user.id
        db = SessionLocal()
        try:
            user = get_user_by_telegram_id(db, telegram_id)
            if user:
                status = "✅ Subscribed" if user.is_subscribed else "🔕 Unsubscribed"
                timezone = user.timezone or "UTC"
                digest_status = "✅ Enabled" if user.receive_digest else "❌ Disabled"
                digest_time = user.digest_time or "09:00"
                
                message = "👤 *Your Status*\n\n"
                message += f"Status: {status}\n"
                message += f"Timezone: {timezone}\n"
                message += f"Daily Digest: {digest_status}\n"
                message += f"Digest Time: {digest_time} {timezone}\n"
                message += f"Subscribed since: {user.created_at.strftime('%Y-%m-%d %H:%M UTC')}"
            else:
                message = "❌ You're not registered. Please use /start first."
        finally:
            db.close()
            
        await update.message.reply_text(message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in status_command: {e}")
        await update.message.reply_text("❌ Sorry, something went wrong. Please try again later.")

async def settings_command(update: TelegramUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command - customize alert preferences."""
    try:
        telegram_id = update.effective_user.id
        db = SessionLocal()
        try:
            user = get_user_by_telegram_id(db, telegram_id)
            if user:
                # Parse arguments if provided
                if context.args:
                    # Handle setting updates
                    setting = context.args[0] if len(context.args) > 0 else None
                    value = context.args[1] if len(context.args) > 1 else None
                    
                    if setting and value:
                        # Update specific setting
                        updated = False
                        if setting == "timezone" and value:
                            user.timezone = value
                            updated = True
                        elif setting == "digest" and value.lower() in ["on", "off"]:
                            user.receive_digest = value.lower() == "on"
                            updated = True
                        elif setting == "digest_time" and value:
                            # Validate time format
                            if ":" in value and len(value) == 5:
                                user.digest_time = value
                                updated = True
                        
                        if updated:
                            db.commit()
                            await update.message.reply_text(f"✅ Setting '{setting}' updated to '{value}'")
                            return
                
                # Show current settings
                timezone = user.timezone or "UTC"
                digest_status = "✅ Enabled" if user.receive_digest else "❌ Disabled"
                digest_time = user.digest_time or "09:00"
                assets = user.preferred_assets or "USDT,USDC,DAI"
                alert_types = user.alert_types or "signal,anomaly,osint"
                min_severity = user.min_severity or "medium"
                
                message = "⚙️ *Your Alert Settings*\n\n"
                message += f"Timezone: `{timezone}`\n"
                message += f"Daily Digest: {digest_status}\n"
                message += f"Digest Time: `{digest_time}`\n"
                message += f"Assets: `{assets}`\n"
                message += f"Alert Types: `{alert_types}`\n"
                message += f"Min Severity: `{min_severity}`\n\n"
                message += "*To update settings:*\n"
                message += "`/settings timezone America/New_York`\n"
                message += "`/settings digest on/off`\n"
                message += "`/settings digest_time 08:00`"
            else:
                message = "❌ You're not registered. Please use /start first."
        finally:
            db.close()
            
        await update.message.reply_text(message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in settings_command: {e}")
        await update.message.reply_text("❌ Sorry, something went wrong. Please try again later.")

async def digest_command(update: TelegramUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /digest command - enable/disable daily digest."""
    try:
        telegram_id = update.effective_user.id
        db = SessionLocal()
        try:
            user = get_user_by_telegram_id(db, telegram_id)
            if user:
                # Parse arguments
                if context.args:
                    action = context.args[0].lower()
                    if action in ["on", "enable"]:
                        user.receive_digest = True
                        db.commit()
                        message = "✅ Daily digest enabled! You'll receive a market summary every day."
                    elif action in ["off", "disable"]:
                        user.receive_digest = False
                        db.commit()
                        message = "🔕 Daily digest disabled."
                    elif action == "test":
                        # Send test digest with real data
                        from database import SessionLocal
                        from helix_telegram.digest import DigestService
                        test_db = SessionLocal()
                        try:
                            market_data = DigestService._fetch_real_market_data(test_db)
                            success = await DigestService.send_daily_digest(user, market_data)
                        finally:
                            test_db.close()
                        if success:
                            message = "✅ Test digest sent!"
                        else:
                            message = "❌ Failed to send test digest."
                    else:
                        message = "❌ Invalid action. Use: `/digest on`, `/digest off`, or `/digest test`"
                else:
                    # Show current status
                    status = "✅ Enabled" if user.receive_digest else "❌ Disabled"
                    digest_time = user.digest_time or "09:00"
                    timezone = user.timezone or "UTC"
                    message = "🌅 *Daily Digest Settings*\n\n"
                    message += f"Status: {status}\n"
                    message += f"Time: `{digest_time} {timezone}`\n\n"
                    message += "Commands:\n"
                    message += "`/digest on` - Enable daily digest\n"
                    message += "`/digest off` - Disable daily digest\n"
                    message += "`/digest test` - Send test digest"
            else:
                message = "❌ You're not registered. Please use /start first."
        finally:
            db.close()
            
        await update.message.reply_text(message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in digest_command: {e}")
        await update.message.reply_text("❌ Sorry, something went wrong. Please try again later.")

async def alerts_command(update: TelegramUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /alerts command - show recent alerts."""
    try:
        # This would fetch recent alerts from the database
        message = "📊 *Recent Alerts*\n\n"
        message += "No recent alerts to display.\n\n"
        message += "_This feature will show your recent alerts when implemented._"
        await update.message.reply_text(message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in alerts_command: {e}")
        await update.message.reply_text("❌ Sorry, something went wrong. Please try again later.")

async def echo_message(update: TelegramUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle regular text messages."""
    await update.message.reply_text("I understand commands only. Please use /help to see available commands.")

async def post_init(application: Application) -> None:
    """Set bot commands when the bot starts."""
    await application.bot.set_my_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help"),
        BotCommand("subscribe", "Subscribe to alerts"),
        BotCommand("unsubscribe", "Unsubscribe from alerts"),
        BotCommand("status", "Check subscription status"),
        BotCommand("settings", "Customize alert preferences"),
        BotCommand("digest", "Manage daily digest"),
        BotCommand("alerts", "Show recent alerts"),
    ])
    logger.info("Bot commands set")

def create_bot_application() -> Optional[Application]:
    """Create and configure the Telegram bot application."""
    if not BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set. Telegram bot will be disabled.")
        return None
        
    try:
        # Create the Application
        application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

        # Add command handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("subscribe", subscribe_command))
        application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("settings", settings_command))
        application.add_handler(CommandHandler("digest", digest_command))
        application.add_handler(CommandHandler("alerts", alerts_command))
        application.add_handler(CommandHandler("signal", rate_limited_signal_command))
        application.add_handler(CommandHandler("brief", rate_limited_brief_command))
        application.add_handler(CommandHandler("price", rate_limited_price_command))
        application.add_handler(CommandHandler("refer", rate_limited_refer_command))
        
        # Add message handler for regular text
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message))

        return application
    except Exception as e:
        logger.error(f"Error creating bot application: {e}")
        return None

# Rate-limited command wrappers
async def rate_limited_signal_command(update: TelegramUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rate-limited wrapper for /signal command."""
    if await telegram_middleware.check_rate_limit(update, context):
        await signal_command(update, context)

async def rate_limited_brief_command(update: TelegramUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rate-limited wrapper for /brief command."""
    if await telegram_middleware.check_rate_limit(update, context):
        await brief_command(update, context)

async def rate_limited_price_command(update: TelegramUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rate-limited wrapper for /price command."""
    if await telegram_middleware.check_rate_limit(update, context):
        await price_command(update, context)

async def rate_limited_refer_command(update: TelegramUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rate-limited wrapper for /refer command."""
    if await telegram_middleware.check_rate_limit(update, context):
        await refer_command(update, context)

async def send_alert_to_user(telegram_id: int, alert_message: str, alert_type: str = "info") -> bool:
    """Send an alert message to a specific user."""
    if not BOT_TOKEN:
        return False
        
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        bot = application.bot
        
        # Send the message
        await bot.send_message(chat_id=telegram_id, text=alert_message, parse_mode="Markdown")
        return True
    except Exception as e:
        logger.error(f"Error sending alert to user {telegram_id}: {e}")
        return False

async def send_alert_to_channel(channel_name: str, alert_message: str) -> bool:
    """Send an alert message to the Telegram channel."""
    if not BOT_TOKEN:
        return False
        
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        bot = application.bot
        
        # Send the message to channel
        await bot.send_message(chat_id=channel_name, text=alert_message, parse_mode="Markdown")
        return True
    except Exception as e:
        logger.error(f"Error sending alert to channel {channel_name}: {e}")
        return False