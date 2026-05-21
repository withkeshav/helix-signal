"""Optional LLM router — add-on only; core platform must run with AI_MODE=ai_off."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

_AI_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 3600
_LOCAL_DAILY_TOKENS = 0


def ai_mode() -> str:
    return os.getenv("AI_MODE", "ai_off").strip().lower()


def _cache_get(key: str) -> dict[str, Any] | None:
    entry = _AI_CACHE.get(key)
    if not entry:
        return None
    ts, payload = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _AI_CACHE.pop(key, None)
        return None
    return payload


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    _AI_CACHE[key] = (time.time(), payload)


def _prompt_hash(feature: str, context: dict[str, Any]) -> str:
    blob = json.dumps({"feature": feature, "context": context}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _openrouter_lite(prompt: str, max_tokens: int) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
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


def _ollama_cloud(prompt: str, max_tokens: int) -> dict[str, Any]:
    base = os.getenv("OLLAMA_CLOUD_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise RuntimeError("OLLAMA_CLOUD_BASE_URL not set")
    model = os.getenv("OLLAMA_CLOUD_MODEL", "llama3.2:3b")
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{base}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "options": {"num_predict": max_tokens}},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"provider": "ollama_cloud", "model": model, "text": data.get("response", ""), "tokens": 0}


def _groq(prompt: str, max_tokens: int) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set")
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
    if mode == "ai_lite":
        return [_openrouter_lite, _ollama_cloud]
    if priority:
        return [_groq, _ollama_cloud, _openrouter_lite]
    return [_openrouter_lite, _ollama_cloud, _groq]


def _within_budget(additional_tokens: int) -> bool:
    global _LOCAL_DAILY_TOKENS
    budget = int(os.getenv("AI_DAILY_TOKEN_BUDGET", "50000"))
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        try:
            from services.cache import _client

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = f"helix:ai:daily_tokens:{today}"
            client = _client()
            current = client.get(key)
            current_count = int(current) if current else 0
            if current_count + additional_tokens > budget:
                return False
            pipe = client.pipeline()
            pipe.incrby(key, additional_tokens)
            pipe.expire(key, 86400)
            pipe.execute()
            return True
        except Exception:
            pass
    if _LOCAL_DAILY_TOKENS + additional_tokens > budget:
        return False
    _LOCAL_DAILY_TOKENS += additional_tokens
    return True


def enrich_with_ai(*, feature: str, context: dict[str, Any], priority: bool = False) -> dict[str, Any]:
    mode = ai_mode()
    if mode == "ai_off":
        return {"available": False, "mode": mode, "reason": "AI disabled; core metrics unchanged."}

    cache_key = _prompt_hash(feature, context)
    cached = _cache_get(cache_key)
    if cached:
        return {**cached, "cached": True}

    prompt = (
        f"Feature:{feature}\n"
        f"Asset:{context.get('asset_symbol', '?')}\n"
        f"Score:{context.get('signal_score')}\n"
        f"Band:{context.get('signal_band')}\n"
        f"Regime:{context.get('regime')}\n"
        "Reply in <=3 sentences. Risk ops tone."
    )
    max_tokens = 120 if mode == "ai_lite" else 256
    errors: list[str] = []

    for provider_fn in _providers_for_mode(mode, priority=priority):
        try:
            result = provider_fn(prompt, max_tokens)
            tokens_returned = int(result.get("tokens") or 0)
            if not _within_budget(tokens_returned):
                return {"available": False, "mode": mode, "reason": "daily_token_budget_exceeded"}
            payload = {
                "available": True,
                "mode": mode,
                "feature": feature,
                "provider": result["provider"],
                "model": result["model"],
                "summary": result["text"].strip(),
                "tokens": tokens_returned,
                "cached": False,
            }
            _cache_set(cache_key, payload)
            return payload
        except Exception as exc:
            errors.append(f"{provider_fn.__name__}:{exc}")

    return {"available": False, "mode": mode, "reason": "all_providers_failed", "errors": errors}
