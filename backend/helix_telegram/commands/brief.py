"""Telegram bot command: /brief - Returns a market brief (top signals, recent alerts, sentiment summary)."""

import logging
from datetime import datetime
from typing import Dict, Any

from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import desc

from database import SessionLocal, SignalEvent, OsintArticle
from signal_engine.core import load_enabled_assets
from services.dashboard import build_dashboard_response
from helix_telegram.templates import TelegramTemplates

logger = logging.getLogger(__name__)

async def brief_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /brief command - returns a market brief (top signals, recent alerts, sentiment summary)."""
    try:
        # Get real data
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            
            # Get top 3 assets by risk score
            top_assets = []
            enabled_assets = load_enabled_assets()
            for asset_cfg in enabled_assets:
                sym = str(asset_cfg["symbol"]).upper()
                try:
                    dash = build_dashboard_response(db, sym)
                    top_assets.append({
                        "symbol": sym,
                        "score": dash.asset_signal.score,
                        "band": dash.asset_signal.band,
                        "price": dash.depeg_index.current_price,
                        "depeg_pct": dash.depeg_index.deviation_pct
                    })
                except Exception:
                    logger.warning(f"Could not build dashboard for asset {sym}", exc_info=True)
            
            # Sort by score descending
            top_assets.sort(key=lambda x: x["score"], reverse=True)
            
            # Get recent signal events (last 24 hours)
            twenty_four_hours_ago = now.replace(hour=0, minute=0, second=0, microsecond=0)
            recent_events = (
                db.query(SignalEvent)
                .filter(SignalEvent.timestamp >= twenty_four_hours_ago)
                .order_by(desc(SignalEvent.severity), desc(SignalEvent.timestamp))
                .limit(5)
                .all()
            )
            
            # Get sentiment summary (compute from recent articles)
            sentiment = None
            try:
                # Get articles from last 24 hours
                twenty_four_hours_ago = now - timedelta(hours=24)
                recent_articles = (
                    db.query(OsintArticle)
                    .filter(OsintArticle.published_at >= twenty_four_hours_ago)
                    .filter(OsintArticle.sentiment_score.isnot(None))
                    .all()
                )
                
                if recent_articles:
                    # Calculate average sentiment
                    scores = [a.sentiment_score for a in recent_articles if a.sentiment_score is not None]
                    if scores:
                        avg_score = sum(scores) / len(scores)
                        sentiment_label = "positive" if avg_score > 0.1 else "neutral" if avg_score >= -0.1 else "negative"
                        sentiment = {
                            "overall_sentiment": sentiment_label,
                            "sentiment_score": avg_score,
                            "articles_analyzed": len(recent_articles)
                        }
            except Exception:
                sentiment = None

            # Format response
            message = "🌅 *Helix Signal Market Brief*\n"
            message += f"──────────────────\n"
            message += f"📅 {now.strftime('%Y-%m-%d %H:%M UTC')}\n\n"

            # Top assets section
            message += "📊 *Top Risk Assets*\n"
            for i, asset in enumerate(top_assets[:3]):
                depeg_str = ""
                if asset["depeg_pct"] is not None:
                    depeg_str = f" ({'+' if asset['depeg_pct'] >= 0 else ''}{asset['depeg_pct']:.4f}%)"
                message += f"{i+1}. `{asset['symbol']}` — {asset['score']}/100 ({asset['band']}) — ${asset['price']:.6f}{depeg_str}\n"
            message += "\n"

            # Recent alerts section
            message += "🔔 *Recent Alerts (24h)*\n"
            if recent_events:
                for event in recent_events[:3]:  # Top 3 events
                    # Truncate long titles
                    title = event.title[:50] + "..." if len(event.title) > 50 else event.title
                    message += f"• *{event.severity.upper()}*: {title}\n"
            else:
                message += "• No recent alerts\n"
            message += "\n"

            # Sentiment section
            message += "📰 *Market Sentiment*\n"
            if sentiment and "overall_sentiment" in sentiment:
                sent = sentiment["overall_sentiment"]
                score = sentiment.get("sentiment_score", 0)
                score_emoji = "🟢" if score > 0.1 else "🟡" if score >= -0.1 else "🔴"
                message += f"{score_emoji} {sent.title()}"
                if "articles_analyzed" in sentiment:
                    message += f" (from {sentiment['articles_analyzed']} articles)"
                message += "\n"
            else:
                message += "• Sentiment data unavailable\n"

            message += "\n🔗 [View Full Dashboard](https://helix.withkeshav.com/)"

            await update.message.reply_text(message, parse_mode="Markdown", disable_web_page_preview=True)
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error in /brief command: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Error retrieving market brief. Please try again later.",
            parse_mode="Markdown"
        )