"""Optional Redis cache for read-heavy API responses (dashboard)."""

from __future__ import annotations

import json
import os
from typing import Any, Callable

_CACHE_ENABLED = os.getenv("ENABLE_REDIS_CACHE", "").strip().lower() in ("1", "true", "yes")
_TTL_SECONDS = int(os.getenv("REDIS_CACHE_TTL_SECONDS", "45"))
_redis_client = None


def _client():
    global _redis_client
    if _redis_client is None:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis.from_url(url, decode_responses=True)
    return _redis_client


def cache_get(key: str) -> dict[str, Any] | None:
    if not _CACHE_ENABLED:
        return None
    try:
        raw = _client().get(key)
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def cache_set(key: str, payload: dict[str, Any], ttl: int | None = None) -> None:
    if not _CACHE_ENABLED:
        return
    try:
        _client().setex(key, ttl or _TTL_SECONDS, json.dumps(payload, default=str))
    except Exception:
        pass


def invalidate_dashboard(asset: str | None) -> None:
    if not _CACHE_ENABLED:
        return
    sym = (asset or "DEFAULT").upper()
    try:
        _client().delete(f"helix:dashboard:{sym}")
    except Exception:
        pass


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
