"""Cache layer for read-heavy API responses — uses CacheManager from core."""

from __future__ import annotations

import os
from typing import Any, Callable

from backend.core.cache_manager import cache

_CACHE_ENABLED = os.getenv("ENABLE_REDIS_CACHE", "").strip().lower() in ("1", "true", "yes")
_TTL_SECONDS = int(os.getenv("REDIS_CACHE_TTL_SECONDS", "45"))

CACHE_TTL = {
    "price": 30,
    "supply": 300,
    "trends": 600,
    "events": 300,
    "sources": 60,
}


def cache_get(key: str) -> dict[str, Any] | None:
    if not _CACHE_ENABLED:
        return None
    return cache.get(key)


def cache_set(key: str, payload: dict[str, Any], ttl: int | None = None) -> None:
    if not _CACHE_ENABLED:
        return
    cache.set(key, payload, ttl or _TTL_SECONDS)


def invalidate_dashboard(asset: str | None) -> None:
    if not _CACHE_ENABLED:
        return
    sym = (asset or "DEFAULT").upper()
    cache.delete(f"helix:dashboard:{sym}")


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


def get_or_build_cache(key: str, builder_fn: Callable, data_type: str = "trends"):
    """Get from cache or build and cache by data type TTL."""
    ttl = CACHE_TTL.get(data_type, 300)
    hit = cache_get(key)
    if hit is not None:
        return hit
    result = builder_fn()
    cache_set(key, result, ttl)
    return result
