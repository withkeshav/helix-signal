"""Predictive core path and AI-off resilience."""

from __future__ import annotations

import pytest

from services.ai_router import ai_mode, enrich_with_ai
from services.predictive import run_predictive_bundle


def test_ai_off_returns_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_off")
    out = enrich_with_ai(feature="risk_explain", context={"asset_symbol": "USDT", "signal_score": 10})
    assert out["available"] is False
    assert ai_mode() == "ai_off"


def test_predictive_bundle_without_llm(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_off")
    monkeypatch.setenv("ENABLE_PREDICTIVE", "true")
    from tests.test_risk_inputs import _seed_usdt_snapshots

    _seed_usdt_snapshots(db_session)
    pred = run_predictive_bundle(db_session, asset_symbol="USDT")
    assert pred["available"] is True
    assert pred["regime"] in ("stable", "volatile", "crisis")
    assert "depeg_probability" in pred
    assert "horizon_1h" in pred["depeg_probability"]


def test_predictive_api(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_off")
    r = client.get("/api/predictive?asset=USDT")
    assert r.status_code == 200
    body = r.json()
    assert "available" in body
