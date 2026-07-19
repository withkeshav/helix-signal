"""Optional LLM router — add-on only; core platform must run with AI_MODE=ai_off.

Per-feature provider:model_id routing via Settings. Supported providers:
Ollama Cloud and OpenRouter only. Usage tracked via AiUsage; no token budget enforcement.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from datetime import datetime, timezone
from functools import partial
from typing import Any

import httpx
from structlog import get_logger

import services.components.ai.cache as _cache_mod
from services.ai_usage import increment_ai_usage
from services.components.ai.cache import (
    _AI_CACHE,
    _CACHE_TTL_SECONDS,
    _FEATURE_CACHE_TTL,
    cache_get_enhanced,
    cache_set_enhanced,
)
from services.components.ai.providers import openrouter_lite as _openrouter_call

_openrouter_lite = _openrouter_call  # back-compat alias for tests

log = get_logger(__name__)

_CACHE_HITS = 0
_CACHE_MISSES = 0
_CACHE_TOKENS_SAVED = 0
_MAX_CACHE_ENTRIES = int(os.getenv("AI_CACHE_MAX_ENTRIES", "1000"))

_PROVIDER_RATE_LIMITS: dict[str, list[float]] = {}
_PROVIDER_FALLBACK_COUNTS: dict[str, int] = {}

VALID_PROVIDERS = frozenset({"ollama_cloud", "openrouter"})

PROVIDER_METADATA: dict[str, dict[str, Any]] = {
    "ollama_cloud": {
        "label": "Ollama Cloud",
        "env_key": "OLLAMA_API_KEY",
        "secret_setting": "secret_ollama_api_key",
        "cost_per_million": 0.15,
        "rate_limit_rpm": 60,
    },
    "openrouter": {
        "label": "OpenRouter",
        "env_key": "OPENROUTER_API_KEY",
        "secret_setting": "secret_openrouter_api_key",
        "cost_per_million": 0.6,
        "rate_limit_rpm": 100,
    },
}


def _parse_provider_model(value: str | None) -> tuple[str, str] | None:
    """Parse ``provider:model_id`` (model_id may contain additional colons)."""
    if not value or not str(value).strip():
        return None
    s = str(value).strip()
    if ":" not in s:
        return None
    provider, _, model_id = s.partition(":")
    provider = provider.strip()
    model_id = model_id.strip()
    if provider not in VALID_PROVIDERS or not model_id:
        return None
    return provider, model_id


def _ollama_cloud(
    prompt: str,
    max_tokens: int,
    system: str | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    api_key = kwargs.get("_resolved_api_key", "").strip()
    if not api_key or not model:
        return None
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
    return {
        "provider": "ollama_cloud",
        "model": model,
        "text": text,
        "tokens": usage.get("total_tokens", 0),
    }


def _cache_get(key: str, feature: str | None = None) -> dict[str, Any] | None:
    return cache_get_enhanced(key, feature)


def _cache_set(key: str, feature: str, prompt: str, payload: dict[str, Any]) -> None:
    cache_set_enhanced(key, feature, prompt, payload)


def _semantic_cache_lookup(cache_key: str, prompt_text: str, feature: str | None = None) -> dict[str, Any] | None:
    """Return cached payload if a semantically similar prompt exists."""
    if not _cache_mod._SEMANTIC_CACHE_ENABLED or not prompt_text:
        return None
    threshold = _cache_mod._SEMANTIC_CACHE_THRESHOLD
    best_sim = 0.0
    best_payload: dict[str, Any] | None = None
    now = time.time()
    for _sem_key, entry in _cache_mod._AI_SEMANTIC_CACHE.items():
        expiry, entry_feature, stored_prompt, payload, _exact_key = entry
        if now > expiry:
            continue
        if feature and entry_feature != feature:
            continue
        sim = _trigram_similarity(prompt_text, stored_prompt)
        if sim > best_sim and sim >= threshold:
            best_sim = sim
            best_payload = payload
    return best_payload


def _prompt_hash(feature: str, context: dict[str, Any]) -> str:
    blob = json.dumps({"feature": feature, "context": context}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _text_trigrams(text: str) -> set[tuple[str, str, str]]:
    normalized = " ".join(text.lower().split())
    if len(normalized) < 3:
        return set()
    return {(normalized[i], normalized[i + 1], normalized[i + 2]) for i in range(len(normalized) - 2)}


def _trigram_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    ta = _text_trigrams(a)
    tb = _text_trigrams(b)
    intersection = len(ta & tb)
    union = len(ta | tb)
    return intersection / union if union else 0.0


def ai_mode(db: Any = None) -> str:
    if db is not None:
        from providers.settings import get_setting

        mode = get_setting("ai_mode", db)
        if mode:
            return str(mode)
    mode = os.getenv("AI_MODE", "").strip()
    return mode or "ai_off"


def get_cache_stats() -> dict[str, Any]:
    total = _CACHE_HITS + _CACHE_MISSES
    return {
        "hits": _CACHE_HITS,
        "misses": _CACHE_MISSES,
        "hit_rate": round(_CACHE_HITS / total * 100, 1) if total > 0 else 0.0,
        "tokens_saved": _CACHE_TOKENS_SAVED,
        "entries": len(_AI_CACHE),
        "max_entries": _MAX_CACHE_ENTRIES,
        "evictions": _cache_mod._CACHE_EVICTIONS,
        "semantic_entries": len(_cache_mod._AI_SEMANTIC_CACHE) if _cache_mod._SEMANTIC_CACHE_ENABLED else 0,
        "semantic_enabled": _cache_mod._SEMANTIC_CACHE_ENABLED,
        "semantic_threshold": _cache_mod._SEMANTIC_CACHE_THRESHOLD,
        "default_ttl_seconds": _CACHE_TTL_SECONDS,
        "feature_ttl_overrides": dict(_FEATURE_CACHE_TTL),
    }


def _resolve_api_key(provider: str, db: Any = None) -> str:
    meta = PROVIDER_METADATA.get(provider, {})
    if db is not None:
        try:
            from providers.settings import get_setting

            secret_key = meta.get("secret_setting", "")
            if secret_key:
                val = get_setting(secret_key, db)
                if val:
                    return str(val).strip()
        except Exception:
            log.warning("Failed to resolve API key from settings", exc_info=True)
    env_key = meta.get("env_key", "")
    return os.getenv(env_key, "").strip() if env_key else ""


def _build_provider_callable(
    provider: str,
    model_id: str,
    db: Any = None,
) -> Callable[..., dict[str, Any] | None] | None:
    if provider not in VALID_PROVIDERS or not model_id:
        return None
    api_key = _resolve_api_key(provider, db)
    if not api_key:
        return None
    if provider == "ollama_cloud":
        return partial(_ollama_cloud, model=model_id, _resolved_api_key=api_key)
    return partial(_openrouter_call, model=model_id, _resolved_api_key=api_key)


def _feature_model_setting(feature: str | None) -> str | None:
    if not feature:
        return None
    return f"ai_model_{feature}"


def get_ai_provider_chain(
    db: Any = None,
    mode: str | None = None,
    feature: str | None = None,
) -> list[Callable[..., dict[str, Any] | None]]:
    """Build [primary, fallback] provider callables from per-feature settings."""
    mode = mode or ai_mode(db)
    if mode == "ai_off":
        return []

    chain: list[Callable[..., dict[str, Any] | None]] = []
    seen: set[str] = set()

    if db is not None and feature:
        from providers.settings import get_setting

        setting_key = _feature_model_setting(feature)
        primary = _parse_provider_model(get_setting(setting_key, db) if setting_key else None)
        if primary:
            fn = _build_provider_callable(primary[0], primary[1], db)
            if fn is not None:
                fn._provider_name = primary[0]  # type: ignore[attr-defined]
                chain.append(fn)
                seen.add(primary[0])

        fallback_provider = str(get_setting("ai_fallback_provider", db) or "openrouter").strip()
        fallback_model = str(get_setting("ai_fallback_model", db) or "").strip()
        if fallback_provider in VALID_PROVIDERS and fallback_model:
            if fallback_provider not in seen:
                fn = _build_provider_callable(fallback_provider, fallback_model, db)
                if fn is not None:
                    fn._provider_name = fallback_provider  # type: ignore[attr-defined]
                    chain.append(fn)

    return chain


def _providers_for_mode(mode: str, *, priority: bool = False, feature: str | None = None) -> list:
    """Legacy env-only path — delegates to get_ai_provider_chain when db unavailable."""
    if mode == "ai_off":
        return []
    return get_ai_provider_chain(mode=mode, feature=feature)


def _check_rate_limit(name: str, rpm: int) -> bool:
    if rpm <= 0:
        return True
    now = time.time()
    timestamps = [t for t in _PROVIDER_RATE_LIMITS.get(name, []) if now - t < 60.0]
    _PROVIDER_RATE_LIMITS[name] = timestamps
    return len(timestamps) < rpm


def _record_call(name: str) -> None:
    _PROVIDER_RATE_LIMITS.setdefault(name, []).append(time.time())


def _record_fallback(name: str) -> None:
    _PROVIDER_FALLBACK_COUNTS[name] = _PROVIDER_FALLBACK_COUNTS.get(name, 0) + 1


def get_provider_stats(db: Any = None) -> dict[str, Any]:
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
            "api_key_configured": bool(_resolve_api_key(name, db)),
        }
    return stats


_FEATURE_TOGGLE_KEYS: dict[str, str] = {
    "risk_explain": "feature_ai_explain",
    "market_overview": "feature_ai_summary",
    "market_narrative": "feature_ai_narrative",
    "insight_summary": "feature_ai_insights",
}


def _setting_bool(val: Any, default: bool = True) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _feature_enabled(feature: str, db: Any) -> bool:
    key = _FEATURE_TOGGLE_KEYS.get(feature)
    if not key:
        return True
    if db is None:
        return True
    from providers.settings import get_setting

    return _setting_bool(get_setting(key, db), default=True)


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
            "What are the most important trends and risks?"
        ),
        "max_tokens_lite": 500,
        "max_tokens_full": 700,
    },
}


def _build_prompt(feature: str, context: dict[str, Any], db: Any = None) -> tuple[str, str | None, int]:
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
                "Reply in <=3 bullet points."
            ),
            "max_tokens_lite": 120,
            "max_tokens_full": 256,
        }
    template = config["user"]
    system = config["system"]
    if db is not None:
        try:
            from providers.settings import get_setting

            custom_user = get_setting(f"ai_prompt_{feature}_user", db)
            custom_sys = get_setting(f"ai_prompt_{feature}_system", db)
            if custom_user and str(custom_user).strip():
                template = str(custom_user)
            if custom_sys and str(custom_sys).strip():
                system = str(custom_sys)
        except Exception:
            log.warning("Failed to load custom prompt from settings", exc_info=True)
    available = {k: v for k, v in context.items() if f"{{{k}}}" in template}
    for k in (
        "feature", "asset_symbol", "signal_score", "signal_band", "regime",
        "depeg_1h", "depeg_24h", "sentiment_label", "sentiment_score", "recent_events",
        "z_score_max", "anomalies", "bridge_flow", "asset_count", "asset_list",
        "avg_signal_score", "band_summary", "total_chains", "supply_changes",
        "supply_change_pct", "chain_count", "top_chain_share", "anomaly_count",
    ):
        available.setdefault(k, "?")
    if "feature" in template:
        available.setdefault("feature", feature)
    prompt = template.format(**available)
    mode = ai_mode(db)
    max_tokens = config["max_tokens_lite"] if mode == "ai_lite" else config["max_tokens_full"]
    return prompt, system, max_tokens


def _read_cache_settings_from_db(db: Any) -> None:
    try:
        from providers.settings import get_setting

        val = get_setting("ai_cache_semantic_enabled", db)
        if val is not None:
            _cache_mod._SEMANTIC_CACHE_ENABLED = bool(val)
        val = get_setting("ai_cache_semantic_threshold", db)
        if val is not None:
            parsed = float(val) if isinstance(val, str) else float(val)
            _cache_mod._SEMANTIC_CACHE_THRESHOLD = max(0.5, min(1.0, parsed))
        val = get_setting("ai_cache_max_entries", db)
        if val is not None:
            _cache_mod._MAX_CACHE_ENTRIES = int(val)
        val = get_setting("ai_cache_max_semantic_entries", db)
        if val is not None:
            _cache_mod._MAX_SEMANTIC_CACHE_ENTRIES = int(val)
    except Exception:
        log.warning("Failed to load cache configuration from settings", exc_info=True)


def enrich_with_ai(
    *,
    feature: str,
    context: dict[str, Any],
    priority: bool = False,
    db: Any = None,
) -> dict[str, Any]:
    mode = ai_mode(db)
    if mode == "ai_off":
        return {"available": False, "mode": mode, "reason": "AI disabled; core metrics unchanged."}

    if not _feature_enabled(feature, db):
        return {
            "available": False,
            "mode": mode,
            "reason": f"Feature '{feature}' is disabled in Settings.",
        }

    global _CACHE_HITS, _CACHE_MISSES, _CACHE_TOKENS_SAVED

    if db is not None:
        _read_cache_settings_from_db(db)

    cache_key = _prompt_hash(feature, context)

    cached = _cache_get(cache_key, feature)
    if cached:
        _CACHE_HITS += 1
        _CACHE_TOKENS_SAVED += cached.get("tokens", 0)
        return {**cached, "cached": True}

    prompt, system, max_tokens = _build_prompt(feature, context, db)

    cached = _semantic_cache_lookup(cache_key, prompt, feature)
    if cached:
        _CACHE_HITS += 1
        _CACHE_TOKENS_SAVED += cached.get("tokens", 0)
        return {**cached, "cached": True}

    _CACHE_MISSES += 1
    errors: list[str] = []

    if db is not None:
        provider_chain = get_ai_provider_chain(db=db, feature=feature)
    else:
        provider_chain = _providers_for_mode(mode, priority=priority, feature=feature)

    if not provider_chain:
        setting_key = _feature_model_setting(feature)
        if db is not None and setting_key:
            from providers.settings import get_setting

            raw = get_setting(setting_key, db)
            if not _parse_provider_model(raw):
                return {"available": False, "mode": mode, "reason": "model_not_configured"}
        return {"available": False, "mode": mode, "reason": "no_providers_configured", "errors": errors}

    preferred_provider: str | None = getattr(provider_chain[0], "_provider_name", None)

    for provider_fn in provider_chain:
        pname = getattr(provider_fn, "_provider_name", "unknown")
        t0 = time.perf_counter()

        try:
            meta = PROVIDER_METADATA.get(pname, {})
            rpm = meta.get("rate_limit_rpm", 0)
            if not _check_rate_limit(pname, rpm):
                _record_fallback(pname)
                errors.append(f"{pname}:rate_limited")
                continue

            result = provider_fn(prompt, max_tokens, system=system)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            if result is None:
                _record_fallback(pname)
                errors.append(f"{pname}:no_api_key")
                log.warning("ai.provider_failed", provider=pname, feature=feature, reason="no_api_key", latency_ms=latency_ms)
                continue

            _record_call(pname)
            log.info(
                "ai.provider_success",
                provider=pname,
                model=result.get("model"),
                feature=feature,
                latency_ms=latency_ms,
                tokens=result.get("tokens"),
            )

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
                "expires_at": datetime.fromtimestamp(
                    now_dt.timestamp() + _CACHE_TTL_SECONDS, tz=timezone.utc
                ).isoformat(),
            }
            _cache_set(cache_key, feature, prompt, payload)
            if db is not None:
                cpm = meta.get("cost_per_million", 0)
                cost = (tokens_returned / 1_000_000) * cpm
                increment_ai_usage(
                    db=db,
                    provider=result.get("provider", pname),
                    model=result.get("model", ""),
                    tokens=tokens_returned,
                    cost=cost,
                )
            return payload
        except Exception as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            _record_fallback(pname)
            errors.append(f"{pname}:{exc}")
            log.warning(
                "ai.provider_error",
                provider=pname,
                feature=feature,
                latency_ms=latency_ms,
                exc_info=True,
            )

    return {"available": False, "mode": mode, "reason": "all_providers_failed", "errors": errors}
