"""Event category catalog for alert routing (webhooks + SMTP)."""

from __future__ import annotations

from typing import Any

# Canonical categories operators subscribe to in Settings / webhook endpoints.
EVENT_CATALOG: list[dict[str, str]] = [
    {"id": "peg_deviation", "label": "Peg deviation"},
    {"id": "signal_band_change", "label": "Signal band change"},
    {"id": "depeg_pressure_change", "label": "Depeg pressure"},
    {"id": "large_supply_change", "label": "Large supply change"},
    {"id": "concentration_change", "label": "Concentration change"},
    {"id": "data_staleness", "label": "Data staleness"},
    {"id": "source_failure", "label": "Source failure"},
    {"id": "source_recovered", "label": "Source recovered"},
    {"id": "anomaly", "label": "Anomaly"},
    {"id": "osint", "label": "OSINT / news"},
    {"id": "issuer_freeze", "label": "Issuer freeze"},
    {"id": "blacklist", "label": "Blacklist"},
    {"id": "yield_apy_collapse", "label": "Yield APY collapse"},
    {"id": "funding_rate_negative", "label": "Negative funding"},
    {"id": "web_search_job_failed", "label": "Web search failed"},
    {"id": "web_search_cache_stale", "label": "Web search cache stale"},
    {"id": "ai_provider_down", "label": "AI provider down"},
    {"id": "ai_feature_degraded", "label": "AI feature degraded"},
]


def event_category(event_type: str | None) -> str:
    """Normalize SignalEvent.event_type to a catalog category id."""
    et = (event_type or "").strip()
    if not et:
        return "unknown"
    lower = et.lower()
    # Rule engine uses "ASSET:type:severity"
    if ":" in et:
        parts = et.split(":")
        if len(parts) >= 2:
            mid = parts[1].lower()
            if mid in {c["id"] for c in EVENT_CATALOG}:
                return mid
            if "freeze" in mid:
                return "issuer_freeze"
            if "peg" in mid:
                return "peg_deviation"
    for c in EVENT_CATALOG:
        if lower == c["id"] or lower.startswith(c["id"]):
            return c["id"]
    if "anomaly" in lower:
        return "anomaly"
    if "osint" in lower or lower in ("depeg_confirmed", "issuer_freeze", "geopolitical"):
        return "osint" if "freeze" not in lower else "issuer_freeze"
    if "blacklist" in lower or "freeze" in lower:
        return "blacklist" if "blacklist" in lower else "issuer_freeze"
    if "supply" in lower:
        return "large_supply_change"
    if "band" in lower:
        return "signal_band_change"
    if "depeg" in lower:
        return "depeg_pressure_change"
    if "source" in lower and "recover" in lower:
        return "source_recovered"
    if "source" in lower:
        return "source_failure"
    if "web_search" in lower:
        return "web_search_job_failed" if "fail" in lower else "web_search_cache_stale"
    if "ai_provider" in lower:
        return "ai_provider_down"
    if "ai_feature" in lower:
        return "ai_feature_degraded"
    return lower[:64]


def catalog_for_api() -> list[dict[str, Any]]:
    return list(EVENT_CATALOG)
