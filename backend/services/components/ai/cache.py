"""AI cache components."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Set, Tuple

# Cache configuration
_CACHE_TTL_SECONDS = int(os.getenv("AI_CACHE_TTL_SECONDS", "3600"))
_MAX_CACHE_ENTRIES = int(os.getenv("AI_CACHE_MAX_ENTRIES", "1000"))
_CACHE_EVICTIONS = 0

# Cache storage
_AI_CACHE: OrderedDict[str, Tuple[float, str, Dict[str, Any]]] = OrderedDict()
_AI_SEMANTIC_CACHE: OrderedDict[str, Tuple[float, str, str, Dict[str, Any], str]] = OrderedDict()
_SEMANTIC_CACHE_ENABLED = os.getenv("AI_CACHE_SEMANTIC_ENABLED", "").strip().lower() in ("1", "true", "yes")
_SEMANTIC_CACHE_THRESHOLD = float(os.getenv("AI_CACHE_SEMANTIC_THRESHOLD", "0.90"))
_MAX_SEMANTIC_CACHE_ENTRIES = int(os.getenv("AI_CACHE_MAX_SEMANTIC_ENTRIES", "200"))

# Redis configuration
_AI_REDIS_CACHE_PREFIX = "helix:ai:cache:"

# Per-feature TTL overrides (seconds) - for enhanced cache functions
def _get_feature_cache_ttl() -> dict[str, int]:
    """Get per-feature TTL overrides with defaults, potentially overridden by settings."""
    default_ttl = {
        "risk_explain": 3600,
        "market_narrative": 3000,
        "anomaly_investigation": 1800,
        "market_overview": 1200,
        "insight_summary": 3600,
    }
    try:
        from providers.settings import get_setting
        mn_ttl = get_setting("ai_cache_ttl_market_narrative")
        if mn_ttl is not None:
            default_ttl["market_narrative"] = int(mn_ttl)
    except Exception:
        pass
    return default_ttl

_FEATURE_CACHE_TTL: dict[str, int] = _get_feature_cache_ttl()

def _prompt_hash(feature: str, context: Dict[str, Any]) -> str:
    """Generate SHA-256 hash of feature + context."""
    hasher = hashlib.sha256()
    hasher.update(feature.encode())
    hasher.update(json.dumps(context, sort_keys=True).encode())
    return hasher.hexdigest()

def _text_trigrams(text: str) -> Set[Tuple[str, str, str]]:
    """Extract character trigrams from text."""
    if len(text) < 3:
        return set()
    return {(text[i], text[i + 1], text[i + 2]) for i in range(len(text) - 2)}

def _trigram_similarity(a: str, b: str) -> float:
    """Calculate character trigram Jaccard similarity."""
    if not a or not b:
        return 1.0 if a == b else 0.0
    trigrams_a = _text_trigrams(a.lower())
    trigrams_b = _text_trigrams(b.lower())
    if not trigrams_a and not trigrams_b:
        return 1.0
    intersection = len(trigrams_a & trigrams_b)
    union = len(trigrams_a | trigrams_b)
    return intersection / union if union > 0 else 0.0

def _try_redis_cache() -> Any:
    """Get Redis cache client if available."""
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        return None
    try:
        from core.cache_manager import cache
        return cache._redis if cache._redis else None
    except Exception:
        return None

def cache_get_enhanced(key: str, feature: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Enhanced cache get with Redis integration and per-feature TTL."""
    # Try Redis first
    rc = _try_redis_cache()
    if rc:
        try:
            val = rc.get(_AI_REDIS_CACHE_PREFIX + key)
            if val:
                return val
        except Exception:
            pass
    
    # Fallback to in-memory cache
    entry = _AI_CACHE.get(key)
    if not entry:
        return None
    
    ts, entry_feature, payload = entry
    ttl = _FEATURE_CACHE_TTL.get(feature or entry_feature, _CACHE_TTL_SECONDS)
    if time.time() - ts > ttl:
        _AI_CACHE.pop(key, None)
        return None
    
    # LRU promotion
    _AI_CACHE.move_to_end(key)
    return payload

def cache_set_enhanced(key: str, feature: str, prompt: str, payload: Dict[str, Any]) -> None:
    """Enhanced cache set with Redis integration and per-feature TTL."""
    now = time.time()
    
    # Store in Redis if available
    rc = _try_redis_cache()
    if rc:
        try:
            ttl = _FEATURE_CACHE_TTL.get(feature, _CACHE_TTL_SECONDS)
            rc.set(_AI_REDIS_CACHE_PREFIX + key, payload, ex=ttl)
        except Exception:
            pass
    
    # Store in in-memory cache
    if key in _AI_CACHE:
        _AI_CACHE.move_to_end(key)
        _AI_CACHE[key] = (now, feature, payload)
    else:
        if len(_AI_CACHE) >= _MAX_CACHE_ENTRIES:
            _AI_CACHE.popitem(last=False)
            global _CACHE_EVICTIONS
            _CACHE_EVICTIONS += 1
        _AI_CACHE[key] = (now, feature, payload)
    
    # Add to semantic cache if enabled
    if _SEMANTIC_CACHE_ENABLED and prompt:
        semantic_key = f"{feature}_{hashlib.md5(prompt.encode(), usedforsecurity=False).hexdigest()}"
        expiry = now + _FEATURE_CACHE_TTL.get(feature, _CACHE_TTL_SECONDS)
        if semantic_key in _AI_SEMANTIC_CACHE:
            _AI_SEMANTIC_CACHE.move_to_end(semantic_key)
            _AI_SEMANTIC_CACHE[semantic_key] = (expiry, feature, prompt, payload, key)
        else:
            if len(_AI_SEMANTIC_CACHE) >= _MAX_SEMANTIC_CACHE_ENTRIES:
                _AI_SEMANTIC_CACHE.popitem(last=False)
            _AI_SEMANTIC_CACHE[semantic_key] = (expiry, feature, prompt, payload, key)

def cache_get(key: str) -> Optional[Dict[str, Any]]:
    """Get cached response by exact-match key."""
    now = time.time()
    entry = _AI_CACHE.get(key)
    if entry is None:
        return None
    expiry, stored_key, payload = entry
    if now > expiry:
        _AI_CACHE.pop(key, None)
        return None
    return payload

def cache_set(key: str, feature: str, prompt: str, payload: Dict[str, Any]) -> None:
    """Store response in exact-match cache."""
    now = time.time()
    expiry = now + _CACHE_TTL_SECONDS
    
    # Add to cache with LRU eviction
    _AI_CACHE[key] = (expiry, key, payload)
    while len(_AI_CACHE) > _MAX_CACHE_ENTRIES:
        _AI_CACHE.popitem(last=False)
    
    # Add to semantic cache if enabled
    if _SEMANTIC_CACHE_ENABLED:
        semantic_key = f"{feature}_{hashlib.md5(prompt.encode(), usedforsecurity=False).hexdigest()}"
        _AI_SEMANTIC_CACHE[semantic_key] = (expiry, feature, prompt, payload, key)
        while len(_AI_SEMANTIC_CACHE) > _MAX_SEMANTIC_CACHE_ENTRIES:
            _AI_SEMANTIC_CACHE.popitem(last=False)

def semantic_cache_search(feature: str, prompt: str) -> Optional[Dict[str, Any]]:
    """Search semantic cache for similar prompts."""
    if not _SEMANTIC_CACHE_ENABLED:
        return None
    
    now = time.time()
    best_match = None
    best_similarity = 0.0
    
    # Search through semantic cache
    expired_keys = []
    for key, entry in _AI_SEMANTIC_CACHE.items():
        expiry, entry_feature, entry_prompt, payload, exact_key = entry
        if now > expiry:
            expired_keys.append(key)
            continue
        if entry_feature != feature:
            continue
            
        similarity = _trigram_similarity(prompt, entry_prompt)
        if similarity >= _SEMANTIC_CACHE_THRESHOLD and similarity > best_similarity:
            best_similarity = similarity
            best_match = payload
    
    # Remove expired entries
    for key in expired_keys:
        _AI_SEMANTIC_CACHE.pop(key, None)
    
    return best_match

def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    now = time.time()
    
    # Exact match cache stats
    exact_hits = sum(1 for entry in _AI_CACHE.values() if now <= entry[0])
    exact_expired = sum(1 for entry in _AI_CACHE.values() if now > entry[0])
    
    # Semantic cache stats
    semantic_hits = sum(1 for entry in _AI_SEMANTIC_CACHE.values() if now <= entry[0])
    semantic_expired = sum(1 for entry in _AI_SEMANTIC_CACHE.values() if now > entry[0])
    
    return {
        "exact_match": {
            "entries": len(_AI_CACHE),
            "active": exact_hits,
            "expired": exact_expired,
            "max_entries": _MAX_CACHE_ENTRIES,
            "ttl_seconds": _CACHE_TTL_SECONDS
        },
        "semantic": {
            "entries": len(_AI_SEMANTIC_CACHE),
            "active": semantic_hits,
            "expired": semantic_expired,
            "max_entries": _MAX_SEMANTIC_CACHE_ENTRIES,
            "enabled": _SEMANTIC_CACHE_ENABLED,
            "threshold": _SEMANTIC_CACHE_THRESHOLD
        }
    }