"""Walk-forward backtest on trend snapshots (transform.md §4.4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import AssetTrendSnapshot


def walk_forward_backtest(
    db: Session,
    *,
    asset_symbol: str,
    metric: str = "price",
    train_points: int = 48,
    test_points: int = 12,
    step_points: int = 12,
    max_folds: int = 5,
) -> dict[str, Any]:
    """Rolling persistence forecast vs actuals on stored trend history."""
    sym = asset_symbol.upper()
    rows = (
        db.execute(
            select(AssetTrendSnapshot)
            .where(AssetTrendSnapshot.asset_symbol == sym)
            .order_by(AssetTrendSnapshot.timestamp.asc())
        )
        .scalars()
        .all()
    )
    if len(rows) < train_points + test_points + 2:
        return {
            "asset": sym,
            "metric": metric,
            "folds": [],
            "summary": None,
            "note": "insufficient_history",
        }

    def _value(row: AssetTrendSnapshot) -> float | None:
        if metric == "price":
            return float(row.price) if row.price is not None else None
        if metric in {"peg", "depeg_index"}:
            return float(row.depeg_index) if row.depeg_index is not None else None
        if metric in {"supply", "total_supply"}:
            return float(row.total_supply) if row.total_supply is not None else None
        if metric == "signal_score":
            return float(row.signal_score) if row.signal_score is not None else None
        return None

    series = [(r.timestamp, _value(r)) for r in rows if _value(r) is not None]
    if len(series) < train_points + test_points + 2:
        return {
            "asset": sym,
            "metric": metric,
            "folds": [],
            "summary": None,
            "note": "insufficient_valid_points",
        }

    folds: list[dict[str, Any]] = []
    start = 0
    while start + train_points + test_points <= len(series) and len(folds) < max_folds:
        train = series[start : start + train_points]
        test = series[start + train_points : start + train_points + test_points]
        baseline = train[-1][1]
        errors = [abs((actual - baseline)) for _, actual in test]
        mae = sum(errors) / len(errors)
        mean_actual = sum(abs(v) for _, v in test) / len(test)
        mape = (mae / mean_actual * 100) if mean_actual > 0 else None
        folds.append({
            "fold": len(folds) + 1,
            "train_end": train[-1][0].isoformat() if train[-1][0] else None,
            "test_end": test[-1][0].isoformat() if test[-1][0] else None,
            "matched_points": len(test),
            "mae": round(mae, 6),
            "mape": round(mape, 2) if mape is not None else None,
            "model": "walk_forward_persistence",
            "target_metric": metric,
            "horizon": test_points,
        })
        start += step_points

    summary = None
    if folds:
        summary = {
            "fold_count": len(folds),
            "mean_mae": round(sum(f["mae"] for f in folds) / len(folds), 6),
            "mean_mape": round(
                sum(f["mape"] for f in folds if f["mape"] is not None)
                / max(1, sum(1 for f in folds if f["mape"] is not None)),
                2,
            )
            if any(f["mape"] is not None for f in folds)
            else None,
        }

    return {
        "asset": sym,
        "metric": metric,
        "folds": folds,
        "summary": summary,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
