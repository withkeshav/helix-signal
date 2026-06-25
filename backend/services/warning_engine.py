"""Warning engine — checks usage thresholds and generates warnings."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from providers.settings import _DEFAULT_SETTINGS


def check_warnings(db: Session | None = None) -> list[dict[str, Any]]:
    """Check all configured warning thresholds and return active warnings.

    Returns a list of warning dicts with keys:
        type, severity, message, current_value, threshold, setting_key
    """
    warnings: list[dict[str, Any]] = []

    # 1. AI daily token budget threshold
    _check_ai_budget(warnings, db)

    # 2. Source usage vs rate limits
    _check_source_usage(warnings, db)

    return warnings


def _check_ai_budget(warnings: list[dict[str, Any]], db: Session | None) -> None:
    """Check if AI token budget usage exceeds the warning threshold."""
    from services.ai_router import get_budget_status

    threshold = _get_warning_threshold("ai_daily_token_budget", db)
    if threshold is None:
        return

    budget_status = get_budget_status()
    pct_used = budget_status.get("pct_used", 0) / 100.0
    used = budget_status.get("tokens_used_today", 0)
    total = budget_status.get("daily_budget", 0)

    if pct_used >= threshold:
        severity = "critical" if pct_used >= 0.95 else "warning"
        warnings.append({
            "type": "ai_budget",
            "severity": severity,
            "message": (
                f"AI daily token budget at {budget_status.get('pct_used', 0)}% "
                f"({used}/{total} tokens)"
            ),
            "current_value": used,
            "threshold": int(total * threshold),
            "setting_key": "ai_daily_token_budget",
        })


def _check_source_usage(warnings: list[dict[str, Any]], db: Session | None) -> None:
    """Check if data source usage exceeds rate-limit warning thresholds."""
    from services.source_usage import get_source_usage_summary

    if db is None:
        return

    usage_summary = get_source_usage_summary(db)

    for setting_key, meta in _DEFAULT_SETTINGS.items():
        if not setting_key.startswith("provider_"):
            continue
        threshold = meta.get("warning_threshold")
        if threshold is None:
            continue
        rate_limit = meta.get("rate_limit_rpm")
        if rate_limit is None:
            continue

        source_name = setting_key.replace("provider_", "")
        source_data = usage_summary.get("sources", {}).get(source_name, {})
        call_count = source_data.get("call_count", 0)

        effective_limit = rate_limit
        if call_count >= effective_limit * threshold:
            severity = "critical" if call_count >= effective_limit * 0.95 else "warning"
            warnings.append({
                "type": "source_rate_limit",
                "severity": severity,
                "message": (
                    f"Source '{source_name}' at {call_count}/{effective_limit} "
                    f"calls ({(call_count / effective_limit * 100) if effective_limit else 0:.0f}%)"
                ),
                "current_value": call_count,
                "threshold": int(effective_limit * threshold),
                "setting_key": setting_key,
            })


def _get_warning_threshold(key: str, db: Session | None) -> float | None:
    """Read warning_threshold from settings metadata for a given key."""
    meta = _DEFAULT_SETTINGS.get(key)
    if meta is None:
        return None
    return meta.get("warning_threshold")
