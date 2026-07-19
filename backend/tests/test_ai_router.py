"""Tests for the simplified AI router (Ollama Cloud + OpenRouter only)."""

from __future__ import annotations

import time

import pytest

from providers.settings import set_setting
from services.ai_router import (
    PROVIDER_METADATA,
    VALID_PROVIDERS,
    _check_rate_limit,
    _parse_provider_model,
    _providers_for_mode,
    _record_call,
    _record_fallback,
    ai_mode,
    enrich_with_ai,
    get_ai_provider_chain,
    get_provider_stats,
)


def test_parse_provider_model_valid() -> None:
    assert _parse_provider_model("ollama_cloud:ministral-3:8b-cloud") == (
        "ollama_cloud",
        "ministral-3:8b-cloud",
    )
    assert _parse_provider_model("openrouter:openai/gpt-4o-mini") == (
        "openrouter",
        "openai/gpt-4o-mini",
    )


def test_parse_provider_model_invalid() -> None:
    assert _parse_provider_model("") is None
    assert _parse_provider_model("invalid:model") is None
    assert _parse_provider_model("ollama_cloud") is None


def test_provider_metadata_only_supported() -> None:
    assert set(PROVIDER_METADATA.keys()) == set(VALID_PROVIDERS)


def test_provider_chain_ai_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_off")
    assert get_ai_provider_chain() == []


def test_provider_chain_from_db(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_full")
    monkeypatch.setenv("OLLAMA_API_KEY", "ok-test")
    set_setting("ai_model_risk_explain", "ollama_cloud:ministral-3:8b-cloud", db_session)
    set_setting("ai_fallback_provider", "openrouter", db_session)
    set_setting("ai_fallback_model", "openai/gpt-4o-mini", db_session)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    chain = get_ai_provider_chain(db=db_session, feature="risk_explain")
    assert len(chain) == 2
    assert chain[0]._provider_name == "ollama_cloud"
    assert chain[1]._provider_name == "openrouter"


def test_enrich_with_ai_ai_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_off")
    result = enrich_with_ai(feature="risk_explain", context={"asset_symbol": "USDT"})
    assert result["available"] is False
    assert result["mode"] == "ai_off"
    assert ai_mode() == "ai_off"


def test_enrich_with_ai_model_not_configured(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_full")
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    set_setting("ai_model_risk_explain", "", db_session)
    result = enrich_with_ai(
        feature="risk_explain",
        context={"asset_symbol": "USDT", "signal_score": 10},
        db=db_session,
    )
    assert result["available"] is False
    assert result["reason"] in ("model_not_configured", "no_providers_configured", "all_providers_failed")


def test_enrich_with_ai_all_providers_failed(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_full")
    monkeypatch.setenv("OLLAMA_API_KEY", "ok-test")
    set_setting("ai_model_risk_explain", "ollama_cloud:ministral-3:8b-cloud", db_session)
    result = enrich_with_ai(
        feature="risk_explain",
        context={"asset_symbol": "USDT", "signal_score": 10},
        db=db_session,
    )
    assert result["available"] is False


def test_providers_for_mode_ai_off() -> None:
    assert _providers_for_mode("ai_off") == []


def test_check_rate_limit_within() -> None:
    name = "test_within"
    assert _check_rate_limit(name, 10) is True
    _record_call(name)
    assert _check_rate_limit(name, 10) is True


def test_fallback_counting() -> None:
    target = "ollama_cloud"
    before = get_provider_stats()[target]["fallback_count"]
    _record_fallback(target)
    assert get_provider_stats()[target]["fallback_count"] == before + 1


def test_get_provider_stats_shape() -> None:
    stats = get_provider_stats()
    assert set(stats.keys()) == set(VALID_PROVIDERS)
    for data in stats.values():
        assert "label" in data
        assert "api_key_configured" in data


def test_enrich_with_ai_requires_keywords() -> None:
    with pytest.raises(TypeError):
        enrich_with_ai("risk_explain", {"asset_symbol": "USDT"})  # type: ignore[call-arg]


def test_rate_limit_window_expiry() -> None:
    from services.ai_router import _PROVIDER_RATE_LIMITS

    name = "test_window_expiry"
    _PROVIDER_RATE_LIMITS[name] = [time.time() - 120]
    assert _check_rate_limit(name, 1) is True
