"""Telegram message templates for Helix Signal."""

from typing import Dict, Any
from datetime import datetime

class TelegramTemplates:
    """Templates for different types of Telegram messages."""
    
    @staticmethod
    def format_signal_event(event_data: Dict[str, Any]) -> str:
        """Format a signal event for Telegram."""
        try:
            # Extract key information
            asset = event_data.get("asset_symbol", "Unknown")
            event_type = event_data.get("event_type", "Event")
            severity = event_data.get("severity", "info").upper()
            title = event_data.get("title", f"{event_type} Alert")
            summary = event_data.get("summary", "")
            chain = event_data.get("chain_key", "")
            
            # Severity mapping
            severity_config = {
                "critical": ("🔴", "CRITICAL"),
                "high": ("🟠", "HIGH"),
                "medium": ("🟡", "MEDIUM"),
                "low": ("🟢", "LOW"),
                "info": ("ℹ️", "INFO")
            }
            emoji, severity_label = severity_config.get(severity.lower(), ("ℹ️", severity))
            
            # Build message
            message = f"{emoji} *{title}*\n"
            message += "──────────────────\n"
            message += f"📦 *Asset:* `{asset}`\n"
            message += f"📈 *Severity:* `{severity_label}`\n"
            
            if chain:
                message += f"📍 *Chain:* `{chain}`\n"
            
            message += "──────────────────\n"
            
            if summary:
                # Truncate if too long
                if len(summary) > 600:
                    summary = summary[:600] + "..."
                message += f"{summary}\n\n"
            
            # Add timestamp if available
            if "timestamp" in event_data:
                try:
                    ts = event_data["timestamp"]
                    if isinstance(ts, str):
                        # Parse string timestamp
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        formatted_time = dt.strftime("%Y-%m-%d %H:%M UTC")
                    else:
                        formatted_time = ts.strftime("%Y-%m-%d %H:%M UTC")
                    message += f"⏱️ *Time:* `{formatted_time}`\n"
                except Exception:
                    message += f"⏱️ *Time:* `{event_data['timestamp']}`\n"
            
            # Add link to dashboard
            message += "🔗 *View Details:* [Dashboard](https://helix.withkeshav.com/)\n"
            
            return message
        except Exception as e:
            # Fallback template
            return "🔔 *New Alert*\n\nAn important event has been detected. Check the dashboard for details."
    
    @staticmethod
    def format_anomaly_alert(anomaly_data: Dict[str, Any]) -> str:
        """Format an anomaly detection alert."""
        try:
            asset = anomaly_data.get("asset", "Unknown")
            metric = anomaly_data.get("metric", "Unknown")
            value = anomaly_data.get("value", "N/A")
            threshold = anomaly_data.get("threshold", "N/A")
            zscore = anomaly_data.get("zscore", "")
            
            message = "🔍 *Anomaly Detected*\n"
            message += "──────────────────\n"
            message += f"📦 *Asset:* `{asset}`\n"
            message += f"📊 *Metric:* `{metric}`\n"
            message += f"🔢 *Value:* `{value}`\n"
            message += f"⚖️ *Threshold:* `{threshold}`\n"
            
            if zscore:
                message += f"📊 *Z-Score:* `{zscore}`\n"
            
            message += "──────────────────\n"
            message += "⚠️ An unusual pattern has been detected. Please review the dashboard for more information.\n\n"
            
            if "timestamp" in anomaly_data:
                message += f"⏱️ *Time:* `{anomaly_data['timestamp']}`\n"
            
            message += "🔗 *View Details:* [Dashboard](https://helix.withkeshav.com/)\n"
            
            return message
        except Exception as e:
            return "🔍 *Anomaly Detected*\n\nUnusual activity detected. Check dashboard for details."
    
    @staticmethod
    def format_osint_article(article_data: Dict[str, Any]) -> str:
        """Format an OSINT article for Telegram."""
        try:
            title = article_data.get("title", "News Article")
            source = article_data.get("source", "Unknown")
            summary = article_data.get("summary", "")
            sentiment = article_data.get("sentiment_label", "Neutral")
            url = article_data.get("url", "")
            
            # Sentiment emoji
            sentiment_emoji = {
                "positive": "🟢",
                "negative": "🔴",
                "neutral": "⚪"
            }.get(sentiment.lower(), "⚪")
            
            message = f"📰 *{title}*\n"
            message += "──────────────────\n"
            message += f"🗞️ *Source:* `{source}`\n"
            message += f"{sentiment_emoji} *Sentiment:* `{sentiment.title()}`\n"
            message += "──────────────────\n"
            
            if summary:
                if len(summary) > 600:
                    summary = summary[:600] + "..."
                message += f"{summary}\n\n"
            
            if url:
                message += f"🔗 [Read Full Article]({url})\n"
            else:
                message += "🔗 *View Details:* [Dashboard](https://helix.withkeshav.com/)\n"
            
            if "published_at" in article_data:
                message += f"⏱️ *Published:* `{article_data['published_at']}`\n"
            
            return message
        except Exception as e:
            return "📰 *News Update*\n\nNew article published. Check dashboard for details."
    
    @staticmethod
    def format_system_status(status_data: Dict[str, Any]) -> str:
        """Format system status update."""
        try:
            status = status_data.get("status", "unknown")
            db_status = status_data.get("db", True)
            sources_down = status_data.get("sources_down", 0)
            
            emoji = "✅" if status == "ok" else "❌"
            db_emoji = "✅" if db_status else "❌"
            
            message = f"{emoji} *System Status Update*\n"
            message += "──────────────────\n"
            message += f"⚙️ *Overall:* `{status.upper()}`\n"
            message += f"🗄️ *Database:* `{'OK' if db_status else 'ERROR'}`\n"
            
            if sources_down > 0:
                message += f"📡 *Sources Down:* `{sources_down}`\n"
            
            message += "──────────────────\n"
            message += "🔄 System status has been updated.\n\n"
            
            if "version" in status_data:
                message += f"🔢 *Version:* `{status_data['version']}`\n"
            
            return message
        except Exception as e:
            return "⚙️ *System Status*\n\nSystem status update available. Check dashboard for details."
    
    @staticmethod
    def format_forecast_update(forecast_data: Dict[str, Any]) -> str:
        """Format forecast update."""
        try:
            asset = forecast_data.get("asset", "Unknown")
            direction = forecast_data.get("direction", "stable")
            confidence = forecast_data.get("confidence", 0)
            
            # Direction emoji
            direction_emoji = {
                "increase": "📈",
                "decrease": "📉",
                "stable": "➡️"
            }.get(direction.lower(), "➡️")
            
            message = f"{direction_emoji} *Forecast Update*\n"
            message += "──────────────────\n"
            message += f"📦 *Asset:* `{asset}`\n"
            message += f"🧭 *Direction:* `{direction.title()}`\n"
            message += f"📊 *Confidence:* `{int(confidence * 100)}%`\n"
            message += "──────────────────\n"
            message += "🔮 Predictive analysis has detected a trend. Monitor for developments.\n\n"
            
            if "timestamp" in forecast_data:
                message += f"⏱️ *Time:* `{forecast_data['timestamp']}`\n"
            
            return message
        except Exception as e:
            return "🔮 *Forecast Update*\n\nNew forecast available. Check dashboard for details."

# Predefined message templates
WELCOME_MESSAGE = """
👋 *Welcome to Helix Signal Bot!*

I'll send you alerts about stablecoin risks, anomalies, and important events.

✅ *Commands:*
/start - Start the bot
/help - Show help
/subscribe - Subscribe to alerts
/unsubscribe - Unsubscribe from alerts
/status - Check your subscription status

You're automatically subscribed to receive alerts.
"""

HELP_MESSAGE = """
🤖 *Helix Signal Bot Commands*

/start - Start the bot and subscribe to alerts
/help - Show this help message
/subscribe - Subscribe to receive alerts
/unsubscribe - Unsubscribe from alerts
/status - Check your subscription status
/alerts - List recent alerts

📝 *What this bot does:*
This bot sends you alerts about stablecoin risks, anomalies, and important events from Helix Signal.

🔔 You're currently subscribed to receive alerts.
"""

SUBSCRIBE_SUCCESS = "✅ You are now subscribed to receive alerts!"

UNSUBSCRIBE_SUCCESS = "🔕 You have been unsubscribed from alerts."

STATUS_SUBSCRIBED = "✅ *Your Status*\n\nStatus: `Subscribed`\n\nYou will receive alerts."

STATUS_UNSUBSCRIBED = "🔕 *Your Status*\n\nStatus: `Unsubscribed`\n\nYou will not receive alerts."

ALERT_HEADER = "🔔 *Helix Signal Alert*"

NO_ALERTS_MESSAGE = "📊 *Recent Alerts*\n\nNo recent alerts to display."