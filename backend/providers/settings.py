"""Settings manager — reads/writes feature flags from DB, env, or defaults."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy import String, Text, select
from sqlalchemy.orm import Mapped, mapped_column, Session

from database import Base

log = logging.getLogger(__name__)

# Import settings registry
from .settings_registry import _DEFAULT_SETTINGS
from .settings_crypto import decrypt_secret, encrypt_secret, is_encrypted


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


def _read_raw_db_value(key: str, db: Session) -> str | None:
    row = db.execute(select(Setting).where(Setting.key == key)).scalars().first()
    if row and row.value is not None:
        return row.value
    return None


def _read_env_secret(meta: dict[str, Any]) -> str:
    env_key = meta.get("key_env", "")
    if env_key:
        return os.getenv(env_key, "").strip()
    return ""


def get_secret(key: str, db: Session | None = None) -> str:
    """Return decrypted secret for provider callables only — never log the result."""
    meta = _DEFAULT_SETTINGS.get(key)
    if not meta or meta.get("type") != "secret":
        return str(get_setting(key, db) or "")

    raw: str | None = None
    if db:
        raw = _read_raw_db_value(key, db)
    if not raw:
        raw = _read_env_secret(meta)
    if not raw:
        return str(meta.get("default", "") or "")

    plaintext = decrypt_secret(raw)
    if db and plaintext and not is_encrypted(raw):
        try:
            _persist_secret_value(key, plaintext, db, reencrypt_only=True)
        except Exception:
            log.warning("settings.lazy_encrypt_failed", extra={"key": key}, exc_info=True)
    return plaintext


def _persist_secret_value(
    key: str,
    plaintext: str,
    db: Session,
    *,
    reencrypt_only: bool = False,
) -> None:
    stored = encrypt_secret(plaintext)
    row = db.execute(select(Setting).where(Setting.key == key)).scalars().first()
    if row:
        if reencrypt_only and row.value == stored:
            return
        row.value = stored
    else:
        db.add(Setting(key=key, value=stored))
    db.commit()


def get_setting(key: str, db: Session | None = None) -> Any:
    """Return a setting's value, falling back to env var then default."""
    meta = _DEFAULT_SETTINGS.get(key)
    if not meta:
        return None

    if meta.get("type") == "secret":
        configured = bool(_secret_configured(key, db))
        if configured:
            return "configured"
        env_val = _read_env_secret(meta)
        if env_val:
            return "configured"
        default = meta.get("default", "")
        return mask_secret(default) if default else default

    # Non-secret path — DB first, env fallback, default last
    if db:
        row = db.execute(select(Setting).where(Setting.key == key)).scalars().first()
        if row and row.value is not None:
            return _coerce(row.value, meta.get("type", "bool"))

    env_key = meta.get("key_env")
    if env_key:
        env_val = os.getenv(env_key, "").strip()
        if env_val:
            if env_val.lower() in ("1", "true", "yes"):
                return True
            if env_val.lower() in ("0", "false", "no"):
                return False
            if meta.get("type") == "str":
                return env_val
            return _coerce(env_val, meta.get("type", "bool"))

    return meta.get("default")


def _secret_configured(key: str, db: Session | None) -> bool:
    meta = _DEFAULT_SETTINGS.get(key) or {}
    if db:
        raw = _read_raw_db_value(key, db)
        if raw:
            return True
    return bool(_read_env_secret(meta))


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
    if meta.get("type") in ("float", "number"):
        try:
            float_val = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Setting '{key}' requires a number") from exc
        min_val = meta.get("min")
        max_val = meta.get("max")
        if min_val is not None and float_val < min_val:
            raise ValueError(f"Setting '{key}' must be >= {min_val}")
        if max_val is not None and float_val > max_val:
            raise ValueError(f"Setting '{key}' must be <= {max_val}")
        value = float_val
    if meta.get("type") == "str" and "choices" in meta:
        if str(value) not in meta["choices"]:
            raise ValueError(f"Setting '{key}' must be one of: {', '.join(meta['choices'])}")

    stored_value = str(value)
    if meta.get("type") == "secret":
        stored_value = encrypt_secret(stored_value)

    # Get the old value for audit logging
    old_row = db.execute(select(Setting).where(Setting.key == key)).scalars().first()
    old_value = old_row.value if old_row else None

    # Update or create the setting
    if old_row:
        old_row.value = stored_value
    else:
        db.add(Setting(key=key, value=stored_value))

    if not flush:
        db.commit()

    # Log the change to the audit log
    try:
        from services.settings_audit import log_settings_change
        audit_old = old_value
        audit_new = stored_value
        if meta.get("type") == "secret":
            audit_old = "[REDACTED]" if old_value else None
            audit_new = "[REDACTED]"
        log_settings_change(
            db=db,
            setting_key=key,
            old_value=audit_old,
            new_value=audit_new,
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except Exception:
        log.warning("settings.audit_log_failed", exc_info=True)

    # Side-effects: presets expand to many keys
    if key == "retention_preset" and not flush:
        try:
            from providers.settings_presets import apply_retention_preset
            apply_retention_preset(str(value), db)
        except Exception:
            log.warning("settings.retention_preset_apply_failed", exc_info=True)
    if key == "anomaly_sensitivity" and not flush:
        try:
            from providers.settings_presets import apply_anomaly_sensitivity
            apply_anomaly_sensitivity(str(value), db)
        except Exception:
            log.warning("settings.anomaly_sensitivity_apply_failed", exc_info=True)


def mask_secret(value: str) -> str | None:
    """Return a display-safe value for secret-type settings.

    Never returns the actual secret — only indicates whether it is configured.
    """
    return "configured" if value else None


_MASKED_SENTINELS = frozenset({"", "configured", "********", "****", "[redacted]", "[REDACTED]"})


def is_secret_skip_value(value: Any) -> bool:
    """True when a submitted secret must NOT overwrite the stored value.

    Used by REST import, PUT /settings, and SQLAdmin so masked export
    round-trips never encrypt the sentinel string ``configured`` as a key.
    """
    if value is None:
        return True
    text = str(value).strip()
    if text.lower() in {s.lower() for s in _MASKED_SENTINELS}:
        return True
    # Common mask patterns: last-4 reveal style "••••abcd" / "****abcd"
    if text.startswith(("•", "*")) and len(text) <= 12:
        return True
    return False


def setting_is_secret(key: str) -> bool:
    meta = _DEFAULT_SETTINGS.get(key) or {}
    return meta.get("type") == "secret"


def get_all_settings(db: Session) -> list[dict[str, Any]]:
    rows = {r.key: r.value for r in db.execute(select(Setting)).scalars().all()}
    out: list[dict[str, Any]] = []
    for key, meta in _DEFAULT_SETTINGS.items():
        val = rows.get(key)
        if val is not None:
            if meta.get("type") == "secret":
                typed = "configured" if val else None
            else:
                typed = _coerce(val, meta.get("type", "bool"))
        else:
            env_val = os.getenv(meta.get("key_env", ""), "").strip() if meta.get("key_env") else None
            if env_val is not None and env_val:
                if meta.get("type") == "secret":
                    typed = "configured"
                elif meta.get("type") == "str":
                    typed = env_val
                else:
                    typed = env_val.lower() in ("1", "true", "yes")
            else:
                typed = meta.get("default")

        # Get current usage for settings that track usage
        current_usage = get_current_usage(key, db)

        api_type = meta.get("type", "bool")
        choices = meta.get("choices")
        # Control Room templates branch on type==="enum" + options; registry stores
        # constrained strings as type "str" with choices — expose both shapes.
        options = list(choices) if choices else None
        if options and api_type == "str":
            api_type = "enum"

        out_item = {
            "key": key,
            "label": meta.get("label"),
            "type": api_type,
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
        if options is not None:
            out_item["choices"] = options
            out_item["options"] = options
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
    if typ in ("float", "number"):
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
    return val


PLAYBOOKS: dict[str, dict[str, Any]] = {
    "max_free": {
        "label": "Maximum Free Tier",
        "description": "Zero API cost — uses Ollama Cloud with aggressive caching",
        "settings": {
            "ai_mode": "ai_lite",
            "ai_model_risk_explain": "ollama_cloud:ministral-3:8b-cloud",
            "ai_model_market_narrative": "ollama_cloud:ministral-3:8b-cloud",
            "ai_model_insight_summary": "ollama_cloud:ministral-3:8b-cloud",
            "ai_fallback_provider": "openrouter",
            "ai_fallback_model": "openrouter/free",
            "ai_cache_ttl_seconds": 7200,
            "ai_cache_semantic_enabled": True,
            "ai_cache_max_entries": 500,
            "feature_ai_summary": True,
        },
    },
    "balanced": {
        "label": "Balanced",
        "description": "Good quality with reasonable cost — Ollama primary, OpenRouter fallback",
        "settings": {
            "ai_mode": "ai_full",
            "ai_model_risk_explain": "ollama_cloud:ministral-3:8b-cloud",
            "ai_model_market_narrative": "ollama_cloud:ministral-3:8b-cloud",
            "ai_model_insight_summary": "ollama_cloud:ministral-3:8b-cloud",
            "ai_model_market_overview": "ollama_cloud:ministral-3:8b-cloud",
            "ai_fallback_provider": "openrouter",
            "ai_fallback_model": "openai/gpt-4o-mini",
            "ai_cache_ttl_seconds": 3600,
            "ai_cache_semantic_enabled": True,
            "ai_cache_max_entries": 1000,
            "feature_ai_summary": True,
        },
    },
    "quality": {
        "label": "Maximum Quality",
        "description": "Best results — OpenRouter primary with Ollama fallback",
        "settings": {
            "ai_mode": "ai_full",
            "ai_model_risk_explain": "openrouter:openai/gpt-4o-mini",
            "ai_model_market_narrative": "openrouter:openai/gpt-4o-mini",
            "ai_model_insight_summary": "openrouter:openai/gpt-4o-mini",
            "ai_model_market_overview": "openrouter:openai/gpt-4o-mini",
            "ai_fallback_provider": "ollama_cloud",
            "ai_fallback_model": "ministral-3:8b-cloud",
            "ai_cache_ttl_seconds": 1800,
            "ai_cache_semantic_enabled": False,
            "ai_cache_max_entries": 2000,
            "feature_ai_summary": True,
        },
    },
    "public_demo": {
        "label": "Public Demo",
        "description": "24h public window, AI off, forensics/export hidden",
        "settings": {
            "ai_mode": "ai_off",
            "public_history_hours": 24,
            "public_export_enabled": False,
            "public_show_forensics": False,
            "public_deterministic_why": True,
            "demo_mode_enabled": False,
            "retention_preset": "minimal",
        },
    },
    "data_hoarder": {
        "label": "Data Hoarder",
        "description": "Research retention + AI lite for long-term asset building",
        "settings": {
            "ai_mode": "ai_lite",
            "retention_preset": "research",
            "feature_osint_feed": True,
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
        from services.source_usage import get_source_usage_summary

        if key in ("provider_dexscreener", "provider_coingecko", "provider_defillama",
                     "provider_moralis", "provider_thegraph", "provider_flipside"):
            source_name = key.replace("provider_", "")
            usage_summary = get_source_usage_summary(db)
            source_usage = usage_summary.get("sources", {}).get(source_name, {})
            return source_usage.get("call_count", 0)
    except Exception:
        import logging
        logging.getLogger(__name__).warning("get_current_usage failed", exc_info=True)

    return None
