"""Settings manager — reads/writes feature flags from DB, env, or defaults."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, Session

from database import Base

# Import settings registry
from .settings_registry import _DEFAULT_SETTINGS


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


def get_setting(key: str, db: Session | None = None) -> Any:
    """Return a setting's value, falling back to env var then default."""
    meta = _DEFAULT_SETTINGS.get(key)
    if not meta:
        return None

    if meta.get("type") == "secret":
        if db:
            row = db.query(Setting).filter(Setting.key == key).first()
            if row and row.value:
                return row.value
        env_key = meta.get("key_env", "")
        if env_key:
            val = os.getenv(env_key, "").strip()
            if val:
                return val
        return meta.get("default", "")

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


def set_setting(key: str, value: Any, db: Session, user: Any = None, ip_address: str = None, user_agent: str = None, flush: bool = False) -> None:
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
    
    # Get the old value for audit logging
    old_row = db.query(Setting).filter(Setting.key == key).first()
    old_value = old_row.value if old_row else None
    
    # Update or create the setting
    if old_row:
        old_row.value = str(value)
    else:
        db.add(Setting(key=key, value=str(value)))
    
    if not flush:
        db.commit()
    
    # Log the change to the audit log
    try:
        from services.settings_audit import log_settings_change
        log_settings_change(
            db=db,
            setting_key=key,
            old_value=old_value,
            new_value=str(value),
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except Exception:
        # Don't fail the settings update if audit logging fails
        pass


def mask_secret(value: str) -> str:
    """Return a display-safe value for secret-type settings.

    Never returns the actual secret — only indicates whether it is configured.
    """
    return "configured" if value else "not_set"


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
                if meta.get("type") == "secret":
                    typed = env_val
                elif meta.get("type") == "str":
                    typed = env_val
                else:
                    typed = env_val.lower() in ("1", "true", "yes")
            else:
                typed = meta.get("default")
        
        # Get current usage for settings that track usage
        current_usage = get_current_usage(key, db)
        
        out_item = {
            "key": key,
            "label": meta.get("label"),
            "type": meta.get("type", "bool"),
            "value": mask_secret(typed) if meta.get("type") == "secret" else typed,
            "default": meta.get("default"),
            "always_active": meta.get("always_active", False),
            "key_env": meta.get("key_env"),
            "min": meta.get("min"),
            "max": meta.get("max"),
            "group": meta.get("group", "General"),
            "description": meta.get("description", ""),
            "requires_restart": meta.get("requires_restart", False),
            "affects_rate_limits": meta.get("affects_rate_limits", False),
            "warning_threshold": meta.get("warning_threshold"),
            "rate_limit_rpm": meta.get("rate_limit_rpm"),
            "provider_metadata": meta.get("provider_metadata"),
            "current_usage": current_usage,
        }
        out.append(out_item)
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


PLAYBOOKS: dict[str, dict[str, Any]] = {
    "max_free": {
        "label": "Maximum Free Tier",
        "description": "Zero API cost — uses only free providers, minimal AI features",
        "settings": {
            "ai_mode": "ai_lite",
            "ai_daily_token_budget": 10000,
            "ai_provider_priority": '["openrouter_free", "ollama_cloud"]',
            "ai_cache_ttl_seconds": 7200,
            "ai_cache_semantic_enabled": True,
            "ai_cache_max_entries": 500,
            "ai_web_search": False,
            "feature_ai_summary": True,
        },
    },
    "balanced": {
        "label": "Balanced",
        "description": "Good quality with reasonable cost — uses cheap providers with caching",
        "settings": {
            "ai_mode": "ai_full",
            "ai_daily_token_budget": 50000,
            "ai_provider_priority": '["groq", "ollama_cloud", "openrouter_free", "openrouter_paid"]',
            "ai_cache_ttl_seconds": 3600,
            "ai_cache_semantic_enabled": True,
            "ai_cache_max_entries": 1000,
            "ai_web_search": True,
            "ai_web_search_max_results": 3,
            "feature_ai_summary": True,
        },
    },
    "quality": {
        "label": "Maximum Quality",
        "description": "Best results — uses paid providers, full AI features, web search",
        "settings": {
            "ai_mode": "ai_full",
            "ai_daily_token_budget": 200000,
            "ai_provider_priority": '["openrouter_paid", "groq", "ollama_cloud"]',
            "ai_cache_ttl_seconds": 1800,
            "ai_cache_semantic_enabled": False,
            "ai_cache_max_entries": 2000,
            "ai_web_search": True,
            "ai_web_search_max_results": 5,
            "feature_ai_summary": True,
        },
    },
}


def get_playbooks() -> dict[str, dict[str, Any]]:
    """Return all playbook definitions (metadata only, no current values)."""
    return {
        name: {
            "name": name,
            "label": pb["label"],
            "description": pb["description"],
            "settings": dict(pb["settings"]),
        }
        for name, pb in PLAYBOOKS.items()
    }


def apply_playbook(name: str, db: Session) -> list[dict[str, Any]]:
    pb = PLAYBOOKS.get(name)
    if pb is None:
        raise ValueError(f"Unknown playbook: {name}")
    changes: list[dict[str, Any]] = []
    for key, value in pb["settings"].items():
        set_setting(key, value, db)
        changes.append({"key": key, "value": value})
    return changes


def get_current_usage(key: str, db: Session) -> Any:
    """Get current usage for a setting that tracks usage."""
    try:
        from services.ai_router import get_budget_status
        from services.source_usage import get_source_usage_summary
        
        if key == "ai_daily_token_budget":
            status = get_budget_status()
            return status.get("tokens_used_today", 0)
        elif key in ("provider_dexscreener", "provider_coingecko", "provider_defillama", 
                     "provider_coinmarketcap", "provider_moralis", "provider_thegraph", "provider_flipside"):
            # Get source usage for data providers
            source_name = key.replace("provider_", "")
            usage_summary = get_source_usage_summary(db)
            source_usage = usage_summary.get("sources", {}).get(source_name, {})
            return source_usage.get("call_count", 0)
    except Exception:
        # If there's any error (e.g., database not initialized), return None
        pass
    
    return None



