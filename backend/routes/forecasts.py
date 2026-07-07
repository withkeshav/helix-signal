from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.limiter import limiter
from database import ForecastPoint, ForecastRun, AssetTrendSnapshot, get_db

router = APIRouter()


@router.get("/forecasts")
@limiter.limit("60/minute")
def list_forecasts(
    request: Request,
    asset: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    asset_key = asset.upper()
    runs = (
        db.execute(
            select(ForecastRun)
            .where(ForecastRun.asset_symbol == asset_key)
            .order_by(ForecastRun.generated_at.desc())
            .limit(5)
        ).scalars().all()
    )
    forecasts = []
    forecast_points = {}
    for run in runs:
        points = (
            db.execute(
                select(ForecastPoint)
                .where(ForecastPoint.run_id == run.id)
                .order_by(ForecastPoint.horizon_step.asc())
            ).scalars().all()
        )
        serialized = [
            {
                "timestamp": p.forecast_timestamp.timestamp() * 1000 if p.forecast_timestamp else None,
                "q10": p.q10,
                "q50": p.q50,
                "q90": p.q90,
            }
            for p in points
        ]
        forecasts.append({
            "run_id": run.id,
            "model": run.model_name,
            "metric": run.target_metric,
            "horizon": run.horizon,
            "generated_at": run.generated_at.isoformat() if run.generated_at else None,
            "points": serialized,
        })
        if run.target_metric not in forecast_points:
            forecast_points[run.target_metric] = serialized

    for pref in ("depeg_index", "price"):
        if pref in forecast_points:
            forecast_points["peg"] = forecast_points[pref]
            break
    if "total_supply" in forecast_points:
        forecast_points["supply"] = forecast_points["total_supply"]

    snapshots = (
        db.execute(
            select(AssetTrendSnapshot)
            .where(AssetTrendSnapshot.asset_symbol == asset_key)
            .order_by(AssetTrendSnapshot.timestamp.desc())
            .limit(288)
        ).scalars().all()
    )
    historical_by_metric: dict[str, list[dict]] = {}
    for snap in reversed(snapshots):
        ts = snap.timestamp.timestamp() * 1000 if snap.timestamp else None
        for metric, val in [
            ("peg", snap.depeg_index),
            ("supply", snap.total_supply),
        ]:
            if val is not None:
                historical_by_metric.setdefault(metric, []).append({"timestamp": ts, "value": val})

    return {
        "forecasts": forecasts,
        "forecast_points": forecast_points,
        "historical": historical_by_metric,
        "asset": asset_key,
    }
