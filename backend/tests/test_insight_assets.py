"""Tests for versioned insight assets (WO-DA-4)."""

from providers.settings import set_setting
from services.insight_assets import VALID_KINDS, persist_insight


def test_insight_risk_explain_deterministic_when_ai_off(db_session, client):
    set_setting("ai_mode", "ai_off", db_session)
    resp = client.get("/api/insights/risk_explain?asset=USDT")
    assert resp.status_code == 200
    body = resp.json()
    assert body["schema_version"] == "1.0"
    assert body["kind"] == "risk_explain"
    assert "deterministic_payload" in body
    assert body["deterministic_payload"].get("asset") == "USDT"
    assert "ai_narrative" not in body


def test_insight_kinds_registered(client):
    for kind in ("risk_explain", "market_snapshot", "anomaly_digest", "dews_explain"):
        resp = client.get(f"/api/insights/{kind}?asset=USDT")
        assert resp.status_code == 200, kind
        assert resp.json()["kind"] == kind


def test_insight_export_ndjson(db_session, client):
    persist_insight(db_session, "risk_explain", "USDT")
    resp = client.get("/api/insights/risk_explain/export?format=ndjson")
    assert resp.status_code == 200
    assert "risk_explain" in resp.text


def test_unknown_kind_404(client):
    resp = client.get("/api/insights/not_a_kind")
    assert resp.status_code == 404


def test_valid_kinds_frozen():
    assert "forecast_run" in VALID_KINDS
