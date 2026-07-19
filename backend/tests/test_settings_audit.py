"""Tests for settings audit log redaction."""

from __future__ import annotations

from sqlalchemy import select

from database import SettingsAuditLog
from providers.settings import set_setting


def test_set_setting_redacts_secrets_in_audit(db_session) -> None:
    set_setting("secret_ollama_api_key", "sk-test-secret-value", db_session)
    row = db_session.execute(
        select(SettingsAuditLog)
        .where(SettingsAuditLog.setting_key == "secret_ollama_api_key")
        .order_by(SettingsAuditLog.created_at.desc())
    ).scalars().first()
    assert row is not None
    assert row.new_value == "[REDACTED]"
    assert "sk-test" not in (row.new_value or "")
