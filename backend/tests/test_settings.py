"""Tests for settings provider (DB priority, mask_secret, enum validation)."""

from __future__ import annotations

import pytest

from providers.settings import get_setting, mask_secret, set_setting


def test_get_setting_db_priority_over_env(monkeypatch: pytest.MonkeyPatch, db_session) -> None:
    """get_setting() should read DB before env for non-secret settings."""
    monkeypatch.setenv("AI_MODE", "ai_off")
    set_setting("ai_mode", "ai_full", db_session)
    assert get_setting("ai_mode", db_session) == "ai_full"


def test_mask_secret_returns_null_for_empty() -> None:
    assert mask_secret("") is None
    assert mask_secret(None) is None  # type: ignore[arg-type]


def test_mask_secret_returns_configured() -> None:
    assert mask_secret("sk-test-key") == "configured"


def test_ai_mode_enum_validation(db_session) -> None:
    with pytest.raises(ValueError, match="must be one of"):
        set_setting("ai_mode", "banana", db_session)
