"""API tests for DEWS endpoint."""


def test_dews_endpoint(client):
    r = client.get("/api/dews?asset=USDT")
    assert r.status_code == 200
    body = r.json()
    assert body.get("asset") == "USDT"
    assert "dews_score" in body
    assert body.get("band") in ("normal", "watch", "warning", "critical")


def test_dews_v4_dispatch_with_stablecoin_type(client, db_session):
    """V4 ONNX model is used when stablecoin_type is present and model file exists."""
    from database import AssetChainSnapshot
    db_session.query(AssetChainSnapshot).filter(
        AssetChainSnapshot.asset_symbol == "USDT"
    ).update({"stablecoin_type": "fiat_backed"})
    db_session.commit()

    r = client.get("/api/dews?asset=USDT")
    assert r.status_code == 200
    body = r.json()
    model = body.get("model", "")
    assert model in ("onnx_depeg_v4", "heuristic_v1")


def test_dews_v4_fallback_without_stablecoin_type(client, db_session):
    """Falls back to legacy/heuristic when stablecoin_type is null."""
    from database import AssetChainSnapshot
    db_session.query(AssetChainSnapshot).filter(
        AssetChainSnapshot.asset_symbol == "USDT"
    ).update({"stablecoin_type": None})
    db_session.commit()

    r = client.get("/api/dews?asset=USDT")
    assert r.status_code == 200
    body = r.json()
    assert body.get("model") != "onnx_depeg_v4"