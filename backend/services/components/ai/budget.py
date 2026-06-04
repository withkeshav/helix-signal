"""AI budget and token management components."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict

# Budget configuration
_LOCAL_DAILY_TOKENS = 0
_LOCAL_TOKEN_DATE = ""

# Lua script for atomic token budget enforcement in Redis
_BUDGET_LUA_SCRIPT = """
local key = KEYS[1]
local budget_limit = tonumber(ARGV[1])
local token_count = tonumber(ARGV[2])
local ttl_seconds = tonumber(ARGV[3])

local current = redis.call('GET', key)
if current == false then
    redis.call('SET', key, token_count, 'EX', ttl_seconds)
    return 1
end

local new_total = tonumber(current) + token_count
if new_total <= budget_limit then
    redis.call('INCRBY', key, token_count)
    return 1
end

return 0
"""

def _reset_local_if_new_day() -> None:
    """Reset local token counter if it's a new day."""
    global _LOCAL_DAILY_TOKENS, _LOCAL_TOKEN_DATE
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _LOCAL_TOKEN_DATE != today:
        _LOCAL_DAILY_TOKENS = 0
        _LOCAL_TOKEN_DATE = today
    
def _get_limit() -> int:
    """Get daily token budget limit from settings."""
    from providers.settings import get_setting
    try:
        return int(get_setting("ai_daily_token_budget"))
    except (ValueError, TypeError):
        return 50000  # fallback to default
    
def _deduct_tokens(count: int) -> bool:
    """Deduct tokens from budget with Redis support for distributed deployments."""
    global _LOCAL_DAILY_TOKENS
    _reset_local_if_new_day()
    
    limit = _get_limit()
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        try:
            from core.cache_manager import cache
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = f"helix:ai:daily_tokens:{today}"
            client = cache._redis
            if client is None:
                raise RuntimeError("redis_unavailable")
            ok = client.eval(_BUDGET_LUA_SCRIPT, 1, key, limit, count, 86400)
            return bool(ok)
        except Exception:
            pass
    if _LOCAL_DAILY_TOKENS + count > limit:
        return False
    _LOCAL_DAILY_TOKENS += count
    return True

def _within_budget(count: int) -> bool:
    """Check if deducting tokens would be within budget (non-deducting)."""
    global _LOCAL_DAILY_TOKENS
    _reset_local_if_new_day()
    
    limit = _get_limit()
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        try:
            from core.cache_manager import cache
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = f"helix:ai:daily_tokens:{today}"
            client = cache._redis
            if client is None:
                raise RuntimeError("redis_unavailable")
            current = client.get(key) or "0"
            return int(current) + count <= limit
        except Exception:
            pass
    return _LOCAL_DAILY_TOKENS + count <= limit

def get_budget_status() -> Dict[str, Any]:
    """Get current AI budget status."""
    global _LOCAL_DAILY_TOKENS
    _reset_local_if_new_day()
    
    limit = _get_limit()
    redis_url = os.getenv("REDIS_URL", "").strip()
    used = _LOCAL_DAILY_TOKENS
    
    if redis_url:
        try:
            from core.cache_manager import cache
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = f"helix:ai:daily_tokens:{today}"
            client = cache._redis
            if client is not None:
                current = client.get(key) or "0"
                used = int(current)
        except Exception:
            pass
    
    remaining = max(0, limit - used)
    pct = (used / limit * 100) if limit > 0 else 0
    
    return {
        "daily_budget": limit,
        "tokens_used_today": used,
        "tokens_remaining": remaining,
        "pct_used": round(pct, 2),
        "within_budget": remaining > 0
    }