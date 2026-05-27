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


def detect_regime(
    db: Session,
    *,
    asset_symbol: str,
    window_hours: int = 48,
) -> dict[str, Any]:
    """Three-state regime classifier: stable / elevated / crisis.

    Uses composite signal score, depeg index, and supply velocity to
    determine the current risk regime and how long it has been active.
    """
    series, timestamps = _fetch_history(db, asset_symbol=asset_symbol, window_days=max(1, window_hours // 24))
    if len(timestamps) < 6:
        return {
            "asset": asset_symbol,
            "available": False,
            "note": "Insufficient history (need >=6 points).",
        }

    scores = series["signal_score"]
    depeg = series["depeg_index"]
    supplies = series["total_supply"]

    def _classify(sig: float, dep: float, sup: float | None) -> str:
        if sig >= 70 or dep >= 85:
            return "crisis"
        if sig >= 40 or dep >= 60:
            return "elevated"
        return "stable"

    regime_series: list[str] = []
    for i in range(len(timestamps)):
        sup = supplies[i] if i < len(supplies) else None
        regime_series.append(_classify(scores[i], depeg[i], sup))

    current = regime_series[-1] if regime_series else "stable"

    duration_hours = 0
    for i in range(len(regime_series) - 2, -1, -1):
        if regime_series[i] == current:
            duration_hours += (timestamps[i + 1] - timestamps[i]).total_seconds() / 3600
        else:
            break

    prev = "stable"
    for r in reversed(regime_series[:-1]):
        if r != current:
            prev = r
            break

    transitions = 0
    for i in range(1, len(regime_series)):
        if regime_series[i] != regime_series[i - 1]:
            transitions += 1

    return {
        "asset": asset_symbol,
        "available": True,
        "current_regime": current,
        "previous_regime": prev,
        "duration_hours": round(duration_hours, 1),
        "transitions_48h": transitions,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def cross_asset_rotation(
    db: Session,
    *,
    asset_symbols: list[str],
    window_days: int = 30,
) -> dict[str, Any]:
    """Detect supply rotation between stablecoin assets.

    Computes rolling correlation of total supply changes between pairs
    of assets to identify "flight to safety" or dominance shifts.
    """
    if len(asset_symbols) < 2:
        return {
            "available": False,
            "note": "Need at least 2 assets for cross-asset comparison.",
        }

    asset_data: dict[str, tuple[list[float], list[datetime]]] = {}
    for sym in asset_symbols:
        series, timestamps = _fetch_history(db, asset_symbol=sym.upper(), window_days=window_days)
        if len(timestamps) >= 10:
            asset_data[sym.upper()] = (series["total_supply"], timestamps)

    if len(asset_data) < 2:
        return {
            "available": False,
            "note": "Insufficient data for one or more assets.",
        }

    pairs: list[dict[str, Any]] = []
    symbols = list(asset_data.keys())
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            sa = symbols[i]
            sb = symbols[j]
            sup_a, _ = asset_data[sa]
            sup_b, _ = asset_data[sb]
            corr = _pearson(sup_a, sup_b)

            latest_a = sup_a[-1] if sup_a else 0
            latest_b = sup_b[-1] if sup_b else 0
            prev_a = sup_a[0] if len(sup_a) > 1 else latest_a
            prev_b = sup_b[0] if len(sup_b) > 1 else latest_b
            chg_a = _pct_change(latest_a, prev_a) if prev_a != 0 else None
            chg_b = _pct_change(latest_b, prev_b) if prev_b != 0 else None

            dominance_shift = None
            if chg_a is not None and chg_b is not None:
                if chg_a > 2 and chg_b < -1:
                    dominance_shift = f"{sa}_gaining_on_{sb}"
                elif chg_b > 2 and chg_a < -1:
                    dominance_shift = f"{sb}_gaining_on_{sa}"

            pairs.append({
                "asset_a": sa,
                "asset_b": sb,
                "correlation_7d": round(corr, 4),
                "supply_change_a_pct": round(chg_a, 4) if chg_a is not None else None,
                "supply_change_b_pct": round(chg_b, 4) if chg_b is not None else None,
                "dominance_shift": dominance_shift,
            })

    return {
        "available": True,
        "point_count": min(len(v[0]) for v in asset_data.values()),
        "pairs": pairs,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _pct_change(later: float, earlier: float) -> float:
    if earlier == 0:
        return 0.0
    return ((later - earlier) / earlier) * 100.0
