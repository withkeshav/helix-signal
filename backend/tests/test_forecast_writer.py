"""Lightweight linear forecast writer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from database import AssetTrendSnapshot, ForecastPoint, ForecastRun
from services.forecast_writer import _extrapolate, run_forecast_job


def test_extrapolate_flat():
    pts = _extrapolate([1.0, 1.0, 1.0], 3)
    assert len(pts) == 3
    assert all(abs(p - 1.0) < 1e-6 for p in pts)


def test_extrapolate_upward():
    pts = _extrapolate([1.0, 2.0, 3.0], 2)
    assert pts[0] > 3.0
    assert pts[1] > pts[0]


def test_run_forecast_job_writes_rows(db_session):
    now = datetime.now(timezone.utc)
    for i in range(10):
        db_session.add(
            AssetTrendSnapshot(
                asset_symbol="USDT",
                timestamp=now - timedelta(hours=10 - i),
                bucket_id=i + 1,
                depeg_index=1.0 + i * 0.0001,
                signal_score=10,
                signal_band="Normal",
                concentration_score=0,
                data_confidence_label="High",
                source_status="ok",
                total_supply=1e10 + i * 1e6,
            )
        )
    db_session.commit()

    result = run_forecast_job(db_session)
    assert result["status"] == "ok"
    assert result["assets_written"] >= 1

    runs = db_session.query(ForecastRun).filter(ForecastRun.asset_symbol == "USDT").all()
    assert len(runs) >= 1
    pts = db_session.query(ForecastPoint).filter(ForecastPoint.asset_symbol == "USDT").all()
    assert len(pts) >= 1
