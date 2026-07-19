"""Tests for webhook alert dispatcher."""

from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


from database import SignalEvent
from services.webhook_dispatcher import (
    WebhookDispatcher,
    build_alert_payload,
    compute_signature,
    dispatch_events,
)


def _event(severity: str = "warning") -> SignalEvent:
    return SignalEvent(
        asset_symbol="USDT",
        chain_key=None,
        event_type="signal_band_change",
        severity=severity,
        title="Test event",
        summary="Summary",
        old_value="Watch",
        new_value="Alert",
        delta=None,
        threshold=None,
        timestamp=datetime.now(timezone.utc),
    )


def test_payload_schema_required_fields():
    payload = build_alert_payload(_event(), signal_score=42, depeg_index=10)
    for key in (
        "schema_version",
        "event_id",
        "timestamp",
        "asset_symbol",
        "severity",
        "event_type",
        "title",
        "summary",
        "metrics",
    ):
        assert key in payload
    assert payload["metrics"]["signal_score"] == 42


def test_hmac_signature_header():
    body = b'{"hello":"world"}'
    sig = compute_signature(body, "test-secret")
    assert sig.startswith("sha256=")
    assert len(sig) > 20


def test_disabled_webhook_noop():
    db = MagicMock()
    with patch("providers.settings.get_setting", side_effect=lambda k, _db=None: False if k == "webhook_enabled" else ""):
        dispatcher = WebhookDispatcher(db)
        result = dispatcher.deliver_event(_event())
    assert result["dispatched"] is False


def _webhook_patches(fake_setting):
    def fake_secret(key, db=None):
        if key == "webhook_signing_secret":
            return str(fake_setting(key, db) or "")
        return ""

    return (
        patch("providers.settings.get_setting", side_effect=fake_setting),
        patch("providers.settings.get_secret", side_effect=fake_secret),
    )


def test_min_severity_filter():
    db = MagicMock()

    def fake_setting(key, db=None):
        return {
            "webhook_enabled": True,
            "webhook_url": "https://example.com/hook",
            "webhook_signing_secret": "secret",
            "webhook_min_severity": "warning",
            "webhook_timeout_seconds": 10,
        }.get(key)

    with ExitStack() as stack:
        for p in _webhook_patches(fake_setting):
            stack.enter_context(p)
        dispatcher = WebhookDispatcher(db)
        assert dispatcher.should_dispatch(_event("info")) is False
        assert dispatcher.should_dispatch(_event("warning")) is True
        assert dispatcher.should_dispatch(_event("critical")) is True


def test_delivery_success_with_retry(monkeypatch):
    db = MagicMock()
    calls = {"n": 0}

    class FakeResp:
        status_code = 200

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, content, headers):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("transient")
            return FakeResp()

    def fake_setting(key, db=None):
        return {
            "webhook_enabled": True,
            "webhook_url": "https://example.com/hook",
            "webhook_signing_secret": "secret",
            "webhook_min_severity": "info",
            "webhook_timeout_seconds": 5,
        }.get(key)

    monkeypatch.setattr("services.webhook_dispatcher.time.sleep", lambda _s: None)
    with ExitStack() as stack:
        for p in _webhook_patches(fake_setting):
            stack.enter_context(p)
        with patch("services.webhook_dispatcher.httpx.Client", FakeClient):
            dispatcher = WebhookDispatcher(db)
            result = dispatcher.deliver_event(_event("critical"))
    assert result["dispatched"] is True
    assert calls["n"] == 2


def test_dispatch_events_batch_disabled():
    db = MagicMock()
    with patch("providers.settings.get_setting", return_value=False):
        out = dispatch_events(db, [_event()])
    assert out == []
