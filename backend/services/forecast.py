"""Plain-function forecasts extracted from Celery worker_tasks.py.

Replaces Celery-based forecast_asset_metric with APScheduler-compatible functions.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from database import AssetTrendSnapshot, ForecastPoint, ForecastRun, SessionLocal
from services.forecast_signals import evaluate_forecast_risk
from structlog import get_logger

log = get_logger(__name__)

_ALLOWED_METRICS = frozenset({"total_supply", "price", "signal_score", "depeg_index", "concentration_score"})


def forecast_asset_metric(asset_symbol: str, metric: str, horizon: int = 24) -> dict:
    """Forecast a single asset metric using TimesFM.

    Plain function (no Celery) — callable from APScheduler or API endpoints.
    """
    from ml_models.registry import get_model_service

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        rows = (
            db.query(AssetTrendSnapshot)
            .filter(
                AssetTrendSnapshot.asset_symbol == asset_symbol,
                AssetTrendSnapshot.timestamp >= cutoff,
            )
            .order_by(AssetTrendSnapshot.timestamp.asc())
            .all()
        )

        if len(rows) < 10:
            return {"status": "skipped", "reason": "insufficient_data", "points": len(rows)}

        if metric not in _ALLOWED_METRICS:
            return {"status": "skipped", "reason": "invalid_metric", "metric": metric}

        values = [getattr(r, metric) for r in rows if getattr(r, metric) is not None]
        timestamps = [r.timestamp.isoformat() for r in rows if getattr(r, metric) is not None]

        if len(values) < 10:
            return {"status": "skipped", "reason": "insufficient_values", "points": len(values)}

        timesfm = get_model_service("timesfm")
        if timesfm is None:
            return {"status": "skipped", "reason": "timesfm_unavailable"}

        result = timesfm.forecast(
            series_id=f"{asset_symbol}_{metric}",
            values=values,
            timestamps=timestamps,
            horizon=horizon,
        )

        run = ForecastRun(
            model_name="timesfm",
            model_version="2.5.0",
            target_metric=metric,
            asset_symbol=asset_symbol,
            input_start=datetime.fromisoformat(timestamps[0]),
            input_end=datetime.fromisoformat(timestamps[-1]),
            horizon=horizon,
            frequency="5min",
            status="completed",
            input_points=len(values),
            generated_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.flush()

        for i, (ts, point) in enumerate(zip(result["forecast_timestamps"], result["point"])):
            fp = ForecastPoint(
                run_id=run.id,
                asset_symbol=asset_symbol,
                target_metric=metric,
                horizon_step=i + 1,
                forecast_timestamp=ts,
                point_forecast=point,
                q10=result["quantiles"]["q10"][i],
                q50=result["quantiles"]["q50"][i],
                q90=result["quantiles"]["q90"][i],
            )
            db.add(fp)

        db.commit()

        points_q = db.query(ForecastPoint).filter(ForecastPoint.run_id == run.id).all()
        signals = evaluate_forecast_risk(asset_symbol, metric, points_q)
        for sig in signals:
            from database import SignalEvent

            ev = SignalEvent(
                asset_symbol=sig["asset_symbol"],
                event_type=sig["event_type"],
                severity=sig["severity"],
                title=sig["title"],
                summary=sig["summary"],
                threshold=sig.get("threshold"),
                timestamp=sig["timestamp"],
                new_value=str(sig.get("forecast_value", "")),
                metadata_json=json.dumps({"model": "timesfm", "metric": metric, "horizon_step": sig.get("horizon_step")}),
            )
            db.add(ev)
        db.commit()

        log.info("forecast.completed", asset=asset_symbol, metric=metric, run_id=run.id, signals=len(signals))
        return {"status": "completed", "run_id": run.id, "horizon": horizon, "signals": len(signals)}

    except Exception as exc:
        db.rollback()
        log.error("forecast.failed", asset=asset_symbol, metric=metric, error=str(exc))
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()


def run_all_forecasts():
    """Run forecasts for all enabled assets and metrics."""
    from backend.core.config_loader import ConfigLoader

    assets = ConfigLoader.get_enabled_assets()
    metrics = ["total_supply", "price", "signal_score", "depeg_index", "concentration_score"]

    results = []
    for asset in assets:
        for metric in metrics:
            result = forecast_asset_metric(asset["symbol"], metric)
            results.append({"asset": asset["symbol"], "metric": metric, "status": result.get("status")})
            log.info("forecast.dispatched", asset=asset["symbol"], metric=metric, status=result.get("status"))

    return {"status": "completed", "tasks": len(results)}
