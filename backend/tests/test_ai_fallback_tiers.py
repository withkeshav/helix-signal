"""Tests for 3-tier AI provider fallback chain."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from database import AiProvider
from providers.settings import set_setting
from providers.settings_crypto import encrypt_secret
from services.ai_router import enrich_with_ai, get_ai_provider_chain


@pytest.fixture()
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "test-encryption-key-for-fallback-pytest"
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", key)
    return key


def _register_provider(db, provider_id: str, api_key: str = "sk-test") -> None:
    db.add(
        AiProvider(
            id=provider_id,
            label=provider_id,
            base_url=f"https://{provider_id}.example.com/v1",
            api_key_enc=encrypt_secret(api_key),
            enabled=True,
        )
    )
    db.commit()


def test_three_tier_fallback_order(db_session, monkeypatch: pytest.MonkeyPatch, encryption_key):
    monkeypatch.setenv("AI_MODE", "ai_full")
    _register_provider(db_session, "primary_p")
    _register_provider(db_session, "task_fb_p")
    _register_provider(db_session, "global_fb_p")

    set_setting("ai_model_risk_explain", "primary_p:model-a", db_session)
    set_setting("ai_fallback_provider", "task_fb_p", db_session)
    set_setting("ai_fallback_model", "model-b", db_session)
    set_setting("ai_default_fallback_provider", "global_fb_p", db_session)
    set_setting("ai_default_fallback_model_id", "model-c", db_session)

    chain = get_ai_provider_chain(db=db_session, feature="risk_explain")
    assert len(chain) == 3
    assert chain[0]._provider_name == "primary_p"
    assert chain[0]._tier == "primary"
    assert chain[1]._provider_name == "task_fb_p"
    assert chain[1]._tier == "task_fallback"
    assert chain[2]._provider_name == "global_fb_p"
    assert chain[2]._tier == "global_fallback"


def test_enrich_falls_through_tiers(db_session, monkeypatch: pytest.MonkeyPatch, encryption_key):
    monkeypatch.setenv("AI_MODE", "ai_full")
    _register_provider(db_session, "primary_p")
    _register_provider(db_session, "task_fb_p")

    set_setting("ai_model_risk_explain", "primary_p:model-a", db_session)
    set_setting("ai_fallback_provider", "task_fb_p", db_session)
    set_setting("ai_fallback_model", "model-b", db_session)

    call_log: list[str] = []

    def _mock_chat(db, provider_id, model_id, messages, max_tokens=256, **kwargs):
        call_log.append(provider_id)
        if provider_id == "primary_p":
            return None
        return {
            "provider": provider_id,
            "model": model_id,
            "text": "Fallback succeeded",
            "tokens": 12,
        }

    monkeypatch.setattr("services.ai_router.chat_completion", _mock_chat)

    result = enrich_with_ai(
        feature="risk_explain",
        context={"asset_symbol": "USDT", "signal_score": 10, "signal_band": "Normal", "regime": "stable"},
        db=db_session,
    )
    assert result["available"] is True
    assert result["provider"] == "task_fb_p"
    assert result["tier"] == "task_fallback"
    assert call_log == ["primary_p", "task_fb_p"]


def test_enrich_ai_off_safe(db_session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AI_MODE", "ai_off")
    set_setting("ai_mode", "ai_off", db_session)
    result = enrich_with_ai(
        feature="risk_explain",
        context={"asset_symbol": "USDT"},
        db=db_session,
    )
    assert result["available"] is False
    assert result["mode"] == "ai_off"


def test_all_tiers_fail(db_session, monkeypatch: pytest.MonkeyPatch, encryption_key):
    monkeypatch.setenv("AI_MODE", "ai_full")
    _register_provider(db_session, "primary_p")
    set_setting("ai_model_risk_explain", "primary_p:model-a", db_session)

    monkeypatch.setattr("services.llm_client.chat_completion", lambda *a, **k: None)

    result = enrich_with_ai(
        feature="risk_explain",
        context={"asset_symbol": "USDT", "signal_score": 10, "signal_band": "Normal", "regime": "stable"},
        db=db_session,
    )
    assert result["available"] is False
    assert result["reason"] == "all_providers_failed"


def test_chat_for_feature_skips_when_ai_off(db_session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AI_MODE", "ai_off")
    set_setting("ai_mode", "ai_off", db_session)
    from services.ai_router import chat_for_feature

    assert chat_for_feature(db=db_session, feature="risk_explain", prompt="hi") is None
