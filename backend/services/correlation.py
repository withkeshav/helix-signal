"""Cross-asset correlation matrix for stablecoin metrics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from database import AssetTrendSnapshot
from signal_engine.core import load_enabled_assets


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 5:
        return None
    a, b = a[:n], b[:n]
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    num = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
    den_a = sum((x - mean_a) ** 2 for x in a) ** 0.5
    den_b = sum((x - mean_b) ** 2 for x in b) ** 0.5
    if den_a == 0 or den_b == 0:
        return None
    return round(num / (den_a * den_b), 4)


def compute_cross_asset_matrix(
    db: Session,
    *,
    window_days: int = 7,
    metrics: tuple[str, ...] = ("signal_score", "depeg_index"),
) -> dict[str, Any]:
    """Weekly-style correlation between tracked stablecoins on supply/peg/concentration trends."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    assets = [a["symbol"].upper() for a in load_enabled_assets() if a.get("enabled")]
    series: dict[str, dict[str, list[float]]] = {sym: {m: [] for m in metrics} for sym in assets}

    for sym in assets:
        rows = (
            db.query(AssetTrendSnapshot)
            .filter(AssetTrendSnapshot.asset_symbol == sym, AssetTrendSnapshot.timestamp >= cutoff)
            .order_by(AssetTrendSnapshot.timestamp.asc())
            .all()
        )
        for r in rows:
            for m in metrics:
                val = getattr(r, m, None)
                if val is not None:
                    series[sym][m].append(float(val))

    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(assets):
        for b in assets[i + 1 :]:
            for metric in metrics:
                coeff = _pearson(series[a][metric], series[b][metric])
                if coeff is None:
                    continue
                pairs.append({
                    "asset_a": a,
                    "asset_b": b,
                    "metric": metric,
                    "coefficient": coeff,
                    "direction": "positive" if coeff >= 0 else "negative",
                    "window_days": window_days,
                })

    return {
        "available": bool(pairs),
        "window_days": window_days,
        "assets": assets,
        "pairs": pairs,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
