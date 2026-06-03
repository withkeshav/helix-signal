"""Database models package."""

from .base import Base
from .assets import AssetChainSnapshot, AssetTrendSnapshot, ChainTrendSnapshot
from .quality import SourceStatus, AssetFreshness
from .content import OsintArticle, SignalEvent
from .forecasting import ForecastRun, ForecastPoint
from .analytics import SourceUsage, AiUsage
from .security import User, SettingsAuditLog
from .telegram import TelegramUser, TelegramReviewItem, TelegramRateLimit

# Import Telegram user management functions
from .telegram import (
    get_user_by_telegram_id,
    get_user_by_id,
    get_all_users,
    get_subscribed_users,
    create_user,
    update_user_subscription,
    delete_user,
    update_user,
)

__all__ = [
    "Base",
    "AssetChainSnapshot",
    "AssetTrendSnapshot", 
    "ChainTrendSnapshot",
    "SourceStatus",
    "AssetFreshness",
    "OsintArticle",
    "SignalEvent",
    "ForecastRun",
    "ForecastPoint",
    "SourceUsage",
    "AiUsage",
    "User",
    "SettingsAuditLog",
    "TelegramUser",
    "TelegramReviewItem",
    "TelegramRateLimit",
    "get_user_by_telegram_id",
    "get_user_by_id",
    "get_all_users",
    "get_subscribed_users",
    "create_user",
    "update_user_subscription",
    "delete_user",
    "update_user",
]