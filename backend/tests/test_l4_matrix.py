"""L4 gate — deterministic insight surfaces with ai_mode off (kimi §3 matrix)."""

from providers.settings import set_setting


def _set_ai_off(db):
    set_setting("ai_mode", "ai_off", db)
    for key in (
        "feature_ai_summary",
        "feature_ai_explain",
        "feature_ai_insights",
        "feature_ai_narrative",
    ):
        set_setting(key, False, db)


def test_l4_risk_explain_deterministic(client, db_session):
    _set_ai_off(db_session)
    db_session.commit()
    r = client.get("/api/insights/risk_explain?asset=USDT")
    assert r.status_code == 200
    assert r.json().get("deterministic_payload")


def test_l4_dews_deterministic(client, db_session):
    _set_ai_off(db_session)
    db_session.commit()
    r = client.get("/api/dews?asset=USDT")
    assert r.status_code == 200
    body = r.json()
    assert body.get("available") and ("band" in body or "score" in body or body.get("composite_score") is not None)


def test_l4_anomaly_detect(client, db_session):
    _set_ai_off(db_session)
    db_session.commit()
    r = client.get("/api/anomaly/detect?asset=USDT")
    assert r.status_code == 200
    assert "anomalies" in r.json()


def test_l4_osint_feed(client, db_session):
    _set_ai_off(db_session)
    db_session.commit()
    r = client.get("/api/osint/feed?limit=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_l4_predictive_bundle(client, db_session):
    _set_ai_off(db_session)
    db_session.commit()
    r = client.get("/api/predictive?asset=USDT")
    assert r.status_code == 200
    body = r.json()
    assert "depeg_probability" in body or "available" in body


def test_l4_insight_market_snapshot(client, db_session):
    _set_ai_off(db_session)
    db_session.commit()
    r = client.get("/api/insights/market_snapshot?asset=USDT")
    assert r.status_code in (200, 404)
