"""Optional LLM router — add-on only; core platform must run with AI_MODE=ai_off."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from functools import partial
from typing import Any

import httpx

_AI_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = int(os.getenv("AI_CACHE_TTL_SECONDS", "3600"))
_LOCAL_DAILY_TOKENS = 0
_LOCAL_TOKEN_DATE = ""
_AI_REDIS_CACHE_PREFIX = "helix:ai:cache:"

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


def _cache_get(key: str) -> dict[str, Any] | None:
    rc = _try_redis_cache()
    if rc:
        val = rc.get(_AI_REDIS_CACHE_PREFIX + key)
        if val:
            return val
    entry = _AI_CACHE.get(key)
    if not entry:
        return None
    ts, payload = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _AI_CACHE.pop(key, None)
        return None
    return payload


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    rc = _try_redis_cache()
    if rc:
        rc.set(_AI_REDIS_CACHE_PREFIX + key, payload, ttl=_CACHE_TTL_SECONDS)
    _AI_CACHE[key] = (time.time(), payload)


def _prompt_hash(feature: str, context: dict[str, Any]) -> str:
    blob = json.dumps({"feature": feature, "context": context}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


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


def _providers_for_mode(mode: str, *, priority: bool = False) -> list:
    if mode == "ai_off":
        return []
    or_free = partial(_openrouter_lite, model=_OPENROUTER_FREE_MODEL)
    primary = os.getenv("OLLAMA_CLOUD_MODEL", "ministral-3:8b-cloud")
    fallback = os.getenv("OLLAMA_CLOUD_FALLBACK_MODEL", "qwen-2.5-7b-cloud")
    if mode == "ai_lite":
        return [
            or_free,
            partial(_ollama_cloud, model=primary),
        ]
    if priority:
        return [
            or_free,
            partial(_ollama_cloud, model=fallback),
            partial(_ollama_cloud, model=primary),
            _groq,
        ]
    return [
        or_free,
        partial(_ollama_cloud, model=primary),
        partial(_ollama_cloud, model=fallback),
        _groq,
    ]


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
    for k in ("asset_symbol", "signal_score", "signal_band", "regime", "web_search_results"):
        available.setdefault(k, "?")
    prompt = template.format(**available)
    mode = ai_mode()
    max_tokens = config["max_tokens_lite"] if mode == "ai_lite" else config["max_tokens_full"]
    return prompt, config["system"], max_tokens


def enrich_with_ai(*, feature: str, context: dict[str, Any], priority: bool = False) -> dict[str, Any]:
    mode = ai_mode()
    if mode == "ai_off":
        return {"available": False, "mode": mode, "reason": "AI disabled; core metrics unchanged."}

    cache_key = _prompt_hash(feature, context)
    cached = _cache_get(cache_key)
    if cached:
        return {**cached, "cached": True}

    prompt, system, max_tokens = _build_prompt(feature, context)
    system_len = len(system.split()) if system else 0
    estimated_tokens = max_tokens + int((len(prompt.split()) + system_len) * 1.3)
    errors: list[str] = []

    for provider_fn in _providers_for_mode(mode, priority=priority):
        try:
            if not _deduct_tokens(estimated_tokens):
                return {"available": False, "mode": mode, "reason": "daily_token_budget_exceeded"}
            result = provider_fn(prompt, max_tokens, system=system)
            if result is None:
                continue
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
            _cache_set(cache_key, payload)
            return payload
        except Exception as exc:
            errors.append(f"{provider_fn.__name__}:{exc}")

    return {"available": False, "mode": mode, "reason": "all_providers_failed", "errors": errors}
