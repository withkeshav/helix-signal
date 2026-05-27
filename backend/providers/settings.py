"""Settings manager — reads/writes feature flags from DB, env, or defaults."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, Session

from database import Base, engine, SessionLocal

_DEFAULT_SETTINGS: dict[str, dict[str, Any]] = {
    "provider_defillama": {"label": "DefiLlama", "type": "bool", "default": True, "always_active": True},
    "provider_dexscreener": {"label": "DexScreener", "type": "bool", "default": True, "always_active": True},
    "provider_coingecko": {"label": "CoinGecko", "type": "bool", "default": True, "always_active": True},
    "provider_coinmarketcap": {"label": "CoinMarketCap", "type": "bool", "default": False, "key_env": "CMC_API_KEY"},
    "provider_moralis": {"label": "Moralis", "type": "bool", "default": False, "key_env": "MORALIS_API_KEY"},
    "feature_osint_feed": {"label": "OSINT Feed (RSS)", "type": "bool", "default": True},
    "feature_nlp_sentiment": {"label": "Sentiment NLP (FinBERT)", "type": "bool", "default": False, "key_env": "ENABLE_NLP"},
    "feature_ai_summary": {"label": "AI Summary", "type": "bool", "default": True},
    "refresh_core_seconds": {"label": "Core data refresh interval", "type": "int", "default": 300, "min": 60, "max": 3600},
    "refresh_osint_minutes": {"label": "OSINT feed refresh interval", "type": "int", "default": 60, "min": 15, "max": 1440},
    "ai_mode": {"label": "AI Mode", "type": "str", "default": "ai_off", "key_env": "AI_MODE"},
    "ai_daily_token_budget": {"label": "AI Daily Token Budget", "type": "int", "default": 50000, "min": 1000, "max": 500000},
    "ai_cache_ttl_seconds": {"label": "AI Cache TTL (seconds)", "type": "int", "default": 3600, "min": 60, "max": 86400},
    "ai_web_search": {"label": "AI Web Search", "type": "bool", "default": False, "key_env": "AI_WEB_SEARCH"},
    "ai_web_search_max_results": {"label": "AI Web Search Max Results", "type": "int", "default": 3, "min": 1, "max": 10, "key_env": "AI_WEB_SEARCH_MAX_RESULTS"},
    "enable_anomaly_detection": {"label": "Anomaly Detection", "type": "bool", "default": False, "key_env": "ENABLE_ANOMALY_DETECTION"},
}


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


def get_setting(key: str, db: Session | None = None) -> Any:
    """Return a setting's value, falling back to env var then default."""
    meta = _DEFAULT_SETTINGS.get(key)
    if not meta:
        return None

    env_val = os.getenv(meta.get("key_env", ""), "").strip() if meta.get("key_env") else None
    if env_val and env_val.lower() in ("1", "true", "yes"):
        return True
    if env_val and env_val.lower() in ("0", "false", "no"):
        return False
    if env_val is not None and env_val:
        return env_val

    if db:
        row = db.query(Setting).filter(Setting.key == key).first()
        if row:
            return _coerce(row.value, meta.get("type", "bool"))

    return meta.get("default")


def set_setting(key: str, value: Any, db: Session) -> None:
    meta = _DEFAULT_SETTINGS.get(key)
    if not meta:
        raise ValueError(f"Unknown setting: {key}")
    if meta.get("always_active"):
        raise ValueError(f"Setting '{key}' cannot be changed")
    if meta.get("type") == "int":
        try:
            int_val = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Setting '{key}' requires an integer value") from exc
        min_val = meta.get("min")
        max_val = meta.get("max")
        if min_val is not None and int_val < min_val:
            raise ValueError(f"Setting '{key}' must be >= {min_val}")
        if max_val is not None and int_val > max_val:
            raise ValueError(f"Setting '{key}' must be <= {max_val}")
        value = int_val
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = str(value)
    else:
        db.add(Setting(key=key, value=str(value)))
    db.commit()


def get_all_settings(db: Session) -> list[dict[str, Any]]:
    rows = {r.key: r.value for r in db.query(Setting).all()}
    out: list[dict[str, Any]] = []
    for key, meta in _DEFAULT_SETTINGS.items():
        val = rows.get(key)
        if val is not None:
            typed = _coerce(val, meta.get("type", "bool"))
        else:
            env_val = os.getenv(meta.get("key_env", ""), "").strip() if meta.get("key_env") else None
            if env_val is not None and env_val:
                typed = env_val if meta.get("type") == "str" else env_val.lower() in ("1", "true", "yes")
            else:
                typed = meta.get("default")
        out.append({
            "key": key,
            "label": meta.get("label"),
            "type": meta.get("type", "bool"),
            "value": typed,
            "default": meta.get("default"),
            "always_active": meta.get("always_active", False),
            "key_env": meta.get("key_env"),
            "min": meta.get("min"),
            "max": meta.get("max"),
        })
    return out


def _coerce(val: str, typ: str) -> Any:
    if typ == "bool":
        return val.lower() in ("1", "true", "yes")
    if typ == "int":
        try:
            return int(val)
        except (ValueError, TypeError):
            return None
    return val



