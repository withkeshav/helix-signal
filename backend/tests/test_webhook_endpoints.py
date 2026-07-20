"""Tests for multi-webhook endpoints + alert_router."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from database import SignalEvent, WebhookEndpoint
from providers.settings_crypto import encrypt_secret
from services.alert_router import (
    _endpoint_matches,
    deliver_to_endpoint,
    migrate_legacy_webhook_settings,
)
from services.event_catalog import event_category
from services.webhook_dispatcher import SIGNATURE_HEADER, compute_signature


def _event(event_type: str = "signal_band_change", severity: str = "warning", asset: str = "USDT") -> SignalEvent:
    return SignalEvent(
        asset_symbol=asset,
        chain_key=None,
        event_type=event_type,
        severity=severity,
        title="Test",
        summary="Summary",
        timestamp=datetime.now(timezone.utc),
    )


def test_event_category_maps_band_change():
    assert event_category("signal_band_change") == "signal_band_change"
    assert event_category("USDT:peg_deviation:warning").startswith("peg")


def test_endpoint_event_filter():
    ep = WebhookEndpoint(
        name="bands",
        url="https://example.com/a",
        signing_secret_enc=encrypt_secret("secret-secret"),
        enabled=True,
        min_severity="warning",
        event_types=["signal_band_change"],
        assets=[],
        timeout_seconds=10,
    )
    assert _endpoint_matches(ep, _event("signal_band_change")) is True
    assert _endpoint_matches(ep, _event("peg_deviation")) is False


def test_endpoint_asset_filter():
    ep = WebhookEndpoint(
        name="usdc",
        url="https://example.com/b",
        signing_secret_enc=encrypt_secret("secret-secret"),
        enabled=True,
        min_severity="info",
        event_types=[],
        assets=["USDC"],
        timeout_seconds=10,
    )
    assert _endpoint_matches(ep, _event(asset="USDC")) is True
    assert _endpoint_matches(ep, _event(asset="USDT")) is False


def test_private_url_rejected():
    ep = WebhookEndpoint(
        name="bad",
        url="http://127.0.0.1/hook",
        signing_secret_enc=encrypt_secret("secret-secret"),
        enabled=True,
        min_severity="info",
        event_types=[],
        assets=[],
        timeout_seconds=10,
    )
    result = deliver_to_endpoint(ep, _event())
    assert result["dispatched"] is False
    assert result["reason"] == "invalid_url"


def test_signature_on_delivery():
    captured = {}

    class FakeResp:
        status_code = 200

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, content=None, headers=None):
            captured["body"] = content
            captured["headers"] = headers
            return FakeResp()

    ep = WebhookEndpoint(
        id=1,
        name="ok",
        url="https://example.com/hook",
        signing_secret_enc=encrypt_secret("my-signing-secret"),
        enabled=True,
        min_severity="info",
        event_types=[],
        assets=[],
        timeout_seconds=10,
    )
    with patch("httpx.Client", FakeClient):
        result = deliver_to_endpoint(ep, _event(), metrics={"signal_score": 1})
    assert result["dispatched"] is True
    sig = captured["headers"][SIGNATURE_HEADER]
    assert sig == compute_signature(captured["body"], "my-signing-secret")


def test_migrate_legacy_webhook_settings(db_session):
    from providers.settings import set_setting

    set_setting("webhook_enabled", True, db_session)
    set_setting("webhook_url", "https://hooks.example.com/helix", db_session)
    set_setting("webhook_signing_secret", "legacy-secret-value", db_session)

    ep = migrate_legacy_webhook_settings(db_session)
    assert ep is not None
    assert ep.name == "Migrated default"
    assert ep.url == "https://hooks.example.com/helix"

    # Second call is no-op
    assert migrate_legacy_webhook_settings(db_session) is None


def test_two_endpoints_only_matching_delivers(db_session):
    from sqlalchemy import delete
    from services.alert_router import deliver_event

    db_session.execute(delete(WebhookEndpoint))
    db_session.commit()

    ep_band = WebhookEndpoint(
        name="bands",
        url="https://example.com/bands",
        signing_secret_enc=encrypt_secret("secret-aaaaaa"),
        enabled=True,
        min_severity="warning",
        event_types=["signal_band_change"],
        assets=[],
        timeout_seconds=10,
    )
    ep_peg = WebhookEndpoint(
        name="pegs",
        url="https://example.com/pegs",
        signing_secret_enc=encrypt_secret("secret-bbbbbb"),
        enabled=True,
        min_severity="warning",
        event_types=["peg_deviation"],
        assets=[],
        timeout_seconds=10,
    )
    db_session.add_all([ep_band, ep_peg])
    db_session.commit()

    delivered_urls = []

    def fake_deliver(ep, event, *, metrics=None):
        delivered_urls.append(ep.url)
        return {"dispatched": True, "endpoint_id": ep.id}

    with (
        patch("services.alert_router.deliver_to_endpoint", side_effect=fake_deliver),
        patch("services.alert_router.deliver_email", return_value={"dispatched": False, "reason": "skip"}),
    ):
        deliver_event(db_session, _event("signal_band_change"))

    assert delivered_urls == ["https://example.com/bands"]
