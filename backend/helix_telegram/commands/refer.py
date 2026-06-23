"""Telegram bot command: /refer - Returns system health + reference links."""

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from database import SessionLocal, SourceStatus
from services.health import build_health_payload
from helix_telegram.templates import TelegramTemplates

logger = logging.getLogger(__name__)

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /refer command - returns system health + reference links."""
    try:
        # Get real data
        db = SessionLocal()
        try:
            # Get system health
            health_data = build_health_payload(db, scheduler=None)
            
            # Get source statuses
            sources = db.query(SourceStatus).order_by(SourceStatus.id.asc()).all()
            
            # Format response
            now = datetime.now(timezone.utc)
            message = "🔗 *Helix Signal System Reference*\n"
            message += "──────────────────\n"
            message += f"🕒 Time: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"

            # System health section
            message += "⚙️ *System Health*\n"
            overall_status = "🟢" if health_data["overall"] == "healthy" else "🟡" if health_data["overall"] == "degraded" else "🔴"
            message += f"{overall_status} Status: {health_data['overall'].title()}\n"
            
            if "components" in health_data:
                for component, status in health_data["components"].items():
                    status_emoji = "🟢" if status == "ok" else "🔴" if status == "error" else "🟡"
                    message += f"   • {component}: {status_emoji} {status.title()}\n"
            message += "\n"

            # Source status section
            message += "📡 *Data Source Status*\n"
            for source in sources:
                status_emoji = "🟢" if source.status == "ok" else "🔴" if source.status == "error" else "🟡"
                status_text = source.status.title()
                if source.last_error:
                    status_text += f" ({source.last_error[:30]}...)" if len(source.last_error) > 30 else f" ({source.last_error})"
                message += f"• {source.source_name}: {status_emoji} {status_text}\n"
                
                # Add last successful fetch if available
                if source.last_successful_fetch:
                    last_fetch = source.last_successful_fetch.strftime('%H:%M')
                    message += f"   └ Last update: {last_fetch} UTC\n"
            message += "\n"

            # Reference links section
            message += "📚 *Reference Links*\n"
            message += "• [Dashboard](https://helix.withkeshav.com/) — Main monitoring interface\n"
            message += "• [GitHub](https://github.com/withkeshav/helix-signal) — Source code & docs\n"
            message += "• [API Docs](https://helix.withkeshav.com/docs/api) — REST API reference\n"
            message += "• [Architecture](https://helix.withkeshav.com/docs/architecture) — System design\n"
            message += "• [Settings Guide](https://helix.withkeshav.com/docs/settings) — Admin setup\n\n"

            # Version info
            from services.retention import HELIX_VERSION
            message += f"📦 Version: `{HELIX_VERSION}`\n"

            await update.message.reply_text(message, parse_mode="Markdown", disable_web_page_preview=True)
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error in /refer command: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Error retrieving system reference. Please try again later.",
            parse_mode="Markdown"
        )