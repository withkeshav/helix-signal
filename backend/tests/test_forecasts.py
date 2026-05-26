from datetime import datetime, timezone


def test_forecasts_empty_db(client):
    response = client.get("/api/forecasts?asset=USDT")
    assert response.status_code == 200
    data = response.json()
    assert data["forecasts"] == []
    assert data["forecast_points"] == {}
    assert data["historical"] == {}
    assert data["asset"] == "USDT"


def test_forecasts_populated(client, db_session):
    from database import ForecastRun, ForecastPoint
    run = ForecastRun(
        model_name="timesfm",
        model_version="2.0",
        target_metric="depeg_index",
        asset_symbol="USDT",
        input_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        input_end=datetime(2025, 1, 2, tzinfo=timezone.utc),
        horizon=24,
        frequency="1h",
        status="completed",
        generated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    pt = ForecastPoint(
        run_id=run.id,
        asset_symbol="USDT",
        target_metric="depeg_index",
        horizon_step=1,
        forecast_timestamp=datetime(2025, 6, 2, tzinfo=timezone.utc),
        point_forecast=1.0,
        q10=0.5,
        q50=1.0,
        q90=1.5,
    )
    db_session.add(pt)
    db_session.commit()

    response = client.get("/api/forecasts?asset=USDT")
    assert response.status_code == 200
    data = response.json()
    assert len(data["forecasts"]) == 1
    assert data["forecasts"][0]["model"] == "timesfm"
    assert data["forecasts"][0]["metric"] == "depeg_index"


def test_forecasts_invalid_asset(client):
    response = client.get("/api/forecasts?asset=")
    assert response.status_code in (400, 422)
    assert "detail" in response.json() or "message" in response.json()


def test_forecast_accuracy_empty_db(client):
    response = client.get("/api/analytics/forecast-accuracy?asset=USDT")
    assert response.status_code == 200
    data = response.json()
    assert data["asset"] == "USDT"
    assert data["runs_evaluated"] == 0
    assert data["results"] == []


def test_forecast_accuracy_populated(client, db_session):
    from database import ForecastRun, ForecastPoint, AssetTrendSnapshot
    run = ForecastRun(
        model_name="timesfm",
        model_version="2.0",
        target_metric="depeg_index",
        asset_symbol="USDT",
        input_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        input_end=datetime(2025, 1, 2, tzinfo=timezone.utc),
        horizon=24,
        frequency="1h",
        status="completed",
        generated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    ts1 = datetime(2025, 6, 2, 0, 0, tzinfo=timezone.utc)
    ts2 = datetime(2025, 6, 2, 1, 0, tzinfo=timezone.utc)
    db_session.add(ForecastPoint(
        run_id=run.id, asset_symbol="USDT", target_metric="depeg_index",
        horizon_step=1, forecast_timestamp=ts1, q50=10.0,
    ))
    db_session.add(ForecastPoint(
        run_id=run.id, asset_symbol="USDT", target_metric="depeg_index",
        horizon_step=2, forecast_timestamp=ts2, q50=12.0,
    ))
    db_session.add(AssetTrendSnapshot(
        asset_symbol="USDT", timestamp=ts1, bucket_id=1, depeg_index=10,
    ))
    db_session.add(AssetTrendSnapshot(
        asset_symbol="USDT", timestamp=ts2, bucket_id=2, depeg_index=12,
    ))
    db_session.commit()

    response = client.get("/api/analytics/forecast-accuracy?asset=USDT")
    assert response.status_code == 200
    data = response.json()
    assert data["runs_evaluated"] >= 1
