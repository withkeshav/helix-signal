from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from schemas import AssetConfigOut, DashboardResponse, TrendPointOut, TrendSummaryOut
from services.dashboard import build_dashboard_response
from services.cache import get_or_build_dashboard
from signal_engine.core import get_asset_by_symbol, load_enabled_assets
from utils import window_delta

from backend.core.limiter import limiter

router = APIRouter()


def _build_trend_summary(points: list[TrendPointOut], *, window: str, now: datetime) -> TrendSummaryOut:
    span_td = window_delta(window)
    window_seconds = max(span_td.total_seconds(), 1.0)
    window_hours = window_seconds / 3600.0
    axis_min = now - span_td
    axis_max = now
    wl = window.strip().lower()

    n = len(points)
    if n == 0:
        return TrendSummaryOut(
            point_count=0,
            supply_change_abs=None,
            supply_change_pct=None,
            score_change=None,
            max_depeg_index=None,
            latest_band=None,
            selected_window=wl,
            window_span_hours=round(window_hours, 4),
            first_timestamp=None,
            latest_timestamp=None,
            available_duration_minutes=None,
            low_data=True,
            low_data_reason="No trend snapshots in this window yet. Run refreshes to collect forward history.",
            chart_axis_min_utc=axis_min,
            chart_axis_max_utc=axis_max,
        )

    first, last = points[0], points[-1]
    first_ts = first.timestamp
    last_ts = last.timestamp
    avail_seconds = max((last_ts - first_ts).total_seconds(), 0.0)
    avail_minutes = avail_seconds / 60.0
    coverage = avail_seconds / window_seconds

    supply_abs = None
    supply_pct = None
    if first.total_supply is not None and last.total_supply is not None:
        supply_abs = float(last.total_supply) - float(first.total_supply)
        if first.total_supply:
            supply_pct = (supply_abs / float(first.total_supply)) * 100.0
    score_change = float(last.signal_score - first.signal_score) if n >= 2 else None
    max_depeg = max((p.depeg_index for p in points), default=None)

    low_data = n < 2 or coverage < 0.92
    low_data_reason: str | None = None
    if n < 2:
        low_data_reason = (
            "Need at least two snapshots to draw reliable trend lines. "
            "History collection started recently inside the selected window."
        )
    elif coverage < 0.92:
        hrs = int(avail_seconds // 3600)
        mins = int((avail_seconds % 3600) // 60)
        dur_txt = f"{hrs}h {mins}m" if hrs else (f"{mins} min" if mins else "under 1 min")
        low_data_reason = (
            f"History collection started recently. Showing about {dur_txt} of available data "
            f"inside the selected {wl} window."
        )

    return TrendSummaryOut(
        point_count=n,
        supply_change_abs=supply_abs,
        supply_change_pct=supply_pct,
        score_change=score_change,
        max_depeg_index=max_depeg,
        latest_band=last.signal_band,
        selected_window=wl,
        window_span_hours=round(window_hours, 4),
        first_timestamp=first_ts,
        latest_timestamp=last_ts,
        available_duration_minutes=round(avail_minutes, 3),
        low_data=low_data,
        low_data_reason=low_data_reason,
        chart_axis_min_utc=axis_min,
        chart_axis_max_utc=axis_max,
    )


@router.get("/dashboard", response_model=DashboardResponse)
@limiter.limit("60/minute")
def dashboard(request: Request, asset: str | None = None, db: Session = Depends(get_db)) -> DashboardResponse:
    def _build() -> dict[str, Any]:
        return build_dashboard_response(db, asset).model_dump(mode="json")

    payload = get_or_build_dashboard(asset, _build)
    payload.pop("_cache", None)
    return DashboardResponse.model_validate(payload)


@router.get("/assets", response_model=list[AssetConfigOut])
@limiter.limit("60/minute")
def assets(request: Request) -> list[AssetConfigOut]:
    enabled_assets = load_enabled_assets()
    return [AssetConfigOut(**asset) for asset in enabled_assets]
