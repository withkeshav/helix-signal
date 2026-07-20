"""Optional LLM router — add-on only; core platform must run with AI_MODE=ai_off.

Per-feature provider:model_id routing via Settings and ai_providers registry.
Three-tier fallback: task primary → task fallback (ai_fallback_*) → global default
(ai_default_fallback_*). Usage tracked via AiUsage; no token budget enforcement.
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
from services.llm_client import chat_completion, get_enabled_provider, seed_default_providers

log = get_logger(__name__)

_CACHE_HITS = 0
_CACHE_MISSES = 0
_CACHE_TOKENS_SAVED = 0
_MAX_CACHE_ENTRIES = int(os.getenv("AI_CACHE_MAX_ENTRIES", "1000"))

_PROVIDER_RATE_LIMITS: dict[str, list[float]] = {}
_PROVIDER_FALLBACK_COUNTS: dict[str, int] = {}

# Legacy metadata for rate limits / cost estimates on built-in provider ids.
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

VALID_PROVIDERS = frozenset(PROVIDER_METADATA.keys())


def _parse_provider_model(value: str | None) -> tuple[str, str] | None:
    """Parse ``provider_id:model_id`` (model_id may contain additional colons)."""
    if not value or not str(value).strip():
        return None
    s = str(value).strip()
    if ":" not in s:
        return None
    provider, _, model_id = s.partition(":")
    provider = provider.strip()
    model_id = model_id.strip()
    if not provider or not model_id:
        return None
    return provider, model_id


def _provider_chat(
    db: Any,
    provider_id: str,
    model_id: str,
    prompt: str,
    max_tokens: int,
    system: str | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return chat_completion(db, provider_id, model_id, messages, max_tokens=max_tokens)


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
            from providers.settings import get_secret

            secret_key = meta.get("secret_setting", "")
            if secret_key:
                val = get_secret(secret_key, db)
                if val:
                    return str(val).strip()
        except Exception:
            log.warning("Failed to resolve API key from settings", exc_info=True)
    env_key = meta.get("env_key", "")
    return os.getenv(env_key, "").strip() if env_key else ""


def _feature_model_setting(feature: str | None) -> str | None:
    if not feature:
        return None
    return f"ai_model_{feature}"


def _resolve_chain_entries(db: Any, feature: str | None) -> list[tuple[str, str, str]]:
    """Return ordered (tier, provider_id, model_id) triples for the 3-tier fallback chain."""
    from providers.settings import get_setting

    entries: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(tier: str, provider_id: str, model_id: str) -> None:
        provider_id = provider_id.strip()
        model_id = model_id.strip()
        if not provider_id or not model_id:
            return
        key = (provider_id, model_id)
        if key in seen:
            return
        entries.append((tier, provider_id, model_id))
        seen.add(key)

    if feature:
        setting_key = _feature_model_setting(feature)
        primary = _parse_provider_model(get_setting(setting_key, db) if setting_key else None)
        if primary:
            _add("primary", primary[0], primary[1])

    task_fb_provider = str(get_setting("ai_fallback_provider", db) or "").strip()
    task_fb_model = str(get_setting("ai_fallback_model", db) or "").strip()
    if task_fb_provider and task_fb_model:
        _add("task_fallback", task_fb_provider, task_fb_model)

    global_provider = str(get_setting("ai_default_fallback_provider", db) or "").strip()
    global_model = str(get_setting("ai_default_fallback_model_id", db) or "").strip()
    if global_provider and global_model:
        _add("global_fallback", global_provider, global_model)

    return entries


def _build_provider_callable(
    tier: str,
    provider_id: str,
    model_id: str,
    db: Any = None,
) -> Callable[..., dict[str, Any] | None] | None:
    if db is None or not provider_id or not model_id:
        return None
    if get_enabled_provider(db, provider_id) is None:
        return None
    fn = partial(_provider_chat, db, provider_id, model_id)
    fn._provider_name = provider_id  # type: ignore[attr-defined]
    fn._tier = tier  # type: ignore[attr-defined]
    fn._model_id = model_id  # type: ignore[attr-defined]
    return fn


def get_ai_provider_chain(
    db: Any = None,
    mode: str | None = None,
    feature: str | None = None,
) -> list[Callable[..., dict[str, Any] | None]]:
    """Build [primary, task_fallback, global_fallback] callables from settings + registry."""
    mode = mode or ai_mode(db)
    if mode == "ai_off":
        return []

    if db is not None:
        seed_default_providers(db)

    chain: list[Callable[..., dict[str, Any] | None]] = []
    if db is None:
        return chain

    for tier, provider_id, model_id in _resolve_chain_entries(db, feature):
        fn = _build_provider_callable(tier, provider_id, model_id, db)
        if fn is not None:
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
    provider_ids = set(PROVIDER_METADATA.keys())
    if db is not None:
        from sqlalchemy import select
        from database import AiProvider

        rows = db.execute(select(AiProvider.id)).scalars().all()
        provider_ids.update(rows)

    for name in provider_ids:
        meta = PROVIDER_METADATA.get(name, {})
        timestamps = _PROVIDER_RATE_LIMITS.get(name, [])
        now = time.time()
        recent = [t for t in timestamps if now - t < 60]
        configured = bool(_resolve_api_key(name, db))
        if db is not None and not configured:
            configured = get_enabled_provider(db, name) is not None
        stats[name] = {
            "label": meta.get("label", name),
            "cost_per_million": meta.get("cost_per_million", 0),
            "rate_limit_rpm": meta.get("rate_limit_rpm", 0),
            "calls_last_minute": len(recent),
            "total_calls_today": len(timestamps),
            "fallback_count": _PROVIDER_FALLBACK_COUNTS.get(name, 0),
            "api_key_configured": configured,
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


# Structured plain-text contract for UI parsing (lines starting with "- ").
_AI_OUTPUT_RULES = (
    "Plain text only — no markdown headings, no bold (**), no code fences. "
    "Each bullet must start with '- ' (hyphen + space). "
    "Use ONLY numbers and facts from the DATA block. Never invent prices, scores, or events. "
    "If a field is missing or '?', say 'data unavailable' — do not guess. "
    "Stay within the word limit so the full answer fits the dashboard card."
)

_FEATURE_PROMPTS: dict[str, dict[str, Any]] = {
    "risk_explain": {
        "system": (
            f"You are a stablecoin risk analyst. {_AI_OUTPUT_RULES} "
            "Return exactly this structure:\n"
            "STATUS: <one line: Normal|Watch|Risk and why, ≤20 words>\n"
            "- <primary driver with score/band numbers>\n"
            "- <secondary driver or mitigating factor>\n"
            "- <one watch item>\n"
            "Word budget: ~90 words total."
        ),
        "user": (
            "DATA for {asset_symbol}:\n"
            "Risk Score: {signal_score}/100 | Band: {signal_band} | Regime: {regime}\n"
            "Peg: {peg_price} | Supply Δ24h: {supply_change_pct}% | Top chain: {top_chain_share}%\n"
            "DEWS: {dews_score} ({dews_band}) | Anomalies: {anomaly_count}\n"
            "Write the STATUS line and 2-3 bullets."
        ),
        "max_tokens_lite": 400,
        "max_tokens_full": 550,
    },
    "market_narrative": {
        "system": (
            f"You are a crypto market analyst for stablecoins. {_AI_OUTPUT_RULES} "
            "Return:\n"
            "STATUS: <one line market posture>\n"
            "- <key driver>\n"
            "- <context from sentiment/events if present>\n"
            "- <what to watch next 24h>\n"
            "Word budget: ~120 words."
        ),
        "user": (
            "DATA for {asset_symbol}:\n"
            "Risk {signal_score}/100 ({signal_band}) | Regime: {regime}\n"
            "Depeg 1h: {depeg_1h}% | Depeg 24h: {depeg_24h}%\n"
            "Sentiment: {sentiment_label} ({sentiment_score})\n"
            "Recent events: {recent_events}\n"
            "Write STATUS + 3 bullets."
        ),
        "max_tokens_lite": 550,
        "max_tokens_full": 750,
    },
    "anomaly_investigation": {
        "system": (
            f"You are a stablecoin forensics analyst. {_AI_OUTPUT_RULES} "
            "Return:\n"
            "STATUS: <likely severity>\n"
            "- <likely cause from metrics>\n"
            "- <market impact>\n"
            "- <recommended operator action>\n"
            "Word budget: ~100 words."
        ),
        "user": (
            "DATA for {asset_symbol}:\n"
            "Highest Z-Score: {z_score_max}\n"
            "Anomaly Metrics: {anomalies}\n"
            "Bridge Flow: {bridge_flow}\n"
            "Write STATUS + 3 bullets."
        ),
        "max_tokens_lite": 350,
        "max_tokens_full": 500,
    },
    "market_overview": {
        "system": (
            f"You are a multi-stablecoin market intelligence analyst. {_AI_OUTPUT_RULES} "
            "Return:\n"
            "STATUS: <book-wide health one-liner>\n"
            "- <stability / average risk>\n"
            "- <band concentration or divergence>\n"
            "- <supply or chain note>\n"
            "- <asset(s) to watch>\n"
            "Word budget: ~160 words."
        ),
        "user": (
            "DATA book:\n"
            "Assets ({asset_count}): {asset_list}\n"
            "Average Risk: {avg_signal_score}/100 | Bands: {band_summary}\n"
            "Chains: {total_chains} | Supply changes 24h: {supply_changes}\n"
            "Write STATUS + 4 bullets."
        ),
        "max_tokens_lite": 700,
        "max_tokens_full": 1000,
    },
    "insight_summary": {
        "system": (
            f"You are a stablecoin intelligence analyst. {_AI_OUTPUT_RULES} "
            "Return:\n"
            "STATUS: <stability one-liner>\n"
            "- <trend from supply/chains>\n"
            "- <risk watch (anomalies/regime)>\n"
            "- <operator focus>\n"
            "Word budget: ~110 words."
        ),
        "user": (
            "DATA for {asset_symbol}:\n"
            "Risk {signal_score}/100 ({signal_band}) | Regime: {regime}\n"
            "Supply Δ24h: {supply_change_pct}% | Chains: {chain_count} | Top share: {top_chain_share}%\n"
            "Anomalies 7d: {anomaly_count} | Peg: {peg_price} | DEWS: {dews_score}\n"
            "Write STATUS + 3 bullets."
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
        "peg_price", "dews_score", "dews_band", "web_context",
    ):
        available.setdefault(k, "?")
    if "feature" in template:
        available.setdefault("feature", feature)
    prompt = template.format(**available)
    web_ctx = str(context.get("web_context") or "").strip()
    if web_ctx and web_ctx != "?":
        prompt = f"{prompt}\n\n{web_ctx}"
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


def _record_usage(db: Any, provider_id: str, model: str, tokens: int) -> None:
    meta = PROVIDER_METADATA.get(provider_id, {})
    cpm = meta.get("cost_per_million", 0)
    cost = (tokens / 1_000_000) * cpm
    increment_ai_usage(db=db, provider=provider_id, model=model, tokens=tokens, cost=cost)


def chat_for_feature(
    *,
    db: Any,
    feature: str | None,
    prompt: str,
    system: str | None = None,
    max_tokens: int = 256,
) -> dict[str, Any] | None:
    """Direct LLM call using the 3-tier provider chain (for non-enrich callers)."""
    if ai_mode(db) == "ai_off" or db is None:
        return None

    errors: list[str] = []
    provider_chain = get_ai_provider_chain(db=db, feature=feature)
    if not provider_chain:
        return None

    for provider_fn in provider_chain:
        pname = getattr(provider_fn, "_provider_name", "unknown")
        tier = getattr(provider_fn, "_tier", "unknown")
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
                errors.append(f"{pname}:call_failed")
                continue

            _record_call(pname)
            tokens_returned = int(result.get("tokens") or 0) or max_tokens
            _record_usage(db, result.get("provider", pname), result.get("model", ""), tokens_returned)
            log.info(
                "ai.chat_for_feature_success",
                provider=pname,
                tier=tier,
                feature=feature,
                latency_ms=latency_ms,
                tokens=tokens_returned,
            )
            return result
        except Exception as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            _record_fallback(pname)
            errors.append(f"{pname}:{exc}")
            log.warning(
                "ai.chat_for_feature_error",
                provider=pname,
                tier=tier,
                feature=feature,
                latency_ms=latency_ms,
                exc_info=True,
            )

    if errors:
        log.warning("ai.chat_for_feature_all_failed", feature=feature, errors=errors)
    return None


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

    preferred_tier: str | None = getattr(provider_chain[0], "_tier", None)

    for provider_fn in provider_chain:
        pname = getattr(provider_fn, "_provider_name", "unknown")
        tier = getattr(provider_fn, "_tier", "unknown")
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
                errors.append(f"{pname}:call_failed")
                log.warning(
                    "ai.provider_failed",
                    provider=pname,
                    tier=tier,
                    feature=feature,
                    reason="call_failed",
                    latency_ms=latency_ms,
                )
                continue

            _record_call(pname)
            log.info(
                "ai.provider_success",
                provider=pname,
                tier=tier,
                model=result.get("model"),
                feature=feature,
                latency_ms=latency_ms,
                tokens=result.get("tokens"),
            )

            if preferred_tier and tier != preferred_tier:
                _record_fallback(pname)

            tokens_returned = int(result.get("tokens") or 0) or max_tokens
            now_dt = datetime.now(timezone.utc)
            payload = {
                "available": True,
                "mode": mode,
                "feature": feature,
                "provider": result["provider"],
                "model": result["model"],
                "tier": tier,
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
                _record_usage(db, result.get("provider", pname), result.get("model", ""), tokens_returned)
            return payload
        except Exception as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            _record_fallback(pname)
            errors.append(f"{pname}:{exc}")
            log.warning(
                "ai.provider_error",
                provider=pname,
                tier=tier,
                feature=feature,
                latency_ms=latency_ms,
                exc_info=True,
            )

    return {"available": False, "mode": mode, "reason": "all_providers_failed", "errors": errors}


# Back-compat alias for legacy callers / tests that patch _ollama_cloud.
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
    import httpx

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
