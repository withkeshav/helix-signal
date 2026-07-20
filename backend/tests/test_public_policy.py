"""Public display policy tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from providers.settings import set_setting
from core.public_policy import (
    demo_mode_active,
    effective_public_history_hours,
    public_config,
    window_allowed_for_hours,
)


def test_default_public_history_24h(db_session):
    assert effective_public_history_hours(db_session) == 24
    cfg = public_config(db_session)
    assert cfg["public_history_hours"] == 24
    assert cfg["public_export_enabled"] is False


def test_window_allowed():
    assert window_allowed_for_hours("24h", 24) is True
    assert window_allowed_for_hours("7d", 24) is False
    assert window_allowed_for_hours("7d", 168) is True


def test_demo_mode_widens(db_session):
    set_setting("demo_mode_enabled", True, db_session)
    set_setting("demo_history_hours", 168, db_session)
    set_setting("demo_mode_until", "", db_session)
    assert demo_mode_active(db_session) is True
    assert effective_public_history_hours(db_session) == 168


def test_demo_mode_expires(db_session):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    set_setting("demo_mode_enabled", True, db_session)
    set_setting("demo_mode_until", past, db_session)
    assert demo_mode_active(db_session) is False
    assert effective_public_history_hours(db_session) == 24


def test_public_config_endpoint(client):
    r = client.get("/api/public/config")
    assert r.status_code == 200
    body = r.json()
    assert body["public_history_hours"] == 24
    assert "signal" in body["public_tabs"]
