"""Cache layer for read-heavy API responses — uses enhanced CacheService."""

from __future__ import annotations

import os
from typing import Any, Callable

from services.cache_service import cache_service

_TTL_SECONDS = int(os.getenv("REDIS_CACHE_TTL_SECONDS", "45"))


def _cache_enabled() -> bool:
    from providers.settings import get_setting
    try:
        return bool(get_setting("enable_redis_cache"))
    except Exception:
        return os.getenv("ENABLE_REDIS_CACHE", "").strip().lower() in ("1", "true", "yes")


def cache_get(key: str) -> dict[str, Any] | None:
    if not _cache_enabled():
        return None
    return cache_service.get(key)


def cache_set(key: str, payload: dict[str, Any], ttl: int | None = None) -> None:
    if not _cache_enabled():
        return
    cache_service.set(key, payload, ttl or _TTL_SECONDS)


def invalidate_dashboard(asset: str | None) -> None:
    if not _cache_enabled():
        return
    cache_service.invalidate_dashboard(asset)


def dashboard_cache_key(asset: str | None) -> str:
    return f"helix:dashboard:{(asset or 'USDT').upper()}"


def get_or_build_dashboard(
    asset: str | None,
    builder: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    key = dashboard_cache_key(asset)
    hit = cache_get(key)
    if hit is not None:
        hit["_cache"] = "hit"
        return hit
    payload = builder()
    cache_set(key, payload)
    payload["_cache"] = "miss"
    return payload


