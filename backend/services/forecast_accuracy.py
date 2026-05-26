from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from structlog import get_logger

from database import ForecastPoint, ForecastRun, AssetTrendSnapshot

log = get_logger(__name__)


def compute_forecast_accuracy(
    db: Session, *, asset_symbol: str, max_runs: int = 10
) -> dict[str, Any]:
    asset_key = asset_symbol.upper()
    runs = (
        db.query(ForecastRun)
        .filter(ForecastRun.asset_symbol == asset_key)
        .order_by(ForecastRun.generated_at.desc())
        .limit(max_runs)
        .all()
    )
    results: list[dict[str, Any]] = []
    for run in runs:
        points = (
            db.query(ForecastPoint)
            .filter(ForecastPoint.run_id == run.id)
            .order_by(ForecastPoint.horizon_step.asc())
            .all()
        )
        if not points:
            continue
        first_ts = points[0].forecast_timestamp
        last_ts = points[-1].forecast_timestamp
        if not first_ts or not last_ts:
            continue
        actuals = (
            db.query(AssetTrendSnapshot)
            .filter(
                AssetTrendSnapshot.asset_symbol == asset_key,
                AssetTrendSnapshot.timestamp >= first_ts,
                AssetTrendSnapshot.timestamp <= last_ts,
            )
            .order_by(AssetTrendSnapshot.timestamp.asc())
            .all()
        )
        if not actuals:
            continue
        errors: list[float] = []
        abs_errors: list[float] = []
        matched = 0
        actual_magnitudes: list[float] = []
        for p in points:
            if not p.forecast_timestamp or p.q50 is None:
                continue
            pt_s = p.forecast_timestamp.timestamp()
            closest = min(actuals, key=lambda a: abs(a.timestamp.timestamp() - pt_s) if a.timestamp else float("inf"))
            if not closest.timestamp:
                continue
            diff_sec = abs(closest.timestamp.timestamp() - pt_s)
            if diff_sec > 7200:
                continue
            actual_val: float | None = None
            if run.target_metric in {"peg", "depeg_index"}:
                actual_val = float(closest.depeg_index) if closest.depeg_index is not None else None
            elif run.target_metric == "price":
                actual_val = float(closest.price) if closest.price is not None else None
            elif run.target_metric in {"supply", "total_supply"}:
                actual_val = float(closest.total_supply) if closest.total_supply is not None else None
            elif run.target_metric == "signal_score":
                actual_val = float(closest.signal_score) if closest.signal_score is not None else None
            if actual_val is None:
                continue
            err = actual_val - float(p.q50)
            errors.append(err)
            abs_errors.append(abs(err))
            actual_magnitudes.append(abs(actual_val))
            matched += 1
        if matched < 2:
            continue
        mae = sum(abs_errors) / matched
        mean_actual = sum(actual_magnitudes) / matched
        mape = (mae / mean_actual * 100) if mean_actual > 0 else None
        results.append({
            "run_id": run.id,
            "model": run.model_name,
            "target_metric": run.target_metric,
            "horizon": run.horizon,
            "generated_at": run.generated_at.isoformat() if run.generated_at else None,
            "matched_points": matched,
            "mae": round(mae, 4),
            "mape": round(mape, 2) if mape is not None else None,
            "bias": round(sum(errors) / matched, 4),
        })
    return {
        "asset": asset_key,
        "runs_evaluated": len(results),
        "results": results,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
