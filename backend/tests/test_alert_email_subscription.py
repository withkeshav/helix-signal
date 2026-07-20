"""Tests for SMTP event subscription via alert_router."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from database import SignalEvent
from services.alert_router import deliver_email, _email_subscribed


def _event(event_type: str = "signal_band_change", severity: str = "warning") -> SignalEvent:
    return SignalEvent(
        asset_symbol="USDT",
        chain_key=None,
        event_type=event_type,
        severity=severity,
        title="Test",
        summary="Summary",
        timestamp=datetime.now(timezone.utc),
    )


def test_email_skipped_when_type_not_subscribed(db_session):
    from providers.settings import set_setting

    set_setting("alert_email_enabled", True, db_session)
    set_setting("alert_email_event_types", '["peg_deviation"]', db_session)
    set_setting("alert_email_min_severity", "warning", db_session)

    assert _email_subscribed(db_session, _event("signal_band_change")) is False
    assert _email_subscribed(db_session, _event("peg_deviation")) is True


def test_email_missing_smtp_returns_clear_error(db_session):
    from providers.settings import set_setting

    set_setting("alert_email_enabled", True, db_session)
    set_setting("alert_email_event_types", '["signal_band_change"]', db_session)
    set_setting("alert_email_min_severity", "info", db_session)
    set_setting("alert_smtp_host", "", db_session)
    set_setting("alert_email_to", "ops@example.com", db_session)

    result = deliver_email(db_session, _event())
    assert result["dispatched"] is False
    assert result["reason"] == "missing_smtp_config"


def test_no_discord_path_in_alert_router():
    import inspect
    import services.alert_router as ar
    import services.alerts as alerts

    src = inspect.getsource(ar) + inspect.getsource(alerts)
    assert "discord" not in src.lower()
    assert "telegram" not in src.lower()
