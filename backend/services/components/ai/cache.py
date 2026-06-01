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
_LOCAL_DAILY_TOKENS = 0

# Cache storage
_AI_CACHE: OrderedDict[str, Tuple[float, str, Dict[str, Any]]] = OrderedDict()
_AI_SEMANTIC_CACHE: OrderedDict[str, Tuple[float, str, str, Dict[str, Any], str]] = OrderedDict()
_SEMANTIC_CACHE_ENABLED = os.getenv("AI_CACHE_SEMANTIC_ENABLED", "").strip().lower() in ("1", "true", "yes")
_SEMANTIC_CACHE_THRESHOLD = float(os.getenv("AI_CACHE_SEMANTIC_THRESHOLD", "0.90"))
_MAX_SEMANTIC_CACHE_ENTRIES = int(os.getenv("AI_CACHE_MAX_SEMANTIC_ENTRIES", "200"))

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
        semantic_key = f"{feature}_{hashlib.md5(prompt.encode()).hexdigest()}"
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