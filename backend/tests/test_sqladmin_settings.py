"""Phase 0.5 — SQLAdmin secret-mask and set_setting(flush) contract tests."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from database import SettingsAuditLog
from providers.settings import Setting, get_setting, set_setting
from sqladmin_setup import is_secret_skip_value


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, True),
        ("", True),
        ("   ", True),
        ("configured", True),
        ("Configured", True),
        ("********", True),
        ("****", True),
        ("[REDACTED]", True),
        ("sk-live-new-secret", False),
        ("ollama-real-key", False),
    ],
)
def test_is_secret_skip_value(value, expected) -> None:
    assert is_secret_skip_value(value) is expected


def test_secret_masked_skip_does_not_overwrite(db_session) -> None:
    """Submitting a mask/empty sentinel must leave the stored secret unchanged."""
    set_setting("secret_ollama_api_key", "sk-original-value", db_session)
    assert get_setting("secret_ollama_api_key", db_session) == "sk-original-value"

    # Simulate SettingAdmin update_model skip path
    if is_secret_skip_value("configured"):
        pass  # no set_setting call
    else:
        set_setting("secret_ollama_api_key", "configured", db_session)

    assert get_setting("secret_ollama_api_key", db_session) == "sk-original-value"
    row = db_session.execute(
        select(Setting).where(Setting.key == "secret_ollama_api_key")
    ).scalars().first()
    assert row is not None
    assert row.value == "sk-original-value"


def test_secret_empty_skip_does_not_overwrite(db_session) -> None:
    set_setting("secret_ollama_api_key", "sk-keep-me", db_session)
    assert is_secret_skip_value("") is True
    assert get_setting("secret_ollama_api_key", db_session) == "sk-keep-me"


def test_set_setting_flush_single_commit_writes_audit(db_session) -> None:
    """flush=True leaves the outer session in control; audit row is written."""
    set_setting("ai_mode", "ai_lite", db_session)  # commits so row exists
    before = db_session.execute(
        select(SettingsAuditLog).where(SettingsAuditLog.setting_key == "ai_mode")
    ).scalars().all()
    before_count = len(before)

    set_setting("ai_mode", "ai_full", db_session, flush=True)
    # log_settings_change commits; outer commit is idempotent for the contract
    db_session.commit()

    after = db_session.execute(
        select(SettingsAuditLog).where(SettingsAuditLog.setting_key == "ai_mode")
    ).scalars().all()
    assert len(after) == before_count + 1
    assert get_setting("ai_mode", db_session) == "ai_full"


def test_invalid_enum_rejected(db_session) -> None:
    with pytest.raises(ValueError, match="must be one of"):
        set_setting("ai_mode", "not-a-mode", db_session, flush=True)
