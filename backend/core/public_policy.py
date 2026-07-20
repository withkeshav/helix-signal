"""Public display policy — 24h (configurable) lookback for anonymous visitors."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def demo_mode_active(db: Session | None) -> bool:
    from providers.settings import get_setting

    if not _coerce_bool(get_setting("demo_mode_enabled", db)):
        return False
    until = str(get_setting("demo_mode_until", db) or "").strip()
    if not until:
        return True
    try:
        # Accept Z suffix
        ts = datetime.fromisoformat(until.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < ts
    except Exception:
        return True


def effective_public_history_hours(db: Session | None) -> int:
    from providers.settings import get_setting

    if demo_mode_active(db):
        try:
            return max(1, int(get_setting("demo_history_hours", db) or 168))
        except (TypeError, ValueError):
            return 168
    try:
        return max(1, int(get_setting("public_history_hours", db) or 24))
    except (TypeError, ValueError):
        return 24


def window_allowed_for_hours(window: str, max_hours: int) -> bool:
    """Return True if a trends window label fits within max_hours."""
    w = (window or "").strip().lower()
    mapping = {
        "6h": 6,
        "24h": 24,
        "7d": 24 * 7,
        "30d": 24 * 30,
        "90d": 24 * 90,
    }
    need = mapping.get(w)
    if need is None:
        return False
    return need <= max_hours


def public_config(db: Session | None) -> dict[str, Any]:
    from providers.settings import get_setting

    hours = effective_public_history_hours(db)
    tabs = str(get_setting("public_tabs_enabled", db) or "signal,market,intel")
    return {
        "public_history_hours": hours,
        "demo_mode_active": demo_mode_active(db),
        "public_tabs": [t.strip() for t in tabs.split(",") if t.strip()],
        "public_export_enabled": _coerce_bool(get_setting("public_export_enabled", db)),
        "public_show_forensics": _coerce_bool(get_setting("public_show_forensics", db)),
        "public_deterministic_why": _coerce_bool(get_setting("public_deterministic_why", db)),
        "intelligence_api_enabled": _coerce_bool(get_setting("intelligence_api_enabled", db)),
    }
