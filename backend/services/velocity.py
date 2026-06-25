"""Velocity and acceleration signals from 5-minute trend snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from database import AssetTrendSnapshot


def _fetch_raw_history(
    db: Session,
    *,
    asset_symbol: str,
    window_hours: int = 24,
    min_points: int = 6,
) -> tuple[list[datetime], list[float], list[int]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    rows = (
        db.query(AssetTrendSnapshot)
        .filter(
            AssetTrendSnapshot.asset_symbol == asset_symbol,
            AssetTrendSnapshot.timestamp >= cutoff,
        )
        .order_by(AssetTrendSnapshot.timestamp.asc())
        .all()
    )
    if len(rows) < min_points:
        return [], [], []
    timestamps: list[datetime] = []
    supplies: list[float] = []
    depeg_indices: list[int] = []
    for r in rows:
        if r.total_supply is not None and r.total_supply > 0:
            timestamps.append(r.timestamp)
            supplies.append(float(r.total_supply))
            depeg_indices.append(r.depeg_index)
    return timestamps, supplies, depeg_indices


def _window_bounds(timestamps: list[datetime], window_hours: float) -> list[int]:
    if not timestamps:
        return []
    cutoff = timestamps[-1] - timedelta(hours=window_hours)
    for i, ts in enumerate(timestamps):
        if ts >= cutoff:
            return [i, len(timestamps) - 1]
    return [0, len(timestamps) - 1]


def _pct_change(later: float, earlier: float) -> float | None:
    if earlier == 0:
        return None
    return ((later - earlier) / earlier) * 100.0


def compute_supply_velocity(
    db: Session,
    *,
    asset_symbol: str,
    window_hours: int = 24,
) -> dict[str, Any]:
    timestamps, supplies, depeg_indices = _fetch_raw_history(
        db, asset_symbol=asset_symbol, window_hours=window_hours
    )
    if len(timestamps) < 6:
        return {
            "asset_symbol": asset_symbol,
            "available": False,
            "note": "Insufficient history (need >=6 snapshots).",
        }

    latest_supply = supplies[-1]

    windows: list[tuple[str, float]] = [
        ("1h", 1.0),
        ("4h", 4.0),
        ("12h", 12.0),
        ("24h", 24.0),
    ]

    velocity: dict[str, float | None] = {}
    for label, hours in windows:
        bounds = _window_bounds(timestamps, hours)
        if bounds and bounds[0] < len(supplies):
            earlier_supply = supplies[bounds[0]]
            vel = _pct_change(latest_supply, earlier_supply)
            velocity[label] = vel
        else:
            velocity[label] = None

    prev_1h = supplies[-12] if len(supplies) >= 12 else supplies[0] if supplies else None
    prev_4h = supplies[-48] if len(supplies) >= 48 else supplies[0] if supplies else None
    acc_1h = None
    acc_4h = None
    if velocity.get("1h") is not None and prev_1h is not None and prev_1h != supplies[-1]:
        prev_vel = _pct_change(supplies[-1], prev_1h)
        if prev_vel is not None and velocity["1h"] is not None:
            acc_1h = velocity["1h"] - prev_vel
    if velocity.get("4h") is not None and prev_4h is not None and prev_4h != supplies[-1]:
        prev_vel = _pct_change(supplies[-1], prev_4h)
        if prev_vel is not None and velocity["4h"] is not None:
            acc_4h = velocity["4h"] - prev_vel

    return {
        "asset_symbol": asset_symbol,
        "available": True,
        "point_count": len(timestamps),
        "latest_supply": latest_supply,
        "velocity": velocity,
        "acceleration": {
            "1h": round(acc_1h, 4) if acc_1h is not None else None,
            "4h": round(acc_4h, 4) if acc_4h is not None else None,
        },
        "direction": (
            "contracting"
            if any(v is not None and v < -0.1 for v in velocity.values())
            else "expanding"
            if any(v is not None and v > 0.1 for v in velocity.values())
            else "stable"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def compute_depeg_velocity(
    db: Session,
    *,
    asset_symbol: str,
    window_hours: int = 24,
) -> dict[str, Any]:
    timestamps, _, depeg_indices = _fetch_raw_history(
        db, asset_symbol=asset_symbol, window_hours=window_hours
    )
    if len(depeg_indices) < 6:
        return {"available": False, "note": "Insufficient history."}

    latest_depeg = float(depeg_indices[-1])

    windows: list[tuple[str, int]] = [
        ("1h", 12),
        ("4h", 48),
        ("12h", 144),
    ]

    depeg_velocity: dict[str, float | None] = {}
    for label, lookback in windows:
        if len(depeg_indices) > lookback:
            earlier = float(depeg_indices[-(lookback + 1)])
            depeg_velocity[label] = latest_depeg - earlier
        else:
            depeg_velocity[label] = None

    return {
        "available": True,
        "latest_depeg_index": int(latest_depeg),
        "depeg_velocity": depeg_velocity,
    }


def supply_velocity_component(
    velocity: dict[str, float | None],
    acceleration: dict[str, float | None],
) -> tuple[int, dict[str, Any]]:
    score = 0
    details: dict[str, Any] = {}

    for label in ("1h", "4h", "12h", "24h"):
        vel = velocity.get(label)
        details[f"{label}_vel_pct"] = vel
        if vel is None:
            continue
        mag = abs(vel)
        if mag > 5:
            score += 20
        elif mag > 2:
            score += 10
        elif mag > 0.5:
            score += 5

    for label in ("1h", "4h"):
        acc = acceleration.get(label)
        details[f"{label}_accel"] = acc
        if acc is None:
            continue
        if abs(acc) > 3:
            score += 15
        elif abs(acc) > 1:
            score += 8

    return min(100, score), details
