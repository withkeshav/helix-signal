"""Lightweight forecast writer — linear trend extrapolate from AssetTrendSnapshot.

Not TimesFM: fills forecast_runs/points so Market charts have real data without
a paid model dependency. Scheduler-safe (never raises).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from structlog import get_logger

from database import AssetTrendSnapshot, ForecastPoint, ForecastRun

log = get_logger(__name__)

MODEL_NAME = "helix_linear_trend"
MODEL_VERSION = "1.0"


def _series(db: Session, asset: str, *, limit: int = 96) -> list[AssetTrendSnapshot]:
    rows = (
        db.execute(
            select(AssetTrendSnapshot)
            .where(AssetTrendSnapshot.asset_symbol == asset.upper())
            .order_by(desc(AssetTrendSnapshot.timestamp))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))


def _extrapolate(values: list[float], horizon: int) -> list[float]:
    if len(values) < 2:
        last = values[-1] if values else 0.0
        return [last] * horizon
    # Simple slope over last window
    n = min(len(values), 24)
    window = values[-n:]
    x_mean = (n - 1) / 2.0
    y_mean = sum(window) / n
    num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(window))
    den = sum((i - x_mean) ** 2 for i in range(n)) or 1.0
    slope = num / den
    last = window[-1]
    return [last + slope * (step + 1) for step in range(horizon)]


def _write_metric(
    db: Session,
    *,
    asset: str,
    metric: str,
    history: list[tuple[datetime, float]],
    horizon: int,
    frequency: str,
    step_delta: timedelta,
) -> bool:
    if len(history) < 2:
        return False
    now = datetime.now(timezone.utc)
    values = [v for _, v in history]
    forecasts = _extrapolate(values, horizon)
    last_ts = history[-1][0]
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=timezone.utc)

    run = ForecastRun(
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        target_metric=metric,
        asset_symbol=asset.upper(),
        chain_key=None,
        input_start=history[0][0],
        input_end=history[-1][0],
        horizon=horizon,
        frequency=frequency,
        status="completed",
        latency_ms=0,
        input_points=len(history),
        error=None,
        generated_at=now,
    )
    db.add(run)
    db.flush()
    for step, point in enumerate(forecasts):
        ft = last_ts + step_delta * (step + 1)
        # Wide bands from residual scatter
        resid = abs(values[-1] - values[-2]) if len(values) >= 2 else abs(point) * 0.01
        band = max(resid, abs(point) * 0.002, 1e-6)
        db.add(
            ForecastPoint(
                run_id=run.id,
                asset_symbol=asset.upper(),
                chain_key=None,
                target_metric=metric,
                horizon_step=step + 1,
                forecast_timestamp=ft,
                point_forecast=float(point),
                q10=float(point - 1.28 * band),
                q50=float(point),
                q90=float(point + 1.28 * band),
            )
        )
    return True


def run_forecast_job(db: Session) -> dict[str, Any]:
    """Write peg (24h hourly) + supply (7d daily-ish) forecasts for enabled assets."""
    try:
        from signal_engine.core import load_enabled_assets

        assets = [
            str(a.get("symbol", "")).upper()
            for a in load_enabled_assets(db)
            if a.get("symbol")
        ] or ["USDT"]
    except Exception:
        assets = ["USDT"]

    written = 0
    errors = 0
    for asset in assets[:6]:
        try:
            snaps = _series(db, asset)
            peg_hist = [
                (s.timestamp, float(s.depeg_index))
                for s in snaps
                if s.depeg_index is not None and s.timestamp is not None
            ]
            supply_hist = [
                (s.timestamp, float(s.total_supply))
                for s in snaps
                if s.total_supply is not None and s.timestamp is not None
            ]
            ok = False
            if _write_metric(
                db,
                asset=asset,
                metric="depeg_index",
                history=peg_hist,
                horizon=24,
                frequency="1h",
                step_delta=timedelta(hours=1),
            ):
                ok = True
            if _write_metric(
                db,
                asset=asset,
                metric="total_supply",
                history=supply_hist,
                horizon=7,
                frequency="1d",
                step_delta=timedelta(days=1),
            ):
                ok = True
            if ok:
                written += 1
                db.commit()
            else:
                db.rollback()
        except Exception:
            errors += 1
            log.exception("forecast_writer.asset_failed", asset=asset)
            try:
                db.rollback()
            except Exception:
                pass

    return {
        "status": "ok",
        "assets_written": written,
        "errors": errors,
        "model": MODEL_NAME,
    }
