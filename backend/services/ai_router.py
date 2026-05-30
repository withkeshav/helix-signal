"""Optional LLM router — add-on only; core platform must run with AI_MODE=ai_off.

Dynamic provider chains driven by Settings metadata. Tiered routing:
Cache -> Groq (cheapest) -> Ollama Cloud -> OpenRouter Free -> OpenRouter Paid.
Rate-limit-aware, cost-aware, fully fallback-safe.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timezone
from functools import partial
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Cache: exact-match (SHA-256) + semantic (trigram similarity)
# ---------------------------------------------------------------------------

_AI_CACHE: OrderedDict[str, tuple[float, str, dict[str, Any]]] = OrderedDict()
_CACHE_TTL_SECONDS = int(os.getenv("AI_CACHE_TTL_SECONDS", "3600"))
_LOCAL_DAILY_TOKENS = 0
_LOCAL_TOKEN_DATE = ""
_AI_REDIS_CACHE_PREFIX = "helix:ai:cache:"

# Per-feature TTL overrides (seconds) — fall back to _CACHE_TTL_SECONDS
_FEATURE_CACHE_TTL: dict[str, int] = {
    "risk_explain": 3600,
    "market_narrative": 3000,
    "anomaly_investigation": 1800,
    "market_overview": 1200,
    "insight_summary": 3600,
}

# Hit / miss / eviction tracking
_CACHE_HITS = 0
_CACHE_MISSES = 0
_CACHE_EVICTIONS = 0
_CACHE_TOKENS_SAVED = 0

# In-memory LRU limits
_MAX_CACHE_ENTRIES = int(os.getenv("AI_CACHE_MAX_ENTRIES", "1000"))

# Semantic cache (trigram-based prompt similarity, off by default)
_SEMANTIC_CACHE: OrderedDict[str, str] = OrderedDict()  # cache_key -> prompt_text
_SEMANTIC_CACHE_ENABLED = os.getenv("AI_CACHE_SEMANTIC_ENABLED", "").strip().lower() in ("1", "true", "yes")
_SEMANTIC_CACHE_THRESHOLD = float(os.getenv("AI_CACHE_SEMANTIC_THRESHOLD", "0.90"))
_MAX_SEMANTIC_CACHE_ENTRIES = 200

_BUDGET_LUA_SCRIPT = """
local current = redis.call('GET', KEYS[1])
local budget = tonumber(ARGV[1])
local count = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
if current and tonumber(current) + count > budget then return 0 end
if not current and count > budget then return 0 end
redis.call('INCRBY', KEYS[1], count)
redis.call('EXPIRE', KEYS[1], ttl)
return 1
"""


def _try_redis_cache() -> Any:
    try:
        from backend.core.cache_manager import cache
        return cache
    except Exception:
        return None


def _reset_local_if_new_day() -> None:
    global _LOCAL_DAILY_TOKENS, _LOCAL_TOKEN_DATE
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _LOCAL_TOKEN_DATE != today:
        _LOCAL_DAILY_TOKENS = 0
        _LOCAL_TOKEN_DATE = today


# ---------------------------------------------------------------------------
# Budget helpers
# ---------------------------------------------------------------------------

def _deduct_tokens(count: int) -> bool:
    global _LOCAL_DAILY_TOKENS
    budget = int(os.getenv("AI_DAILY_TOKEN_BUDGET", "50000"))
    _reset_local_if_new_day()
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        try:
            from backend.core.cache_manager import cache
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = f"helix:ai:daily_tokens:{today}"
            client = cache._redis
            if client is None:
                raise RuntimeError("redis_unavailable")
            ok = client.eval(_BUDGET_LUA_SCRIPT, 1, key, budget, count, 86400)
            return bool(ok)
        except Exception:
            pass
    if _LOCAL_DAILY_TOKENS + count > budget:
        return False
    _LOCAL_DAILY_TOKENS += count
    return True


def _within_budget(count: int) -> bool:
    """Check if estimated tokens fit within daily budget (no deduction).

    Used by sentiment.py and osint.py as a pre-check before work begins.
    Local-only check; the real guard is *deduct_tokens* which handles Redis.
    """
    global _LOCAL_DAILY_TOKENS
    budget = int(os.getenv("AI_DAILY_TOKEN_BUDGET", "50000"))
    _reset_local_if_new_day()
    return _LOCAL_DAILY_TOKENS + count <= budget


def get_budget_status() -> dict[str, Any]:
    global _LOCAL_DAILY_TOKENS, _LOCAL_TOKEN_DATE
    budget = int(os.getenv("AI_DAILY_TOKEN_BUDGET", "50000"))
    _reset_local_if_new_day()
    redis_url = os.getenv("REDIS_URL", "").strip()
    used = _LOCAL_DAILY_TOKENS
    if redis_url:
        try:
            from backend.core.cache_manager import cache
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            client = cache._redis
            if client is not None:
                used = int(client.get(f"helix:ai:daily_tokens:{today}") or 0)
        except Exception:
            pass
    return {
        "daily_budget": budget,
        "tokens_used_today": used,
        "tokens_remaining": max(0, budget - used),
        "pct_used": round(used / budget * 100, 1) if budget > 0 else 0,
    }


def ai_mode() -> str:
    return os.getenv("AI_MODE", "ai_off").strip().lower()

# ---------------------------------------------------------------------------
# Cache helpers — exact-match (SHA-256), LRU, per-feature TTL
# ---------------------------------------------------------------------------


def _cache_get(key: str) -> dict[str, Any] | None:
    """Exact-match lookup with per-feature TTL and LRU promotion."""
    rc = _try_redis_cache()
    if rc:
        val = rc.get(_AI_REDIS_CACHE_PREFIX + key)
        if val:
            return val
    entry = _AI_CACHE.get(key)
    if not entry:
        return None
    ts, feature, payload = entry
    ttl = _FEATURE_CACHE_TTL.get(feature, _CACHE_TTL_SECONDS)
    if time.time() - ts > ttl:
        _AI_CACHE.pop(key, None)
        global _CACHE_EVICTIONS
        _CACHE_EVICTIONS += 1
        return None
    _AI_CACHE.move_to_end(key)
    return payload


def _cache_set(key: str, feature: str, prompt: str, payload: dict[str, Any]) -> None:
    """Store in exact-match cache with per-feature TTL and LRU eviction."""
    global _CACHE_EVICTIONS
    rc = _try_redis_cache()
    if rc:
        rc.set(_AI_REDIS_CACHE_PREFIX + key, payload, ttl=_CACHE_TTL_SECONDS)
    now = time.time()
    if key in _AI_CACHE:
        _AI_CACHE.move_to_end(key)
        _AI_CACHE[key] = (now, feature, payload)
    else:
        if len(_AI_CACHE) >= _MAX_CACHE_ENTRIES:
            _AI_CACHE.popitem(last=False)
            _CACHE_EVICTIONS += 1
        _AI_CACHE[key] = (now, feature, payload)
    if prompt:
        _semantic_cache_store(key, prompt)


def _prompt_hash(feature: str, context: dict[str, Any]) -> str:
    blob = json.dumps({"feature": feature, "context": context}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Semantic cache — character trigram Jaccard similarity
# ---------------------------------------------------------------------------


def _text_trigrams(text: str) -> set[tuple[str, str, str]]:
    """Character trigrams from lowercased, normalized text."""
    normalized = " ".join(text.lower().split())
    return {(normalized[i], normalized[i + 1], normalized[i + 2]) for i in range(len(normalized) - 2)}


def _trigram_similarity(a: str, b: str) -> float:
    """Jaccard similarity of character trigrams (0.0 – 1.0)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    ta = _text_trigrams(a)
    tb = _text_trigrams(b)
    intersection = len(ta & tb)
    union = len(ta | tb)
    return intersection / union if union else 0.0


def _semantic_cache_store(cache_key: str, prompt_text: str) -> None:
    """Store prompt text for future semantic matching."""
    if not _SEMANTIC_CACHE_ENABLED:
        return
    if cache_key in _SEMANTIC_CACHE:
        _SEMANTIC_CACHE.move_to_end(cache_key)
        _SEMANTIC_CACHE[cache_key] = prompt_text
    else:
        if len(_SEMANTIC_CACHE) >= _MAX_SEMANTIC_CACHE_ENTRIES:
            _SEMANTIC_CACHE.popitem(last=False)
        _SEMANTIC_CACHE[cache_key] = prompt_text


def _semantic_cache_lookup(cache_key: str, prompt_text: str) -> dict[str, Any] | None:
    """Return cached payload if a semantically similar prompt exists."""
    if not _SEMANTIC_CACHE_ENABLED or not prompt_text:
        return None
    best_sim = 0.0
    best_key: str | None = None
    for stored_key, stored_prompt in _SEMANTIC_CACHE.items():
        if stored_key == cache_key:
            continue
        sim = _trigram_similarity(prompt_text, stored_prompt)
        if sim > best_sim:
            best_sim = sim
            best_key = stored_key
    if best_sim >= _SEMANTIC_CACHE_THRESHOLD and best_key:
        entry = _AI_CACHE.get(best_key)
        if entry:
            ts, feat, payload = entry
            ttl = _FEATURE_CACHE_TTL.get(feat, _CACHE_TTL_SECONDS)
            if time.time() - ts <= ttl:
                return payload
    return None


def get_cache_stats() -> dict[str, Any]:
    """Return cache performance metrics for observability."""
    total = _CACHE_HITS + _CACHE_MISSES
    return {
        "hits": _CACHE_HITS,
        "misses": _CACHE_MISSES,
        "hit_rate": round(_CACHE_HITS / total * 100, 1) if total > 0 else 0.0,
        "tokens_saved": _CACHE_TOKENS_SAVED,
        "entries": len(_AI_CACHE),
        "max_entries": _MAX_CACHE_ENTRIES,
        "evictions": _CACHE_EVICTIONS,
        "semantic_entries": len(_SEMANTIC_CACHE) if _SEMANTIC_CACHE_ENABLED else 0,
        "semantic_enabled": _SEMANTIC_CACHE_ENABLED,
        "semantic_threshold": _SEMANTIC_CACHE_THRESHOLD,
        "default_ttl_seconds": _CACHE_TTL_SECONDS,
        "feature_ttl_overrides": dict(_FEATURE_CACHE_TTL),
    }


# ---------------------------------------------------------------------------
# Provider functions (one per service)
# ---------------------------------------------------------------------------

def _openrouter_lite(
    prompt: str, max_tokens: int, model: str | None = None, **kwargs
) -> dict[str, Any] | None:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None
    model = model or os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    return {"provider": "openrouter", "model": model, "text": text, "tokens": usage.get("total_tokens", 0)}


_OPENROUTER_FREE_MODEL = os.getenv("OPENROUTER_FREE_MODEL", "openrouter/free").strip()


def _ollama_cloud(prompt: str, max_tokens: int, system: str | None = None, model: str | None = None) -> dict[str, Any] | None:
    api_key = os.getenv("OLLAMA_API_KEY", "").strip()
    if not api_key:
        return None
    model = model or os.getenv("OLLAMA_CLOUD_MODEL", "ministral-3:8b-cloud")
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            "https://ollama.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens},
        )
        resp.raise_for_status()
        data = resp.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    return {"provider": "ollama_cloud", "model": model, "text": text, "tokens": usage.get("total_tokens", 0)}


def _groq(prompt: str, max_tokens: int, **kwargs) -> dict[str, Any] | None:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    return {"provider": "groq", "model": model, "text": text, "tokens": usage.get("total_tokens", 0)}


# ---------------------------------------------------------------------------
# Provider metadata — maps logical names to specs
# ---------------------------------------------------------------------------

PROVIDER_METADATA: dict[str, dict[str, Any]] = {
    "groq": {
        "label": "Groq",
        "default_model": "llama-3.1-8b-instant",
        "env_key": "GROQ_API_KEY",
        "cost_per_million": 0.05,
        "rate_limit_rpm": 30,
        "free_tier_calls": 0,
        "max_tokens": 8192,
        "models": ["llama-3.1-8b-instant"],
    },
    "ollama_cloud": {
        "label": "Ollama Cloud",
        "default_model": "ministral-3:8b-cloud",
        "fallback_model": "qwen-2.5-7b-cloud",
        "env_key": "OLLAMA_API_KEY",
        "cost_per_million": 0.15,
        "rate_limit_rpm": 60,
        "free_tier_calls": 0,
        "max_tokens": 4096,
        "models": ["ministral-3:8b-cloud", "qwen-2.5-7b-cloud"],
    },
    "openrouter_free": {
        "label": "OpenRouter Free",
        "default_model": "openrouter/free",
        "env_key": "OPENROUTER_API_KEY",
        "cost_per_million": 0.0,
        "rate_limit_rpm": 20,
        "free_tier_calls": 1000,
        "max_tokens": 4096,
        "models": ["openrouter/free"],
    },
    "openrouter_paid": {
        "label": "OpenRouter Paid",
        "default_model": "openai/gpt-4o-mini",
        "env_key": "OPENROUTER_API_KEY",
        "cost_per_million": 0.6,
        "rate_limit_rpm": 100,
        "free_tier_calls": 0,
        "max_tokens": 4096,
        "models": ["openai/gpt-4o-mini"],
    },
}

# Default priority order when no Settings override is present
_DEFAULT_PROVIDER_PRIORITY = ["groq", "ollama_cloud", "openrouter_free", "openrouter_paid"]
_DEFAULT_LITE_PRIORITY = ["openrouter_free", "ollama_cloud"]
_DEFAULT_PRIORITY_PRIORITY = ["openrouter_free", "ollama_cloud", "groq"]

# Map provider names to env var keys for API key presence check
_PROVIDER_ENV_KEYS: dict[str, str] = {
    "groq": "GROQ_API_KEY",
    "ollama_cloud": "OLLAMA_API_KEY",
    "openrouter_free": "OPENROUTER_API_KEY",
    "openrouter_paid": "OPENROUTER_API_KEY",
}

# In-memory rate-limit tracker: provider_name -> list of call timestamps
_PROVIDER_RATE_LIMITS: dict[str, list[float]] = {}
# Fallback tracking: how many times each provider was used as fallback
_PROVIDER_FALLBACK_COUNTS: dict[str, int] = {}


def _check_rate_limit(name: str, rpm: int) -> bool:
    """Return True if the provider is within its rate limit."""
    if rpm <= 0:
        return True
    now = time.time()
    window = 60.0
    timestamps = _PROVIDER_RATE_LIMITS.get(name, [])
    # Purge timestamps older than the window
    timestamps = [t for t in timestamps if now - t < window]
    _PROVIDER_RATE_LIMITS[name] = timestamps
    return len(timestamps) < rpm


def _record_call(name: str) -> None:
    """Record a successful call to a provider."""
    if name not in _PROVIDER_RATE_LIMITS:
        _PROVIDER_RATE_LIMITS[name] = []
    _PROVIDER_RATE_LIMITS[name].append(time.time())


def _record_fallback(name: str) -> None:
    """Increment fallback counter for a provider."""
    _PROVIDER_FALLBACK_COUNTS[name] = _PROVIDER_FALLBACK_COUNTS.get(name, 0) + 1


# ---------------------------------------------------------------------------
# Provider chain construction
# ---------------------------------------------------------------------------

def _get_provider_priority_list(db: Any = None) -> list[str]:
    """Read ordered provider priority list from Settings DB or fall back to env.

    When *db* is provided the function reads from the Settings table using
    ``providers.settings.get_setting``.  Otherwise it uses ``AI_MODE`` + env
    vars to produce a backward-compatible list.
    """
    mode = ai_mode()
    if mode == "ai_off":
        return []

    if db is not None:
        try:
            from providers.settings import get_setting
            raw = get_setting("ai_provider_priority", db)
            if raw:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(parsed, list) and parsed:
                    return parsed
        except Exception:
            pass

    return _env_based_priority(mode)


def _env_based_priority(mode: str) -> list[str]:
    """Build a priority list from env vars (backward-compat path)."""
    if mode == "ai_lite":
        return list(_DEFAULT_LITE_PRIORITY)
    return list(_DEFAULT_PROVIDER_PRIORITY)


def _build_provider_callable(name: str) -> Callable[..., dict[str, Any] | None] | None:
    """Return the appropriate provider function for *name*, or None if the
    required API key is not configured."""
    meta = PROVIDER_METADATA.get(name)
    if not meta:
        return None

    env_key = meta["env_key"]
    if not os.getenv(env_key, "").strip():
        return None

    if name == "groq":
        return _groq
    if name == "ollama_cloud":
        model = os.getenv("OLLAMA_CLOUD_MODEL", meta["default_model"])
        return partial(_ollama_cloud, model=model)
    if name == "openrouter_free":
        return partial(_openrouter_lite, model=_OPENROUTER_FREE_MODEL)
    if name == "openrouter_paid":
        model = os.getenv("OPENROUTER_MODEL", meta["default_model"])
        return partial(_openrouter_lite, model=model)

    return None


def get_ai_provider_chain(db: Any = None, mode: str | None = None) -> list[Callable[..., dict[str, Any] | None]]:
    """Build a dynamic provider chain from Settings metadata.

    Returns a list of callables ordered by priority.  Each callable accepts
    ``(prompt, max_tokens, system=None, **kwargs)`` and returns a result dict
    or ``None`` on failure.

    *db* — optional SQLAlchemy session for Settings lookups (falls back to env vars)
    *mode* — override AI mode (defaults to ``ai_mode()``)
    """
    mode = mode or ai_mode()
    if mode == "ai_off":
        return []

    priority = _get_provider_priority_list(db)
    chain: list[Callable[..., dict[str, Any] | None]] = []
    for name in priority:
        fn = _build_provider_callable(name)
        if fn is not None:
            fn._provider_name = name
            chain.append(fn)
    return chain


# ---------------------------------------------------------------------------
# Backward-compatible _providers_for_mode (delegates to new system)
# ---------------------------------------------------------------------------

def _providers_for_mode(mode: str, *, priority: bool = False) -> list:
    """Legacy provider list — retained for backward compatibility.

    Delegates to the new Settings-driven chain when *db* is available, or
    falls back to env-vars-only mode.
    """
    if mode == "ai_off":
        return []

    if priority and mode != "ai_lite":
        or_free = partial(_openrouter_lite, model=_OPENROUTER_FREE_MODEL)
        primary = os.getenv("OLLAMA_CLOUD_MODEL", "ministral-3:8b-cloud")
        fallback = os.getenv("OLLAMA_CLOUD_FALLBACK_MODEL", "qwen-2.5-7b-cloud")
        return [
            or_free,
            partial(_ollama_cloud, model=fallback),
            partial(_ollama_cloud, model=primary),
            _groq,
        ]

    return get_ai_provider_chain(mode=mode)


# ---------------------------------------------------------------------------
# Provider stats & observability
# ---------------------------------------------------------------------------

def get_provider_stats() -> dict[str, Any]:
    """Return per-provider usage statistics for observability.

    Includes call counts, fallback frequency, and current rate-limit state.
    """
    stats: dict[str, dict[str, Any]] = {}
    for name, meta in PROVIDER_METADATA.items():
        timestamps = _PROVIDER_RATE_LIMITS.get(name, [])
        now = time.time()
        recent = [t for t in timestamps if now - t < 60]
        stats[name] = {
            "label": meta["label"],
            "cost_per_million": meta["cost_per_million"],
            "rate_limit_rpm": meta["rate_limit_rpm"],
            "calls_last_minute": len(recent),
            "total_calls_today": len(timestamps),
            "fallback_count": _PROVIDER_FALLBACK_COUNTS.get(name, 0),
            "api_key_configured": bool(os.getenv(meta["env_key"], "").strip()),
        }
    return stats


# ---------------------------------------------------------------------------
# Feature prompts
# ---------------------------------------------------------------------------

_FEATURE_PROMPTS: dict[str, dict[str, Any]] = {
    "risk_explain": {
        "system": (
            "You are a stablecoin risk analyst. Plain text only — no markdown, no bold, no italics. "
            "Output 2-3 bullet points starting with '-'. Limit: ~80 words. Be concise and data-driven. "
            "CRITICAL: Use ONLY the data provided below. Do NOT use your internal training "
            "knowledge or fabricate numbers. If data doesn't support a claim, say so."
        ),
        "user": (
            "Asset: {asset_symbol}\n"
            "Risk Score: {signal_score}/100\n"
            "Band: {signal_band}\n"
            "Regime: {regime}\n"
            "Web Search Results:\n{web_search_results}\n"
            "Explain the key risk driver."
        ),
        "max_tokens_lite": 350,
        "max_tokens_full": 500,
    },
    "market_narrative": {
        "system": (
            "You are a crypto market analyst. Plain text only — no markdown, no bold, no italics. "
            "Output 3-4 bullet points starting with '-'. Limit: ~120 words. Cover: key driver, market context, what to watch. "
            "Be specific and data-driven. "
            "CRITICAL: Use ONLY the data provided below. Do NOT use your internal training "
            "knowledge or fabricate numbers. If data doesn't support a claim, say so."
        ),
        "user": (
            "Asset: {asset_symbol}\n"
            "Risk Score: {signal_score}/100\n"
            "Band: {signal_band}\n"
            "Regime: {regime}\n"
            "Depeg Probability (1h): {depeg_1h}%\n"
            "Depeg Probability (24h): {depeg_24h}%\n"
            "Sentiment: {sentiment_label} ({sentiment_score})\n"
            "Recent Events: {recent_events}\n"
            "Web Search Results:\n{web_search_results}\n"
            "Explain the current market narrative and what to watch."
        ),
        "max_tokens_lite": 500,
        "max_tokens_full": 700,
    },
    "anomaly_investigation": {
        "system": (
            "You are a stablecoin forensics analyst. Plain text only — no markdown, no bold, no italics. "
            "Output 2-3 bullet points starting with '-'. Cover: likely cause, market impact, recommended action. "
            "Be specific and data-driven. CRITICAL: Use ONLY the data provided below. Do NOT use your "
            "internal training knowledge or fabricate numbers. If data doesn't support a claim, say so."
        ),
        "user": (
            "Asset: {asset_symbol}\n"
            "Highest Z-Score: {z_score_max}\n"
            "Anomaly Metrics: {anomalies}\n"
            "Bridge Flow: {bridge_flow}\n"
            "Investigate the root cause and recommend action."
        ),
        "max_tokens_lite": 200,
        "max_tokens_full": 400,
    },
    "market_overview": {
        "system": (
            "You are a crypto market intelligence analyst. Plain text only — no markdown, no bold, no italics. "
            "Output 4-5 bullet points starting with '-'. Limit: ~180 words. Cover: overall market health, notable trends, "
            "risk concentrations, and assets to watch. Be specific and data-driven. "
            "CRITICAL: Use ONLY the data provided below. Do NOT use your internal training "
            "knowledge or fabricate numbers. If data doesn't support a claim, say so."
        ),
        "user": (
            "Tracked Assets ({asset_count}): {asset_list}\n"
            "Average Risk Score: {avg_signal_score}/100\n"
            "Band Distribution: {band_summary}\n"
            "Total Active Chains: {total_chains}\n"
            "24h Supply Changes: {supply_changes}\n"
            "Provide a market-wide intelligence overview covering overall stability, "
            "notable divergences, and assets requiring attention."
        ),
        "max_tokens_lite": 800,
        "max_tokens_full": 1200,
    },
    "insight_summary": {
        "system": (
            "You are a stablecoin intelligence analyst. Plain text only — no markdown, no bold, no italics. "
            "Output 3-4 bullet points starting with '-'. Limit: ~120 words. Cover: stability status, key trends, risk watch. "
            "Be specific and data-driven. "
            "CRITICAL: Use ONLY the data provided below. Do NOT use your internal training "
            "knowledge or fabricate numbers. If data doesn't support a claim, say so."
        ),
        "user": (
            "Asset: {asset_symbol}\n"
            "Risk Score: {signal_score}/100 (Band: {signal_band})\n"
            "Regime: {regime}\n"
            "Supply Change 24h: {supply_change_pct}%\n"
            "Chain Count: {chain_count}\n"
            "Top Chain Share: {top_chain_share}%\n"
            "Anomalies (7d): {anomaly_count}\n"
            "Web Search Results:\n{web_search_results}\n"
            "What are the most important trends and risks?"
        ),
        "max_tokens_lite": 500,
        "max_tokens_full": 700,
    },
}


def _build_prompt(feature: str, context: dict[str, Any]) -> tuple[str, str | None, int]:
    config = _FEATURE_PROMPTS.get(feature)
    if not config:
        config = {
            "system": "Plain text only — no markdown. Output 2-3 bullet points. Use ONLY the data provided.",
            "user": (
                "Feature:{feature}\n"
                "Asset:{asset_symbol}\n"
                "Score:{signal_score}\n"
                "Band:{signal_band}\n"
                "Regime:{regime}\n"
                "Web Search Results:\n{web_search_results}\n"
                "Reply in <=3 bullet points."
            ),
            "max_tokens_lite": 120,
            "max_tokens_full": 256,
        }
    template = config["user"]
    available = {k: v for k, v in context.items() if f"{{{k}}}" in template}
    for k in ("feature", "asset_symbol", "signal_score", "signal_band", "regime", "web_search_results"):
        available.setdefault(k, "?")
    if "feature" in template:
        available.setdefault("feature", feature)
    prompt = template.format(**available)
    mode = ai_mode()
    max_tokens = config["max_tokens_lite"] if mode == "ai_lite" else config["max_tokens_full"]
    return prompt, config["system"], max_tokens


# ---------------------------------------------------------------------------
# Cache settings sync from DB
# ---------------------------------------------------------------------------


def _read_cache_settings_from_db(db: Any) -> None:
    """Override cache globals from Settings DB when available."""
    global _SEMANTIC_CACHE_ENABLED, _SEMANTIC_CACHE_THRESHOLD, _MAX_CACHE_ENTRIES
    try:
        from providers.settings import get_setting
        val = get_setting("ai_cache_semantic_enabled", db)
        if val is not None:
            _SEMANTIC_CACHE_ENABLED = bool(val)
        val = get_setting("ai_cache_semantic_threshold", db)
        if val is not None:
            parsed = float(val) if isinstance(val, str) else float(val)
            _SEMANTIC_CACHE_THRESHOLD = max(0.5, min(1.0, parsed))
        val = get_setting("ai_cache_max_entries", db)
        if val is not None:
            _MAX_CACHE_ENTRIES = int(val)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main enrichment entry point
# ---------------------------------------------------------------------------

def enrich_with_ai(
    *,
    feature: str,
    context: dict[str, Any],
    priority: bool = False,
    db: Any = None,
) -> dict[str, Any]:
    """Generate AI text for *feature* using the dynamic provider chain.

    Parameters
    ----------
    feature : str
        One of the keys in ``_FEATURE_PROMPTS``.
    context : dict
        Template variables for prompt construction.
    priority : bool
        Legacy flag — when True uses a slightly different ordering
        (only relevant in env-var fallback mode).
    db : Session or None
        Optional DB session for reading provider priority from Settings.
        When ``None`` the function falls back to env vars.
    """
    mode = ai_mode()
    if mode == "ai_off":
        return {"available": False, "mode": mode, "reason": "AI disabled; core metrics unchanged."}

    global _CACHE_HITS, _CACHE_MISSES, _CACHE_TOKENS_SAVED

    if db is not None:
        _read_cache_settings_from_db(db)

    cache_key = _prompt_hash(feature, context)

    # 1. Exact-match cache
    cached = _cache_get(cache_key)
    if cached:
        _CACHE_HITS += 1
        _CACHE_TOKENS_SAVED += cached.get("tokens", 0)
        return {**cached, "cached": True}

    prompt, system, max_tokens = _build_prompt(feature, context)

    # 2. Semantic cache (trigram similarity)
    cached = _semantic_cache_lookup(cache_key, prompt)
    if cached:
        _CACHE_HITS += 1
        _CACHE_TOKENS_SAVED += cached.get("tokens", 0)
        return {**cached, "cached": True}

    _CACHE_MISSES += 1
    system_len = len(system.split()) if system else 0
    estimated_tokens = max_tokens + int((len(prompt.split()) + system_len) * 1.3)
    errors: list[str] = []

    if db is not None:
        provider_chain = get_ai_provider_chain(db=db)
    else:
        provider_chain = _providers_for_mode(mode, priority=priority)

    preferred_provider: str | None = None

    for provider_fn in provider_chain:
        pname = getattr(provider_fn, "_provider_name",
                        getattr(provider_fn, "func", provider_fn).__name__)

        try:
            # Rate-limit guard
            meta = PROVIDER_METADATA.get(pname)
            rpm = meta["rate_limit_rpm"] if meta else 0
            if not _check_rate_limit(pname, rpm):
                _record_fallback(pname)
                errors.append(f"{pname}:rate_limited")
                continue

            if not _deduct_tokens(estimated_tokens):
                return {"available": False, "mode": mode, "reason": "daily_token_budget_exceeded"}

            result = provider_fn(prompt, max_tokens, system=system)
            if result is None:
                _record_fallback(pname)
                errors.append(f"{pname}:no_api_key")
                continue

            _record_call(pname)

            if preferred_provider and pname != preferred_provider:
                _record_fallback(pname)

            tokens_returned = int(result.get("tokens") or 0) or max_tokens
            now_dt = datetime.now(timezone.utc)
            payload = {
                "available": True,
                "mode": mode,
                "feature": feature,
                "provider": result["provider"],
                "model": result["model"],
                "summary": result["text"].strip().replace("**", ""),
                "tokens": tokens_returned,
                "cached": False,
                "generated_at": now_dt.isoformat(),
                "expires_at": datetime.fromtimestamp(now_dt.timestamp() + _CACHE_TTL_SECONDS, tz=timezone.utc).isoformat(),
            }
            _cache_set(cache_key, feature, prompt, payload)
            return payload
        except Exception as exc:
            _record_fallback(pname)
            errors.append(f"{pname}:{exc}")

    return {"available": False, "mode": mode, "reason": "all_providers_failed", "errors": errors}
