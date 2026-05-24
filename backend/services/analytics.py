"""Analytics service — correlations, pattern detection, and cross-metric analysis."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session
from structlog import get_logger

from database import AssetTrendSnapshot
from backend.core.database_manager import dbm

log = get_logger(__name__)

_METRIC_FIELDS = ("total_supply", "price", "depeg_index", "signal_score", "concentration_score")


def _fetch_history(
    db: Session, *, asset_symbol: str, window_days: int = 30
) -> tuple[dict[str, list[float]], list[datetime]]:
    rows = dbm.get_trend_history(db, asset_symbol=asset_symbol, window_days=window_days)
    if rows:
        series: dict[str, list[float]] = {f: [] for f in _METRIC_FIELDS}
        timestamps: list[datetime] = []
        for r in rows:
            ts = r["timestamp"]
            if isinstance(ts, datetime):
                timestamps.append(ts)
            series["total_supply"].append(float(r.get("total_supply") or 0.0))
            series["price"].append(float(r.get("price") or 1.0))
            series["depeg_index"].append(float(r.get("depeg_index") or 0))
            series["signal_score"].append(float(r.get("signal_score") or 0))
            series["concentration_score"].append(float(r.get("concentration_score") or 0))
        return series, timestamps

    return {f: [] for f in _METRIC_FIELDS}, []


def _pearson(x: list[float], y: list[float]) -> float:
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    x = x[:n]
    y = y[:n]
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    dy = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def compute_correlations(db: Session, *, asset_symbol: str, window_days: int = 30) -> dict[str, Any]:
    series, timestamps = _fetch_history(db, asset_symbol=asset_symbol, window_days=window_days)
    fields = list(_METRIC_FIELDS)

    matrix: dict[str, dict[str, float]] = {}
    for f1 in fields:
        matrix[f1] = {}
        for f2 in fields:
            matrix[f1][f2] = round(_pearson(series[f1], series[f2]), 4)

    pair_results: list[dict[str, Any]] = []
    for i in range(len(fields)):
        for j in range(i + 1, len(fields)):
            val = matrix[fields[i]][fields[j]]
            strength = (
                "strong" if abs(val) >= 0.70
                else "moderate" if abs(val) >= 0.40
                else "weak"
            )
            pair_results.append({
                "metric_a": fields[i],
                "metric_b": fields[j],
                "coefficient": val,
                "strength": strength,
                "direction": "positive" if val > 0 else "negative" if val < 0 else "none",
            })

    pair_results.sort(key=lambda p: abs(p["coefficient"]), reverse=True)

    return {
        "asset": asset_symbol,
        "window_days": window_days,
        "point_count": len(timestamps),
        "matrix": matrix,
        "pairs": pair_results,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def detect_patterns(db: Session, *, asset_symbol: str, window_days: int = 30) -> dict[str, Any]:
    series, timestamps = _fetch_history(db, asset_symbol=asset_symbol, window_days=window_days)
    if len(timestamps) < 20:
        return {
            "asset": asset_symbol,
            "status": "insufficient_data",
            "point_count": len(timestamps),
            "patterns": [],
        }

    patterns: list[dict[str, Any]] = []

    for metric in _METRIC_FIELDS:
        values = series[metric]
        if len(values) < 20:
            continue

        # Trend direction: simple linear regression slope
        n = len(values)
        xs = list(range(n))
        mx = sum(xs) / n
        my = sum(values) / n
        num = sum((xs[i] - mx) * (values[i] - my) for i in range(n))
        den = sum((xi - mx) ** 2 for xi in xs)
        slope = num / den if den != 0 else 0.0

        # Volatility: coefficient of variation
        if my != 0:
            std = math.sqrt(sum((v - my) ** 2 for v in values) / n)
            cv = std / abs(my) if abs(my) > 1e-9 else 0.0
        else:
            cv = 0.0

        trend_dir = "rising" if slope > 0 else "falling" if slope < 0 else "stable"
        vol_label = "high" if cv > 0.05 else "moderate" if cv > 0.01 else "low"

        # Day-of-week seasonality check
        dow_buckets: dict[int, list[float]] = defaultdict(list)
        for ts, v in zip(timestamps, values):
            dow_buckets[ts.weekday()].append(v)
        dow_means = {}
        for dow, vals in dow_buckets.items():
            if vals:
                dow_means[dow] = sum(vals) / len(vals)

        seasonality_detected = False
        if len(dow_means) >= 3:
            dow_values = list(dow_means.values())
            dow_range = max(dow_values) - min(dow_values)
            avg = sum(dow_values) / len(dow_values) if dow_values else 0
            if avg > 1e-9 and dow_range / avg > 0.05:
                seasonality_detected = True

        patterns.append({
            "metric": metric,
            "trend": trend_dir,
            "slope_per_step": round(slope, 6),
            "volatility": vol_label,
            "coefficient_of_variation": round(cv, 4),
            "seasonality_detected": seasonality_detected,
            "dow_means": {str(k): round(v, 4) for k, v in dow_means.items()} if len(dow_means) >= 3 else None,
        })

    return {
        "asset": asset_symbol,
        "window_days": window_days,
        "point_count": len(timestamps),
        "patterns": patterns,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
