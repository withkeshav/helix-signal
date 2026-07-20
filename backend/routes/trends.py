from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import AssetTrendSnapshot, ChainTrendSnapshot, get_db
from schemas import ChainTrendPointOut, ChainTrendResponseOut, ChainTrendSeriesOut, TrendPointOut, TrendResponseOut
from services.exports import trends_export
from signal_engine.core import get_asset_by_symbol
from utils import window_delta

from core.limiter import limiter
from core.api_auth import AuthContext, enforce_asset_allowed, enforce_window_history, require_read_open

router = APIRouter()

_ALLOWED_TREND_WINDOWS = frozenset({"6h", "24h", "7d", "30d", "90d"})


def _chain_trend_summary_dict(
    series: list[ChainTrendSeriesOut],
    *,
    window: str,
    now: datetime,
    total_points: int,
) -> dict[str, Any]:
    stamps: list[datetime] = []
    for s in series:
        for p in s.points:
            stamps.append(p.timestamp)
    stamps.sort()
    span_td = window_delta(window)
    window_seconds = max(span_td.total_seconds(), 1.0)
    window_hours = window_seconds / 3600.0
    axis_min = now - span_td
    axis_max = now
    wl = window.strip().lower()
    if not stamps:
        return {
            "series_count": len(series),
            "total_points": total_points,
            "selected_window": wl,
            "window_span_hours": round(window_hours, 4),
            "first_timestamp": None,
            "latest_timestamp": None,
            "available_duration_minutes": None,
            "low_data": True,
            "low_data_reason": "No chain trend snapshots in this window yet.",
            "chart_axis_min_utc": axis_min,
            "chart_axis_max_utc": axis_max,
        }
    first_ts, last_ts = stamps[0], stamps[-1]
    avail_seconds = max((last_ts - first_ts).total_seconds(), 0.0)
    avail_minutes = avail_seconds / 60.0
    coverage = avail_seconds / window_seconds
    low_data = total_points < 2 or coverage < 0.92
    reason: str | None = None
    if total_points < 2:
        reason = (
            "Need at least two chain snapshots to draw reliable trend lines. "
            "History collection started recently inside the selected window."
        )
    elif coverage < 0.92:
        hrs = int(avail_seconds // 3600)
        mins = int((avail_seconds % 3600) // 60)
        dur_txt = f"{hrs}h {mins}m" if hrs else (f"{mins} min" if mins else "under 1 min")
        reason = (
            f"History collection started recently. Showing about {dur_txt} of available data "
            f"inside the selected {wl} window."
        )
    return {
        "series_count": len(series),
        "total_points": total_points,
        "selected_window": wl,
        "window_span_hours": round(window_hours, 4),
        "first_timestamp": first_ts,
        "latest_timestamp": last_ts,
        "available_duration_minutes": round(avail_minutes, 3),
        "low_data": low_data,
        "low_data_reason": reason,
        "chart_axis_min_utc": axis_min,
        "chart_axis_max_utc": axis_max,
    }


@router.get("/trends", response_model=TrendResponseOut, dependencies=[Depends(require_read_open("trends:read"))])
@limiter.limit("60/minute")
def trends(
    request: Request,
    asset: str,
    window: str = Query("7d"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_read_open("trends:read")),
) -> TrendResponseOut:
    w = window.strip().lower()
    if w not in _ALLOWED_TREND_WINDOWS:
        raise HTTPException(status_code=400, detail="Invalid window. Use 6h, 24h, 7d, 30d, or 90d.")
    enforce_window_history(auth, w)
    sym = asset.strip().upper()
    enforce_asset_allowed(auth, sym)
    selected = get_asset_by_symbol(sym)
    if selected is None or not bool(selected.get("enabled")):
        raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")

    now = datetime.now(timezone.utc)
    cutoff = now - window_delta(w)
    agg_rows = None
    if w in ("30d", "90d"):
        from services.v4_series_reads import fetch_asset_trend_history

        agg_rows = fetch_asset_trend_history(db, asset_symbol=sym, window=w)
    if agg_rows is not None:
        points = [
            TrendPointOut(
                timestamp=r["timestamp"],
                total_supply=r.get("total_supply"),
                price=r.get("price"),
                depeg_index=int(r.get("depeg_index") or 0),
                signal_score=int(r.get("signal_score") or 0),
                signal_band=str(r.get("signal_band") or "normal"),
                concentration_score=int(r.get("concentration_score") or 0),
                data_confidence=str(r.get("data_confidence_label") or "Low"),
            )
            for r in agg_rows
        ]
    else:
        rows = (
            db.execute(
                select(AssetTrendSnapshot)
                .where(AssetTrendSnapshot.asset_symbol == sym, AssetTrendSnapshot.timestamp >= cutoff)
                .order_by(AssetTrendSnapshot.timestamp.asc())
            ).scalars().all()
        )
        points = [
            TrendPointOut(
                timestamp=r.timestamp,
                total_supply=r.total_supply,
                price=r.price,
                depeg_index=int(r.depeg_index),
                signal_score=int(r.signal_score),
                signal_band=str(r.signal_band),
                concentration_score=int(r.concentration_score),
                data_confidence=str(r.data_confidence_label),
            )
            for r in rows
        ]

    from services.dashboard import build_trend_summary as _build_ts

    summary = _build_ts(points, window=w, now=now)
    return TrendResponseOut(
        asset=sym,
        window=w,
        generated_at=now,
        points=points,
        summary=summary,
    )


@router.get("/trends/export", dependencies=[Depends(require_read_open("export:read"))])
@limiter.limit("30/minute")
def trends_export_route(
    request: Request,
    asset: str,
    window: str = Query("7d"),
    format: str = Query("csv", alias="format"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_read_open("export:read")),
):
    w = window.strip().lower()
    enforce_window_history(auth, w)
    enforce_asset_allowed(auth, asset)
    return trends_export(db, asset=asset, window=window, fmt=format)


@router.get("/trends/chains", response_model=ChainTrendResponseOut, dependencies=[Depends(require_read_open("trends:read"))])
@limiter.limit("60/minute")
def trends_chains(
    request: Request,
    asset: str,
    window: str = Query("7d"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_read_open("trends:read")),
) -> ChainTrendResponseOut:
    w = window.strip().lower()
    if w not in _ALLOWED_TREND_WINDOWS:
        raise HTTPException(status_code=400, detail="Invalid window. Use 6h, 24h, 7d, 30d, or 90d.")
    enforce_window_history(auth, w)
    sym = asset.strip().upper()
    enforce_asset_allowed(auth, sym)
    selected = get_asset_by_symbol(sym)
    if selected is None or not bool(selected.get("enabled")):
        raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")

    now = datetime.now(timezone.utc)
    cutoff = now - window_delta(w)
    rows = (
        db.execute(
            select(ChainTrendSnapshot)
            .where(ChainTrendSnapshot.asset_symbol == sym, ChainTrendSnapshot.timestamp >= cutoff)
            .order_by(ChainTrendSnapshot.timestamp.asc())
        ).scalars().all()
    )
    grouped: dict[str, dict] = defaultdict(lambda: {"chain_name": "", "points": []})
    for r in rows:
        g = grouped[r.chain_key]
        if not g["chain_name"]:
            g["chain_name"] = r.chain_name
        g["points"].append(
            ChainTrendPointOut(
                timestamp=r.timestamp,
                supply=r.supply,
                supply_share_pct=r.supply_share_pct,
                chain_tvl=r.chain_tvl,
                chain_signal_score=int(r.chain_signal_score),
                chain_signal_band=str(r.chain_signal_band),
                data_confidence_score=int(r.data_confidence_score),
            )
        )
    series: list[ChainTrendSeriesOut] = []
    for key in sorted(grouped.keys()):
        blob = grouped[key]
        pts = sorted(blob["points"], key=lambda p: p.timestamp)
        series.append(ChainTrendSeriesOut(chain_key=key, chain_name=blob["chain_name"], points=pts))
    total_points = sum(len(s.points) for s in series)
    summary = _chain_trend_summary_dict(series, window=w, now=now, total_points=total_points)
    return ChainTrendResponseOut(
        asset=sym,
        window=w,
        generated_at=now,
        series=series,
        summary=summary,
    )
