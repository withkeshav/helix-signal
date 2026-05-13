import json
import os
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, or_

from database import AssetChainSnapshot, ChainTrendSnapshot, AssetTrendSnapshot, SessionLocal, SignalEvent, SourceStatus, init_db
from schemas import (
    AssetConfigOut,
    AssetMetadataOut,
    AssetSignalOut,
    ChainConcentrationOut,
    ChainTrendPointOut,
    ChainTrendResponseOut,
    ChainTrendSeriesOut,
    ChainSignalOut,
    DashboardChainRow,
    DashboardResponse,
    DataConfidenceOut,
    DepegIndexOut,
    FreshnessOut,
    SignalEventOut,
    SignalEventsResponseOut,
    SourceStatusOut,
    SupplyMomentumOut,
    TrendPointOut,
    TrendResponseOut,
    TrendSummaryOut,
)
from signal_engine import scoring
from signal_engine.core import get_asset_by_symbol, get_default_asset_symbol, load_enabled_assets, refresh_chain_data


def _refresh_job() -> None:
    db = SessionLocal()
    try:
        refresh_chain_data(db)
    finally:
        db.close()


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()

    scheduler = BackgroundScheduler()
    interval_seconds = int(os.getenv("REFRESH_INTERVAL_SECONDS", "300"))
    scheduler.add_job(_refresh_job, "interval", seconds=interval_seconds, id="defillama-refresh", replace_existing=True)
    scheduler.start()

    # Trigger one immediate refresh at startup.
    _refresh_job()

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Helix-Signal API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> str:
    return "Hello Helix-Signal!"


@app.post("/api/refresh")
def api_refresh() -> dict[str, bool]:
    """Run the DefiLlama ingest pipeline once (same as the scheduler job)."""
    db = SessionLocal()
    try:
        refresh_chain_data(db)
        return {"ok": True}
    finally:
        db.close()


@app.get("/api/dashboard", response_model=DashboardResponse)
def dashboard(asset: str | None = None) -> DashboardResponse:
    db = SessionLocal()
    try:
        selected_symbol = (asset or get_default_asset_symbol()).upper()
        selected_asset = get_asset_by_symbol(selected_symbol)
        if selected_asset is None or not bool(selected_asset.get("enabled")):
            raise HTTPException(status_code=404, detail=f"Asset '{selected_symbol}' is not enabled")

        refresh_interval = int(os.getenv("REFRESH_INTERVAL_SECONDS", "300"))

        chains_orm = (
            db.query(AssetChainSnapshot)
            .filter(AssetChainSnapshot.asset_symbol == selected_symbol)
            .order_by(AssetChainSnapshot.supply_current.desc(), AssetChainSnapshot.chain_name.asc())
            .all()
        )
        sources_orm = db.query(SourceStatus).order_by(SourceStatus.id.asc()).all()
        sources = [SourceStatusOut.model_validate(s) for s in sources_orm]

        defillama = next((s for s in sources_orm if s.source_name == "defillama"), None)
        source_status = defillama.status if defillama else "unknown"

        newest_chain_snapshot = max((_utc(c.fetched_at) for c in chains_orm), default=None) if chains_orm else None

        freshness_dict = scoring.compute_freshness(
            source_status=source_status,
            last_successful_fetch=_utc(defillama.last_successful_fetch) if defillama else None,
            newest_chain_snapshot=newest_chain_snapshot,
            refresh_interval_seconds=refresh_interval,
        )
        freshness = FreshnessOut(**freshness_dict)

        raw_total = sum((c.supply_current or 0.0) for c in chains_orm)
        total_supply = raw_total if raw_total > 0 else None

        total_prev_day = sum((c.supply_prev_day or 0.0) for c in chains_orm)
        total_prev_week = sum((c.supply_prev_week or 0.0) for c in chains_orm)
        total_prev_month = sum((c.supply_prev_month or 0.0) for c in chains_orm)

        total_change_24h_pct: float | None = None
        if total_supply is not None and total_prev_day > 0:
            total_change_24h_pct = ((total_supply - total_prev_day) / total_prev_day) * 100.0

        chain_shares: list[float] = []
        if total_supply and total_supply > 0:
            for c in chains_orm:
                if c.supply_current is not None and c.supply_current > 0:
                    chain_shares.append(float(c.supply_current) / float(total_supply))

        source_ok = defillama is not None and defillama.status == "ok"
        source_error = defillama.last_error if defillama else None

        price = next((c.price for c in chains_orm if c.price is not None), None)

        if price is not None:
            dev_abs, dev_pct = scoring.peg_deviation(price)
        else:
            dev_abs, dev_pct = None, None
        depeg_index = DepegIndexOut(
            score=scoring.depeg_index_score(price),
            current_price=price,
            deviation_abs=dev_abs,
            deviation_pct=dev_pct,
            peg_status=scoring.peg_status_label(price),
        )

        conc_s, conc_detail = scoring.concentration_component(chain_shares)
        top_chain_name: str | None = None
        if total_supply and total_supply > 0 and chains_orm:
            top_row = max(chains_orm, key=lambda c: (c.supply_current or 0.0))
            if (top_row.supply_current or 0.0) > 0:
                top_chain_name = top_row.chain_name

        chain_concentration = ChainConcentrationOut(
            top_chain=top_chain_name,
            top_chain_share_pct=conc_detail.get("top_chain_share_pct"),
            hhi=conc_detail.get("hhi"),
            label=scoring.composite_band(conc_s),
        )

        asset_signal_dict = scoring.compute_asset_signal(
            price=price,
            supply_current=float(total_supply or 0.0),
            supply_prev_day=total_prev_day if total_prev_day > 0 else None,
            supply_prev_week=total_prev_week if total_prev_week > 0 else None,
            supply_prev_month=total_prev_month if total_prev_month > 0 else None,
            chain_shares=chain_shares,
            source_ok=source_ok,
            source_error=source_error,
            age_seconds=freshness_dict.get("age_seconds"),
            refresh_interval_seconds=refresh_interval,
        )
        asset_signal = AssetSignalOut(
            score=int(asset_signal_dict["score"]),
            band=str(asset_signal_dict["band"]),
            components=dict(asset_signal_dict["components"]),
        )

        now = datetime.now(timezone.utc)
        dashboard_chains: list[DashboardChainRow] = []
        asset_name = selected_asset.get("name")

        for c in chains_orm:
            fetched = _utc(c.fetched_at)
            age_s = (now - fetched).total_seconds() if fetched else None

            sm_raw = scoring.chain_supply_momentum(
                supply_current=c.supply_current,
                supply_prev_day=c.supply_prev_day,
                supply_prev_week=c.supply_prev_week,
                supply_prev_month=c.supply_prev_month,
            )
            supply_momentum = SupplyMomentumOut(**sm_raw)

            share_pct = (
                (float(c.supply_current) / float(total_supply)) * 100.0
                if total_supply and c.supply_current is not None and total_supply > 0
                else None
            )

            cur_supply = float(c.supply_current or 0.0)
            mom_hint, _ = scoring.supply_momentum_component(
                supply_current=cur_supply,
                supply_prev_day=c.supply_prev_day,
                supply_prev_week=c.supply_prev_week,
                supply_prev_month=c.supply_prev_month,
            )

            cs_raw = scoring.chain_row_signal(
                chain_share_pct=share_pct,
                peg_price=c.price,
                momentum_score_hint=mom_hint,
            )
            chain_signal = ChainSignalOut(score=int(cs_raw["score"]), band=str(cs_raw["band"]))

            dc_raw = scoring.chain_data_confidence(
                source_ok=source_ok,
                chain_snapshot_age_seconds=age_s,
                refresh_interval_seconds=refresh_interval,
            )
            data_confidence = DataConfidenceOut(
                score=int(dc_raw["score"]),
                label=str(dc_raw["label"]),
                reason=str(dc_raw["reason"]),
            )

            dashboard_chains.append(
                DashboardChainRow(
                    asset_symbol=selected_symbol,
                    asset_name=asset_name,
                    chain_name=c.chain_name,
                    supply_current=c.supply_current,
                    supply_prev_day=c.supply_prev_day,
                    supply_prev_week=c.supply_prev_week,
                    supply_prev_month=c.supply_prev_month,
                    chain_tvl=c.tvl,
                    price=c.price,
                    peg_type=c.peg_type,
                    fetched_at=c.fetched_at,
                    supply_momentum=supply_momentum,
                    chain_share_pct=round(share_pct, 4) if share_pct is not None else None,
                    chain_signal=chain_signal,
                    data_confidence=data_confidence,
                )
            )

        generated_at = datetime.now(timezone.utc)

        return DashboardResponse(
            asset=AssetMetadataOut(
                symbol=selected_symbol,
                name=selected_asset.get("name"),
                peg_type=selected_asset.get("peg_type"),
            ),
            generated_at=generated_at,
            refresh_interval_seconds=refresh_interval,
            freshness=freshness,
            asset_signal=asset_signal,
            depeg_index=depeg_index,
            chain_concentration=chain_concentration,
            total_supply_current=total_supply,
            total_supply_change_24h_pct=total_change_24h_pct,
            chains=dashboard_chains,
            sources=sources,
        )
    finally:
        db.close()


@app.get("/api/assets", response_model=list[AssetConfigOut])
def assets() -> list[AssetConfigOut]:
    enabled_assets = load_enabled_assets()
    return [AssetConfigOut(**asset) for asset in enabled_assets]


_ALLOWED_TREND_WINDOWS = frozenset({"24h", "7d", "30d"})


def _window_delta(window: str) -> timedelta:
    if window == "24h":
        return timedelta(hours=24)
    if window == "7d":
        return timedelta(days=7)
    return timedelta(days=30)


def _signal_event_rows_to_out(rows: list[SignalEvent]) -> list[SignalEventOut]:
    out: list[SignalEventOut] = []
    for r in rows:
        meta: dict | None = None
        if r.metadata_json:
            try:
                meta = json.loads(r.metadata_json)
            except json.JSONDecodeError:
                meta = None
        out.append(
            SignalEventOut(
                id=r.id,
                asset_symbol=r.asset_symbol,
                chain_key=r.chain_key,
                event_type=r.event_type,
                severity=r.severity,
                title=r.title,
                summary=r.summary,
                old_value=r.old_value,
                new_value=r.new_value,
                delta=r.delta,
                threshold=r.threshold,
                timestamp=r.timestamp,
                metadata=meta,
            )
        )
    return out


def _build_trend_summary(points: list[TrendPointOut], *, window: str, now: datetime) -> TrendSummaryOut:
    span_td = _window_delta(window)
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
        if hrs > 0:
            dur_txt = f"{hrs}h {mins}m" if mins else f"{hrs}h"
        else:
            dur_txt = f"{mins} min" if mins else "under 1 min"
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


@app.get("/api/trends", response_model=TrendResponseOut)
def trends(asset: str, window: str = Query("7d")) -> TrendResponseOut:
    w = window.strip().lower()
    if w not in _ALLOWED_TREND_WINDOWS:
        raise HTTPException(status_code=400, detail="Invalid window. Use 24h, 7d, or 30d.")
    sym = asset.strip().upper()
    selected = get_asset_by_symbol(sym)
    if selected is None or not bool(selected.get("enabled")):
        raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - _window_delta(w)
        rows = (
            db.query(AssetTrendSnapshot)
            .filter(AssetTrendSnapshot.asset_symbol == sym, AssetTrendSnapshot.timestamp >= cutoff)
            .order_by(AssetTrendSnapshot.timestamp.asc())
            .all()
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
        summary = _build_trend_summary(points, window=w, now=now)
        return TrendResponseOut(
            asset=sym,
            window=w,
            generated_at=now,
            points=points,
            summary=summary,
        )
    finally:
        db.close()


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
    span_td = _window_delta(window)
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


@app.get("/api/trends/chains", response_model=ChainTrendResponseOut)
def trends_chains(asset: str, window: str = Query("7d")) -> ChainTrendResponseOut:
    w = window.strip().lower()
    if w not in _ALLOWED_TREND_WINDOWS:
        raise HTTPException(status_code=400, detail="Invalid window. Use 24h, 7d, or 30d.")
    sym = asset.strip().upper()
    selected = get_asset_by_symbol(sym)
    if selected is None or not bool(selected.get("enabled")):
        raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - _window_delta(w)
        rows = (
            db.query(ChainTrendSnapshot)
            .filter(ChainTrendSnapshot.asset_symbol == sym, ChainTrendSnapshot.timestamp >= cutoff)
            .order_by(ChainTrendSnapshot.timestamp.asc())
            .all()
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
    finally:
        db.close()


@app.get("/api/events", response_model=SignalEventsResponseOut)
def events(
    limit: int = Query(50, ge=1, le=200),
    asset: str | None = None,
) -> SignalEventsResponseOut:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        q = db.query(SignalEvent)
        if asset:
            sym = asset.strip().upper()
            selected = get_asset_by_symbol(sym)
            if selected is None or not bool(selected.get("enabled")):
                raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")
            q = q.filter(or_(SignalEvent.asset_symbol == sym, SignalEvent.asset_symbol == "ALL"))
        rows = q.order_by(desc(SignalEvent.timestamp)).limit(limit).all()
        return SignalEventsResponseOut(generated_at=now, events=_signal_event_rows_to_out(rows))
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
