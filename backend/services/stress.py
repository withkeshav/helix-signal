"""Stress leaderboard — per-chain supply velocity and ranking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import AssetChainSnapshot


def build_stress_leaderboard(
    db: Session,
    *,
    asset_symbol: str,
    top_n: int = 10,
) -> dict[str, Any]:
    chains = (
        db.execute(select(AssetChainSnapshot).where(AssetChainSnapshot.asset_symbol == asset_symbol))
        .scalars()
        .all()
    )
    if not chains:
        return {
            "asset_symbol": asset_symbol,
            "available": False,
            "note": "No chain data found.",
        }

    rows: list[dict[str, Any]] = []
    for c in chains:
        cur = float(c.supply_current or 0.0)
        prev_day = float(c.supply_prev_day or 0.0)
        prev_week = float(c.supply_prev_week or 0.0)

        vel_24h = None
        if prev_day > 0:
            vel_24h = ((cur - prev_day) / prev_day) * 100.0

        vel_7d = None
        if prev_week > 0:
            vel_7d = ((cur - prev_week) / prev_week) * 100.0

        stress_score = 0
        if vel_24h is not None:
            stress_score += abs(vel_24h) * 2
        if vel_7d is not None:
            stress_score += abs(vel_7d)

        rows.append({
            "chain_name": c.chain_name,
            "supply_current": cur,
            "velocity_24h_pct": round(vel_24h, 4) if vel_24h is not None else None,
            "velocity_7d_pct": round(vel_7d, 4) if vel_7d is not None else None,
            "direction": (
                "inflow" if (vel_24h or 0) > 0.1
                else "outflow" if (vel_24h or 0) < -0.1
                else "stable"
            ),
            "stress_score": round(stress_score, 2),
        })

    rows.sort(key=lambda r: r["stress_score"], reverse=True)

    return {
        "asset_symbol": asset_symbol,
        "available": True,
        "chain_count": len(rows),
        "leaderboard": rows[:top_n],
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
