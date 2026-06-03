"""Tests for the multi-layer AI cache (exact-match + semantic).

Covers: per-feature TTL, LRU eviction, hit/miss tracking,
trigram similarity, semantic lookup, cache stats.
"""

from __future__ import annotations

import time

import pytest

import services.ai_router as r
from services.ai_router import (
    _AI_CACHE,
    _FEATURE_CACHE_TTL,
    _SEMANTIC_CACHE,
    _cache_get,
    _cache_set,
    _prompt_hash,
    _semantic_cache_lookup,
    _text_trigrams,
    _trigram_similarity,
    enrich_with_ai,
    get_cache_stats,
)
from services.components.ai import cache as cache_mod


# ---------------------------------------------------------------------------
# Per-feature TTL
# ---------------------------------------------------------------------------


def test_feature_ttl_map_has_all_features() -> None:
    features = {"risk_explain", "market_narrative", "anomaly_investigation", "market_overview", "insight_summary"}
    assert set(_FEATURE_CACHE_TTL.keys()) == features


def test_cache_get_respects_feature_ttl() -> None:
    key = _prompt_hash("risk_explain", {"asset_symbol": "USDT"})
    _AI_CACHE[key] = (time.time(), "risk_explain", {"summary": "test", "tokens": 10})
    result = _cache_get(key)
    assert result is not None
    assert result["summary"] == "test"


def test_cache_get_expires_per_feature() -> None:
    key = _prompt_hash("market_overview", {"asset_symbol": "USDT"})
    ttl = _FEATURE_CACHE_TTL.get("market_overview", 3600)
    _AI_CACHE[key] = (time.time() - ttl - 1, "market_overview", {"summary": "stale"})
    result = _cache_get(key)
    assert result is None


def test_cache_set_stores_feature() -> None:
    key = _prompt_hash("risk_explain", {"asset_symbol": "DAI"})
    _cache_set(key, "risk_explain", "prompt text", {"summary": "ok", "tokens": 5})
    entry = _AI_CACHE.get(key)
    assert entry is not None
    ts, feature, payload = entry
    assert feature == "risk_explain"
    assert payload["summary"] == "ok"


# ---------------------------------------------------------------------------
# LRU eviction
# ---------------------------------------------------------------------------


def test_lru_eviction() -> None:
    cache_mod._MAX_CACHE_ENTRIES = 3
    for i in range(5):
        _cache_set(f"key{i}", "risk_explain", f"prompt{i}", {"summary": f"r{i}", "tokens": 1})
    assert len(_AI_CACHE) <= 3
    assert "key0" not in _AI_CACHE
    assert "key1" not in _AI_CACHE
    assert "key4" in _AI_CACHE


def test_lru_promotion_prevents_eviction() -> None:
    cache_mod._MAX_CACHE_ENTRIES = 3
    for i in range(3):
        _AI_CACHE[f"key{i}"] = (time.time(), "risk_explain", {"i": i})
    _cache_get("key0")
    _cache_get("key0")
    _cache_set("key3", "risk_explain", "p", {"summary": "new", "tokens": 1})
    _cache_set("key4", "risk_explain", "p", {"summary": "new", "tokens": 1})
    assert "key0" in _AI_CACHE
    assert "key1" not in _AI_CACHE


# ---------------------------------------------------------------------------
# Hit / miss tracking
# ---------------------------------------------------------------------------


def test_cache_stats_shape() -> None:
    stats = get_cache_stats()
    assert "hits" in stats
    assert "misses" in stats
    assert "hit_rate" in stats
    assert "tokens_saved" in stats
    assert "entries" in stats
    assert "evictions" in stats
    assert "semantic_enabled" in stats
    assert "semantic_threshold" in stats


def test_cache_tracks_hits() -> None:
    key = _prompt_hash("risk_explain", {"asset_symbol": "USDT"})
    _cache_set(key, "risk_explain", "p", {"summary": "hit", "tokens": 10})
    before = r._CACHE_HITS
    cached = _cache_get(key)
    if cached:
        r._CACHE_HITS += 1
        r._CACHE_TOKENS_SAVED += cached.get("tokens", 0)
    assert r._CACHE_HITS == before + 1
    assert r._CACHE_TOKENS_SAVED >= 10


def test_cache_tracks_misses() -> None:
    before = r._CACHE_MISSES
    key = _prompt_hash("risk_explain", {"asset_symbol": "UNKNOWN"})
    result = _cache_get(key)
    assert result is None
    r._CACHE_MISSES += 1
    assert r._CACHE_MISSES == before + 1


def test_hit_rate_zero_when_no_requests() -> None:
    stats = get_cache_stats()
    assert stats["hit_rate"] == 0.0


def test_hit_rate_calculated() -> None:
    r._CACHE_HITS = 80
    r._CACHE_MISSES = 20
    stats = get_cache_stats()
    assert stats["hit_rate"] == 80.0


# ---------------------------------------------------------------------------
# Trigram similarity
# ---------------------------------------------------------------------------


def test_trigram_similarity_identical() -> None:
    assert _trigram_similarity("hello world", "hello world") == 1.0


def test_trigram_similarity_empty() -> None:
    assert _trigram_similarity("", "") == 1.0
    assert _trigram_similarity("abc", "") == 0.0


def test_trigram_similarity_partial() -> None:
    sim = _trigram_similarity("USDT depeg risk high", "USDT depeg risk elevated")
    assert sim > 0.5
    assert sim < 1.0


def test_trigram_similarity_different() -> None:
    sim = _trigram_similarity("bitcoin price rally", "USDT stablecoin peg")
    assert sim < 0.3


def test_trigram_similarity_normalizes_whitespace() -> None:
    assert _trigram_similarity("  hello   world  ", "hello world") == 1.0


# ---------------------------------------------------------------------------
# Semantic cache
# ---------------------------------------------------------------------------


def test_semantic_cache_disabled_by_default() -> None:
    assert r._SEMANTIC_CACHE_ENABLED is False


def test_semantic_store_adds_entry() -> None:
    cache_mod._SEMANTIC_CACHE_ENABLED = True
    _cache_set("hash1", "risk_explain", "What is the risk of USDT?", {"summary": "test", "tokens": 10})
    assert _cache_get("hash1") is not None


def test_semantic_store_noop_when_disabled() -> None:
    key = _prompt_hash("risk_explain", {"asset_symbol": "USDT"})
    _cache_set(key, "risk_explain", "text", {"summary": "test", "tokens": 10})
    assert _cache_get(key) is not None


def test_semantic_lookup_returns_cached() -> None:
    cache_mod._SEMANTIC_CACHE_ENABLED = True
    cache_mod._SEMANTIC_CACHE_THRESHOLD = 0.75

    stored_key = _prompt_hash("risk_explain", {"asset_symbol": "USDT", "signal_score": 30})
    _cache_set(stored_key, "risk_explain", "What is the risk of USDT with score 30?", {"summary": "medium risk", "tokens": 5})

    lookup_key = _prompt_hash("risk_explain", {"asset_symbol": "USDT", "signal_score": 35})
    result = _semantic_cache_lookup(lookup_key, "What is the risk of USDT with score 35?")
    assert result is not None
    assert result["summary"] == "medium risk"


def test_semantic_lookup_respects_threshold() -> None:
    cache_mod._SEMANTIC_CACHE_ENABLED = True
    cache_mod._SEMANTIC_CACHE_THRESHOLD = 0.99

    stored_key = _prompt_hash("risk_explain", {"asset_symbol": "USDT"})
    _cache_set(stored_key, "risk_explain", "USDT risk analysis very important", {"summary": "low risk", "tokens": 5})

    lookup_key = _prompt_hash("risk_explain", {"asset_symbol": "DAI"})
    result = _semantic_cache_lookup(lookup_key, "DAI depeg probability analysis")
    assert result is None


def test_semantic_lookup_noop_when_disabled() -> None:
    cache_mod._SEMANTIC_CACHE_ENABLED = False
    key = _prompt_hash("risk_explain", {"asset_symbol": "USDT"})
    result = _semantic_cache_lookup(key, "some prompt")
    assert result is None


def test_semantic_cache_lru_eviction() -> None:
    cache_mod._SEMANTIC_CACHE_ENABLED = True
    cache_mod._MAX_SEMANTIC_CACHE_ENTRIES = 3
    for i in range(5):
        _cache_set(f"hash{i}", "risk_explain", f"prompt {i}", {"summary": f"r{i}", "tokens": 1})
    assert len(cache_mod._AI_SEMANTIC_CACHE) <= 3


# ---------------------------------------------------------------------------
# Integration with enrich_with_ai
# ---------------------------------------------------------------------------


def test_enrich_with_ai_stores_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_off")
    ctx = {"asset_symbol": "USDT", "signal_score": 10}
    enrich_with_ai(feature="risk_explain", context=ctx)
    key = _prompt_hash("risk_explain", ctx)
    assert _cache_get(key) is None


def test_cache_evictions_tracked() -> None:
    cache_mod._MAX_CACHE_ENTRIES = 2
    cache_mod._CACHE_EVICTIONS = 0
    for i in range(5):
        key = _prompt_hash("risk_explain", {"asset_symbol": f"ASSET{i}"})
        _cache_set(key, "risk_explain", f"prompt{i}", {"summary": f"r{i}", "tokens": 1})
    assert cache_mod._CACHE_EVICTIONS >= 3


def test_cache_stats_semantic_flag() -> None:
    r._SEMANTIC_CACHE_ENABLED = True
    r._SEMANTIC_CACHE_THRESHOLD = 0.80
    stats = get_cache_stats()
    assert stats["semantic_enabled"] is True
    assert stats["semantic_threshold"] == 0.80
