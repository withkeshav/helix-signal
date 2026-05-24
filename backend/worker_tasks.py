"""Celery tasks: refresh, predictive inference, optional AI enrichment."""

from __future__ import annotations

from celery_app import celery_app
from database import SessionLocal
from signal_engine.core import refresh_chain_data


@celery_app.task(name="helix.refresh_chain_data")
def task_refresh_chain_data() -> str:
    db = SessionLocal()
    try:
        refresh_chain_data(db)
        return "ok"
    finally:
        db.close()


@celery_app.task(name="helix.predictive_inference")
def task_predictive_inference(asset_symbol: str = "USDT") -> dict:
    from services.predictive import run_predictive_bundle

    db = SessionLocal()
    try:
        return run_predictive_bundle(db, asset_symbol=asset_symbol, log_to_mlflow=True)
    finally:
        db.close()


@celery_app.task(name="helix.ai_enrich")
def task_ai_enrich(feature: str, context: dict) -> dict:
    from services.ai_router import enrich_with_ai

    return enrich_with_ai(feature=feature, context=context)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, name="helix.forecast_asset_metric")
def forecast_asset_metric(self, asset_symbol: str, metric: str, horizon: int = 24):
    """Forecast a single asset metric using TimesFM."""
    from datetime import datetime, timedelta, timezone

    from database import AssetTrendSnapshot, ForecastPoint, ForecastRun

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

        _ALLOWED_METRICS = frozenset({"total_supply", "price", "signal_score", "depeg_index", "concentration_score"})
        if metric not in _ALLOWED_METRICS:
            return {"status": "skipped", "reason": "invalid_metric", "metric": metric}
        values = [getattr(r, metric) for r in rows if getattr(r, metric) is not None]
        timestamps = [r.timestamp.isoformat() for r in rows if getattr(r, metric) is not None]

        if len(values) < 10:
            return {"status": "skipped", "reason": "insufficient_values", "points": len(values)}

        from backend.ml_models.registry import get_model_service

        timesfm = get_model_service("timesfm")
        if timesfm is None:
            return {"status": "skipped", "reason": "timesfm_unavailable"}

        result = timesfm.forecast(
            series_id=f"{asset_symbol}_{metric}",
            values=values,
            timestamps=timestamps,
            horizon=horizon,
        )

        import json

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

        from services.forecast_signals import evaluate_forecast_risk
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

        return {"status": "completed", "run_id": run.id, "horizon": horizon, "signals": len(signals)}

    except Exception as exc:
        db.rollback()
        self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(name="helix.run_all_forecasts")
def run_all_forecasts():
    """Run forecasts for all enabled assets and metrics."""
    from backend.core.config_loader import ConfigLoader

    assets = ConfigLoader.get_enabled_assets()
    metrics = ["total_supply", "price", "signal_score", "depeg_index", "concentration_score"]

    results = []
    for asset in assets:
        for metric in metrics:
            task = forecast_asset_metric.delay(asset["symbol"], metric)
            results.append({"asset": asset["symbol"], "metric": metric, "task_id": task.id})

    return {"status": "dispatched", "tasks": len(results)}
