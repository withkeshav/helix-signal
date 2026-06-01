"""Settings manager — reads/writes feature flags from DB, env, or defaults."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, Session

from database import Base, engine, SessionLocal

_DEFAULT_SETTINGS: dict[str, dict[str, Any]] = {
    "provider_defillama": {
        "label": "DefiLlama",
        "type": "bool",
        "default": True,
        "always_active": True,
        "group": "Data Providers",
        "description": "Enable DefiLlama API for stablecoin metrics",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
    "provider_dexscreener": {
        "label": "DexScreener",
        "type": "bool",
        "default": True,
        "always_active": True,
        "group": "Data Providers",
        "description": "Enable DexScreener API for DEX pool data",
        "requires_restart": False,
        "affects_rate_limits": True,
        "rate_limit_rpm": 300,
        "warning_threshold": 0.8,
    },
    "provider_coingecko": {
        "label": "CoinGecko",
        "type": "bool",
        "default": True,
        "always_active": True,
        "group": "Data Providers",
        "description": "Enable CoinGecko API for price data",
        "requires_restart": False,
        "affects_rate_limits": True,
        "rate_limit_rpm": 50,
        "warning_threshold": 0.8,
    },
    "provider_coinmarketcap": {
        "label": "CoinMarketCap",
        "type": "bool",
        "default": False,
        "key_env": "CMC_API_KEY",
        "group": "Data Providers",
        "description": "Enable CoinMarketCap API (requires API key)",
        "requires_restart": False,
        "affects_rate_limits": True,
    },
    "provider_moralis": {
        "label": "Moralis",
        "type": "bool",
        "default": False,
        "key_env": "MORALIS_API_KEY",
        "group": "Data Providers",
        "description": "Enable Moralis API for token analytics (requires API key)",
        "requires_restart": False,
        "affects_rate_limits": True,
    },
    "feature_osint_feed": {
        "label": "OSINT Feed (RSS)",
        "type": "bool",
        "default": True,
        "group": "Features",
        "description": "Enable OSINT feed processing",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
    "feature_nlp_sentiment": {
        "label": "Sentiment NLP (FinBERT)",
        "type": "bool",
        "default": False,
        "key_env": "ENABLE_NLP",
        "group": "Features",
        "description": "Enable FinBERT sentiment analysis",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
    "feature_ai_summary": {
        "label": "AI Summary",
        "type": "bool",
        "default": True,
        "group": "Features",
        "description": "Enable AI-powered summaries",
        "requires_restart": False,
        "affects_rate_limits": True,
    },
    "refresh_core_seconds": {
        "label": "Core data refresh interval",
        "type": "int",
        "default": 300,
        "min": 60,
        "max": 3600,
        "group": "Performance",
        "description": "Interval between core data refreshes (seconds)",
        "requires_restart": True,
        "affects_rate_limits": False,
    },
    "refresh_osint_minutes": {
        "label": "OSINT feed refresh interval",
        "type": "int",
        "default": 60,
        "min": 15,
        "max": 1440,
        "group": "Performance",
        "description": "Interval between OSINT feed refreshes (minutes)",
        "requires_restart": True,
        "affects_rate_limits": False,
    },
    "ai_mode": {
        "label": "AI Mode",
        "type": "str",
        "default": "ai_off",
        "key_env": "AI_MODE",
        "group": "AI & Intelligence",
        "description": "AI mode: ai_off, ai_lite, or ai_full",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
    "ai_daily_token_budget": {
        "label": "AI Daily Token Budget",
        "type": "int",
        "default": 50000,
        "min": 1000,
        "max": 500000,
        "group": "AI & Intelligence",
        "description": "Maximum tokens to consume per day across all AI providers",
        "requires_restart": False,
        "affects_rate_limits": True,
        "warning_threshold": 0.8,
    },
    "ai_provider_priority": {
        "label": "AI Provider Priority",
        "type": "str",
        "default": '["groq","ollama_cloud","openrouter_free","openrouter_paid"]',
        "group": "AI & Intelligence",
        "description": "Ordered priority list of AI providers (JSON array). Tiers: cache → groq → ollama_cloud → openrouter_free → openrouter_paid",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
    "ai_cache_ttl_seconds": {
        "label": "AI Cache TTL (seconds)",
        "type": "int",
        "default": 3600,
        "min": 60,
        "max": 86400,
        "key_env": "AI_CACHE_TTL_SECONDS",
        "group": "AI & Intelligence",
        "description": "Time to live for AI response cache",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
    "ai_cache_semantic_enabled": {
        "label": "AI Semantic Cache",
        "type": "bool",
        "default": False,
        "key_env": "AI_CACHE_SEMANTIC_ENABLED",
        "group": "AI & Intelligence",
        "description": "Enable semantic caching — matches similar prompts via text similarity (character trigram Jaccard)",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
    "ai_cache_semantic_threshold": {
        "label": "AI Semantic Cache Threshold",
        "type": "str",
        "default": "0.90",
        "key_env": "AI_CACHE_SEMANTIC_THRESHOLD",
        "group": "AI & Intelligence",
        "description": "Similarity threshold (0.5-1.0) for semantic cache matches",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
    "ai_cache_max_entries": {
        "label": "AI Cache Max Entries",
        "type": "int",
        "default": 1000,
        "min": 100,
        "max": 10000,
        "key_env": "AI_CACHE_MAX_ENTRIES",
        "group": "AI & Intelligence",
        "description": "Maximum number of entries in the in-memory AI response cache",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
    "ai_web_search": {
        "label": "AI Web Search",
        "type": "bool",
        "default": False,
        "key_env": "AI_WEB_SEARCH",
        "group": "AI & Intelligence",
        "description": "Enable web search for AI features",
        "requires_restart": False,
        "affects_rate_limits": True,
    },
    "ai_web_search_max_results": {
        "label": "AI Web Search Max Results",
        "type": "int",
        "default": 3,
        "min": 1,
        "max": 10,
        "key_env": "AI_WEB_SEARCH_MAX_RESULTS",
        "group": "AI & Intelligence",
        "description": "Maximum number of web search results to include",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
    "enable_anomaly_detection": {
        "label": "Anomaly Detection",
        "type": "bool",
        "default": False,
        "key_env": "ENABLE_ANOMALY_DETECTION",
        "group": "Features",
        "description": "Enable anomaly detection algorithms",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
    "secret_cmc_api_key": {
        "label": "CoinMarketCap API Key",
        "type": "secret",
        "default": "",
        "key_env": "CMC_API_KEY",
        "group": "API Keys",
        "description": "API key for CoinMarketCap",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
    "secret_moralis_api_key": {
        "label": "Moralis API Key",
        "type": "secret",
        "default": "",
        "key_env": "MORALIS_API_KEY",
        "group": "API Keys",
        "description": "API key for Moralis",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
    "secret_ollama_api_key": {
        "label": "Ollama API Key",
        "type": "secret",
        "default": "",
        "key_env": "OLLAMA_API_KEY",
        "group": "API Keys",
        "description": "API key for Ollama Cloud",
        "requires_restart": False,
        "affects_rate_limits": False,
        "provider_metadata": {
            "name": "Ollama Cloud",
            "tier": "cloud",
            "models": ["ministral-3:8b-cloud", "qwen-2.5-7b-cloud"],
            "max_tokens": 4096,
            "cost_per_million_tokens": 0.15,
            "free_tier_calls": 0,
            "rate_limit_rpm": 60,
        },
    },
    "secret_openrouter_api_key": {
        "label": "OpenRouter API Key",
        "type": "secret",
        "default": "",
        "key_env": "OPENROUTER_API_KEY",
        "group": "API Keys",
        "description": "API key for OpenRouter",
        "requires_restart": False,
        "affects_rate_limits": False,
        "provider_metadata": {
            "name": "OpenRouter",
            "tier": "cloud",
            "models": ["openrouter/free", "openai/gpt-4o-mini"],
            "max_tokens": 4096,
            "cost_per_million_tokens": 0.6,
            "free_tier_calls": 1000,
            "rate_limit_rpm": 100,
        },
    },
    "secret_groq_api_key": {
        "label": "Groq API Key",
        "type": "secret",
        "default": "",
        "key_env": "GROQ_API_KEY",
        "group": "API Keys",
        "description": "API key for Groq",
        "requires_restart": False,
        "affects_rate_limits": False,
        "provider_metadata": {
            "name": "Groq",
            "tier": "cloud",
            "models": ["llama-3.1-8b-instant"],
            "max_tokens": 8192,
            "cost_per_million_tokens": 0.05,
            "free_tier_calls": 0,
            "rate_limit_rpm": 30,
        },
    },
    "secret_etherscan_api_key": {
        "label": "Etherscan API Key",
        "type": "secret",
        "default": "",
        "key_env": "ETHERSCAN_API_KEY",
        "group": "API Keys",
        "description": "API key for Etherscan",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
    "secret_fred_api_key": {
        "label": "FRED API Key",
        "type": "secret",
        "default": "",
        "key_env": "FRED_API_KEY",
        "group": "API Keys",
        "description": "API key for FRED (Federal Reserve Economic Data)",
        "requires_restart": False,
        "affects_rate_limits": False,
    },
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
            "value": bool(typed) if meta.get("type") == "secret" else typed,
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
                     "provider_coinmarketcap", "provider_moralis"):
            # Get source usage for data providers
            source_name = key.replace("provider_", "")
            usage_summary = get_source_usage_summary(db)
            source_usage = usage_summary.get("sources", {}).get(source_name, {})
            return source_usage.get("call_count", 0)
    except Exception:
        # If there's any error (e.g., database not initialized), return None
        pass
    
    return None



