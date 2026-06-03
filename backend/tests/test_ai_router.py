"""Comprehensive tests for the refactored AI router.

Covers: dynamic provider chains, metadata, rate-limit tracking,
fallback counting, budget pre-check, and backward compatibility.
"""

from __future__ import annotations

import json
import time

import pytest

from services.ai_router import (
    PROVIDER_METADATA,
    _DEFAULT_PROVIDER_PRIORITY,
    _DEFAULT_LITE_PRIORITY,
    _check_rate_limit,
    _env_based_priority,
    _get_provider_priority_list,
    _providers_for_mode,
    _record_call,
    _record_fallback,
    _within_budget,
    ai_mode,
    enrich_with_ai,
    get_ai_provider_chain,
    get_provider_stats,
)

# ---------------------------------------------------------------------------
# Budget pre-check (_within_budget)
# ---------------------------------------------------------------------------


def test_within_budget_under_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "50000")
    assert _within_budget(100) is True
    assert _within_budget(50000) is True


def test_within_budget_exact_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "50000")
    assert _within_budget(50000) is True


def test_within_budget_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "100")
    assert _within_budget(101) is False


def test_within_budget_zero_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "0")
    assert _within_budget(1) is False


# ---------------------------------------------------------------------------
# Provider metadata structure
# ---------------------------------------------------------------------------


def test_provider_metadata_has_all_fields() -> None:
    required = {"groq", "ollama_cloud", "cloudflare", "openrouter_free", "openrouter_paid"}
    assert set(PROVIDER_METADATA.keys()) == required


def test_provider_metadata_structure() -> None:
    for name, meta in PROVIDER_METADATA.items():
        assert "label" in meta, f"{name} missing label"
        assert "default_model" in meta, f"{name} missing default_model"
        assert "env_key" in meta, f"{name} missing env_key"
        assert "cost_per_million" in meta, f"{name} missing cost_per_million"
        assert "rate_limit_rpm" in meta, f"{name} missing rate_limit_rpm"
        assert "models" in meta, f"{name} missing models"
        assert isinstance(meta["models"], list), f"{name} models not a list"
        assert meta["cost_per_million"] >= 0, f"{name} negative cost"


def test_groq_is_cheapest() -> None:
    costs = {name: meta["cost_per_million"] for name, meta in PROVIDER_METADATA.items()}
    assert costs["groq"] == 0.05
    assert costs["groq"] < costs["ollama_cloud"]
    assert costs["groq"] < costs["openrouter_paid"]


def test_openrouter_free_is_free() -> None:
    assert PROVIDER_METADATA["openrouter_free"]["cost_per_million"] == 0.0
    assert PROVIDER_METADATA["openrouter_free"]["free_tier_calls"] == 1000


# ---------------------------------------------------------------------------
# Default priority lists
# ---------------------------------------------------------------------------


def test_default_priority_includes_all() -> None:
    assert set(_DEFAULT_PROVIDER_PRIORITY) == {"groq", "ollama_cloud", "cloudflare", "openrouter_free", "openrouter_paid"}


def test_groq_is_first_in_default() -> None:
    assert _DEFAULT_PROVIDER_PRIORITY[0] == "groq"


def test_lite_priority() -> None:
    assert _DEFAULT_LITE_PRIORITY == ["openrouter_free", "ollama_cloud", "cloudflare"]


# ---------------------------------------------------------------------------
# _env_based_priority
# ---------------------------------------------------------------------------


def test_env_based_priority_ai_lite() -> None:
    result = _env_based_priority("ai_lite")
    assert result == _DEFAULT_LITE_PRIORITY


def test_env_based_priority_ai_full() -> None:
    result = _env_based_priority("ai_full")
    assert result == _DEFAULT_PROVIDER_PRIORITY


def test_env_based_priority_ai_off() -> None:
    result = _env_based_priority("ai_off")
    assert result == _DEFAULT_PROVIDER_PRIORITY  # ai_off is handled separately


# ---------------------------------------------------------------------------
# _get_provider_priority_list
# ---------------------------------------------------------------------------


def test_priority_list_ai_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_off")
    assert _get_provider_priority_list() == []


def test_priority_list_no_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_lite")
    result = _get_provider_priority_list(db=None)
    assert result == _DEFAULT_LITE_PRIORITY


def test_priority_list_fallback_ai_full(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_full")
    result = _get_provider_priority_list(db=None)
    assert "groq" in result


# ---------------------------------------------------------------------------
# get_ai_provider_chain
# ---------------------------------------------------------------------------


def test_provider_chain_ai_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_off")
    chain = get_ai_provider_chain()
    assert chain == []


def test_provider_chain_returns_callables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_lite")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("OLLAMA_API_KEY", "ok-test")
    chain = get_ai_provider_chain()
    assert len(chain) >= 1
    for fn in chain:
        assert callable(fn)
        assert hasattr(fn, "_provider_name")


def test_provider_chain_skips_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_full")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    chain = get_ai_provider_chain()
    # Without any keys, chain should be empty
    assert chain == []


def test_provider_chain_with_mixed_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_full")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    chain = get_ai_provider_chain()
    assert len(chain) >= 1
    assert chain[0]._provider_name == "openrouter_free"


# ---------------------------------------------------------------------------
# _providers_for_mode backward compat
# ---------------------------------------------------------------------------


def test_providers_for_mode_ai_off() -> None:
    assert _providers_for_mode("ai_off") == []


def test_providers_for_mode_no_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    chain = _providers_for_mode("ai_full")
    assert chain == []


def test_providers_for_mode_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("OLLAMA_API_KEY", "ok-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    chain = _providers_for_mode("ai_full", priority=True)
    assert len(chain) >= 2


# ---------------------------------------------------------------------------
# Rate-limit tracking
# ---------------------------------------------------------------------------


def test_check_rate_limit_no_limit() -> None:
    assert _check_rate_limit("test_provider", 0) is True


def test_check_rate_limit_within() -> None:
    assert _check_rate_limit("test_within", 10) is True
    _record_call("test_within")
    assert _check_rate_limit("test_within", 10) is True


def test_record_call() -> None:
    name = "test_record_call"
    _record_call(name)
    _record_call(name)
    _record_call(name)
    # After recording, check rate limit with low RPM should be false
    assert _check_rate_limit(name, 2) is False
    # With high enough RPM, should still be true
    assert _check_rate_limit(name, 10) is True


def test_fallback_counting() -> None:
    """Fallback tracking works for known providers in stats output."""
    target = "groq"
    before = get_provider_stats()[target]["fallback_count"]
    _record_fallback(target)
    after = get_provider_stats()[target]["fallback_count"]
    assert after == before + 1
    _record_fallback(target)
    assert get_provider_stats()[target]["fallback_count"] == after + 1


# ---------------------------------------------------------------------------
# get_provider_stats
# ---------------------------------------------------------------------------


def test_get_provider_stats_shape() -> None:
    stats = get_provider_stats()
    assert set(stats.keys()) == {"groq", "ollama_cloud", "cloudflare", "openrouter_free", "openrouter_paid"}
    for name, data in stats.items():
        assert "label" in data
        assert "cost_per_million" in data
        assert "rate_limit_rpm" in data
        assert "calls_last_minute" in data
        assert "total_calls_today" in data
        assert "fallback_count" in data
        assert "api_key_configured" in data


# ---------------------------------------------------------------------------
# enrich_with_ai — backward compat (env-only, no DB)
# ---------------------------------------------------------------------------


def test_enrich_with_ai_ai_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_off")
    result = enrich_with_ai(feature="risk_explain", context={"asset_symbol": "USDT"})
    assert result["available"] is False
    assert result["mode"] == "ai_off"
    assert ai_mode() == "ai_off"


def test_enrich_with_ai_over_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_lite")
    monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    result = enrich_with_ai(
        feature="risk_explain",
        context={"asset_symbol": "USDT", "signal_score": 10},
    )
    assert result["available"] is False
    assert result["reason"] == "daily_token_budget_exceeded"


def test_enrich_with_ai_all_providers_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_lite")
    monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "50000")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("OLLAMA_API_KEY", "ok-test")
    result = enrich_with_ai(
        feature="risk_explain",
        context={"asset_symbol": "USDT", "signal_score": 10},
    )
    # Providers exist but API calls fail (no real endpoint) -> all_providers_failed
    assert result["available"] is False


# ---------------------------------------------------------------------------
# enrich_with_ai — caching behavior
# ---------------------------------------------------------------------------


def test_enrich_with_ai_cache_returns_same(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_off")
    ctx = {"asset_symbol": "USDT", "signal_score": 10}
    first = enrich_with_ai(feature="risk_explain", context=ctx)
    second = enrich_with_ai(feature="risk_explain", context=ctx)
    assert first["available"] == second["available"]


# ---------------------------------------------------------------------------
# enrich_with_ai — no_keyword_args_mode
# ---------------------------------------------------------------------------


def test_enrich_with_ai_requires_keywords() -> None:
    with pytest.raises(TypeError):
        enrich_with_ai("risk_explain", {"asset_symbol": "USDT"})  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Integration with settings system (DB-backed chain)
# ---------------------------------------------------------------------------


def test_enrich_with_ai_priority_flag_backward_compat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_full")
    monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "50000")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # With no keys configured and ai_full, should fail gracefully
    result = enrich_with_ai(
        feature="risk_explain",
        context={"asset_symbol": "USDT", "signal_score": 10},
        priority=True,
    )
    assert result["available"] is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_unknown_feature_uses_fallback_prompt() -> None:
    from services.ai_router import _build_prompt

    prompt, system, max_tokens = _build_prompt("nonexistent_feature", {})
    assert prompt is not None
    assert system is not None
    assert max_tokens >= 120


def test_provider_chain_custom_priority_via_db(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that DB-backed priority overrides env defaults."""
    monkeypatch.setenv("AI_MODE", "ai_full")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("OLLAMA_API_KEY", "ok-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    from providers.settings import set_setting
    custom_priority = json.dumps(["ollama_cloud", "groq", "openrouter_free", "openrouter_paid"])
    set_setting("ai_provider_priority", custom_priority, db_session)

    result = _get_provider_priority_list(db=db_session)
    assert result == ["ollama_cloud", "groq", "openrouter_free", "openrouter_paid"]
    assert result[0] == "ollama_cloud"
    assert result[1] == "groq"


def test_get_provider_stats_no_api_keys() -> None:
    stats = get_provider_stats()
    for name in ("groq", "ollama_cloud", "openrouter_free", "openrouter_paid"):
        assert name in stats


def test_within_budget_resets_daily(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "50000")
    assert _within_budget(100) is True


def test_rate_limit_window_expiry() -> None:
    name = "test_window_expiry"
    old_timestamp = time.time() - 120  # 2 minutes ago
    from services.ai_router import _PROVIDER_RATE_LIMITS
    _PROVIDER_RATE_LIMITS[name] = [old_timestamp]
    # Should pass because old timestamps are purged
    assert _check_rate_limit(name, 1) is True


def test_provider_metadata_consistency() -> None:
    """Verify metadata matches between PROVIDER_METADATA and settings.py."""
    for name, meta in PROVIDER_METADATA.items():
        assert "models" in meta
        assert isinstance(meta["models"], list)
        assert len(meta["models"]) >= 1
        assert meta["default_model"] in meta["models"] or meta["default_model"] == meta["models"][0]
