"""Anomaly investigation cooldown tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agents.anomaly_agent import _recent_ai_investigation, INVESTIGATION_COOLDOWN_MINUTES
from database import SignalEvent


def test_recent_ai_investigation_no_events(db_session) -> None:
    result = _recent_ai_investigation(db_session, asset_symbol="USDT")
    assert result is False


def test_recent_ai_investigation_within_cooldown(db_session) -> None:
    event = SignalEvent(
        asset_symbol="USDT",
        chain_key=None,
        event_type="ai_investigation",
        severity="warning",
        title="test investigation",
        summary="test",
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()

    result = _recent_ai_investigation(db_session, asset_symbol="USDT")
    assert result is True


def test_recent_ai_investigation_outside_cooldown(db_session) -> None:
    from datetime import timedelta

    old_ts = datetime.now(timezone.utc) - timedelta(minutes=INVESTIGATION_COOLDOWN_MINUTES + 5)
    event = SignalEvent(
        asset_symbol="USDT",
        chain_key=None,
        event_type="ai_investigation",
        severity="warning",
        title="old investigation",
        summary="test",
        timestamp=old_ts,
    )
    db_session.add(event)
    db_session.commit()

    result = _recent_ai_investigation(db_session, asset_symbol="USDT")
    assert result is False


def test_recent_ai_investigation_ignores_other_event_types(db_session) -> None:
    event = SignalEvent(
        asset_symbol="USDT",
        chain_key=None,
        event_type="anomaly_detected",
        severity="warning",
        title="not ai investigation",
        summary="test",
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()

    result = _recent_ai_investigation(db_session, asset_symbol="USDT")
    assert result is False
