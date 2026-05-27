"""Predictive core path and AI-off resilience."""

from __future__ import annotations

import pytest

from services.ai_router import ai_mode, enrich_with_ai
from services.predictive import run_predictive_bundle

network = pytest.mark.network


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


def test_ai_narrative_returns_200_when_ai_off(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_off")
    r = client.get("/api/ai/narrative?asset=USDT")
    assert r.status_code == 200
    body = r.json()
    assert body.get("available") is False


def test_ai_insights_returns_200_when_ai_off(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_off")
    r = client.get("/api/ai/insights?asset=USDT")
    assert r.status_code == 200
    body = r.json()
    assert body.get("available") is False


def test_ai_explain_returns_200_when_ai_off(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_off")
    r = client.get("/api/ai/explain?asset=USDT")
    assert r.status_code == 200
    body = r.json()
    assert body.get("available") is False


@network
def test_ai_narrative_returns_200_when_asset_not_found(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_lite")
    r = client.get("/api/ai/narrative?asset=NONEXISTENT")
    assert r.status_code == 200
    body = r.json()
    assert body.get("available") is False


@network
def test_ai_insights_returns_200_when_asset_not_found(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_lite")
    r = client.get("/api/ai/insights?asset=NONEXISTENT")
    assert r.status_code == 200
    body = r.json()
    assert body.get("available") is False


def test_ai_budget_endpoint(client) -> None:
    r = client.get("/api/ai/budget")
    assert r.status_code == 200
    body = r.json()
    assert "daily_budget" in body
    assert "tokens_used_today" in body
    assert "tokens_remaining" in body
    assert "pct_used" in body


def test_ai_budget_shape(client) -> None:
    r = client.get("/api/ai/budget")
    body = r.json()
    assert body["daily_budget"] > 0
    assert body["tokens_remaining"] >= 0
    assert 0 <= body["pct_used"] <= 100


def test_ai_explain_requires_token_when_enabled(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_lite")
    monkeypatch.setenv("AI_REQUIRE_TOKEN", "true")
    monkeypatch.setenv("HELIX_ADMIN_TOKEN", "test-admin-token")
    r = client.get("/api/ai/explain?asset=USDT", headers={"X-Admin-Token": "wrong"})
    assert r.status_code == 403


@network
def test_ai_explain_passes_with_correct_token(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_lite")
    monkeypatch.setenv("AI_REQUIRE_TOKEN", "true")
    monkeypatch.setenv("HELIX_ADMIN_TOKEN", "test-admin-token")
    r = client.get("/api/ai/explain?asset=USDT", headers={"X-Admin-Token": "test-admin-token"})
    assert r.status_code == 200


def test_ai_no_auth_when_token_not_configured(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODE", "ai_lite")
    monkeypatch.setenv("AI_REQUIRE_TOKEN", "true")
    monkeypatch.delenv("HELIX_ADMIN_TOKEN", raising=False)
    r = client.get("/api/ai/explain?asset=USDT")
    assert r.status_code == 503
