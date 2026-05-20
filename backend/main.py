import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session
from structlog import get_logger

from database import (
    AssetTrendSnapshot,
    ChainTrendSnapshot,
    SessionLocal,
    SignalEvent,
    get_db,
    init_db,
)
from logging_config import configure_logging
from schemas import (
    AssetConfigOut,
    ChainTrendPointOut,
    ChainTrendResponseOut,
    ChainTrendSeriesOut,
    DashboardResponse,
    SignalEventOut,
    SignalEventsResponseOut,
    TrendPointOut,
    TrendResponseOut,
    TrendSummaryOut,
)
from services.alerts import load_alert_rules, evaluate_alerts
from services.anomaly import detect_anomalies, train_models, forecast_supply
from services.backfill import run_backfill
from services.chain_detail import build_chain_detail
from services.compare import build_compare_payload
from services.dashboard import build_dashboard_response
from services.exports import events_export, trends_export
from services.governance import build_governance_payload
from services.health import build_health_payload
from services.osint import ingest_osint_feed, get_osint_feed, get_sentiment_timeseries, get_attestation_status, correlate_sentiment_depeg
from services.retention import prune_old_history
from signal_engine.core import get_asset_by_symbol, load_enabled_assets, refresh_chain_data
from utils import utc_normalize, window_delta, signal_event_rows_to_out

configure_logging()
log = get_logger(__name__)

# --- Prometheus metrics ---
METRIC_REQUEST_COUNT = Counter(
    "helix_http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)
METRIC_REQUEST_LATENCY = Histogram(
    "helix_http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
METRIC_SCHEDULER_RUNNING = Gauge("helix_scheduler_running", "Scheduler is running (1/0)")
METRIC_LAST_REFRESH_AGE = Gauge("helix_last_refresh_age_seconds", "Seconds since last successful refresh")
METRIC_SOURCE_HEALTH = Gauge("helix_source_health", "Source health status per source", ["source"])
METRIC_DB_CONNECTIONS = Gauge("helix_db_connections", "Active DB connection count")

limiter = Limiter(key_func=get_remote_address)


def _refresh_job() -> None:
    log.info("refresh_job.start")
    db = SessionLocal()
    try:
        refresh_chain_data(db)
        log.info("refresh_job.complete")
    except Exception:
        log.exception("refresh_job.failed")
    finally:
        db.close()


def _retention_job() -> None:
    db = SessionLocal()
    try:
        prune_old_history(db)
    finally:
        db.close()


def _osint_job() -> None:
    db = SessionLocal()
    try:
        count = ingest_osint_feed(db)
        if count:
            log.info("osint_job.complete", articles_ingested=count)
    except Exception:
        log.exception("osint_job.failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    scheduler = BackgroundScheduler()
    skip_refresh = os.getenv("HELIX_SKIP_STARTUP_REFRESH", "").strip().lower() in ("1", "true", "yes")
    if not skip_refresh:
        interval_seconds = int(os.getenv("REFRESH_INTERVAL_SECONDS", "300"))
        scheduler.add_job(
            _refresh_job,
            "interval",
            seconds=interval_seconds,
            id="defillama-refresh",
            replace_existing=True,
        )
    scheduler.add_job(
        _retention_job,
        "cron",
        hour=3,
        minute=15,
        id="history-retention",
        replace_existing=True,
    )
    scheduler.add_job(
        _osint_job,
        "interval",
        hours=1,
        id="osint-ingest",
        replace_existing=True,
    )
    scheduler.start()
    app.state.scheduler = scheduler

    if not skip_refresh:
        _refresh_job()

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Helix-Signal API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.monotonic()
    response: Response = await call_next(request)
    duration = time.monotonic() - start
    endpoint = request.url.path
    METRIC_REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status=str(response.status_code)).inc()
    METRIC_REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(duration)
    return response


@app.get("/metrics")
def prometheus_metrics() -> Response:
    db = next(get_db())
    scheduler = getattr(app.state, "scheduler", None)
    METRIC_SCHEDULER_RUNNING.set(1 if scheduler and scheduler.running else 0)

    if scheduler and scheduler.running:
        jobs = scheduler.get_jobs()
        for job in jobs:
            if job.id == "defillama-refresh" and hasattr(job, "next_run_time"):
                if job.next_run_time:
                    age = (datetime.now(timezone.utc) - job.next_run_time).total_seconds()
                    METRIC_LAST_REFRESH_AGE.set(max(age, 0))

    source_count = db.query(AssetTrendSnapshot).count()
    METRIC_DB_CONNECTIONS.set(source_count)

    for src in ("defillama", "coingecko", "dexscreener"):
        METRIC_SOURCE_HEALTH.labels(source=src).set(1)

    return Response(content=generate_latest(), media_type="text/plain; charset=utf-8")


@app.get("/")
@limiter.limit("60/minute")
def root(request: Request) -> str:
    return "Hello Helix-Signal!"


@app.get("/api/health")
@limiter.limit("60/minute")
def api_health(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    scheduler = getattr(app.state, "scheduler", None)
    return build_health_payload(db, scheduler=scheduler)


@app.post("/api/refresh")
@limiter.limit("10/minute")
def api_refresh(request: Request, db: Session = Depends(get_db)) -> dict[str, bool]:
    """Run the DefiLlama ingest pipeline once (same as the scheduler job)."""
    refresh_chain_data(db)
    return {"ok": True}


@app.get("/api/dashboard", response_model=DashboardResponse)
@limiter.limit("60/minute")
def dashboard(request: Request, asset: str | None = None, db: Session = Depends(get_db)) -> DashboardResponse:
    return build_dashboard_response(db, asset)


@app.get("/api/assets", response_model=list[AssetConfigOut])
@limiter.limit("60/minute")
def assets(request: Request) -> list[AssetConfigOut]:
    enabled_assets = load_enabled_assets()
    return [AssetConfigOut(**asset) for asset in enabled_assets]


_ALLOWED_TREND_WINDOWS = frozenset({"24h", "7d", "30d"})


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
@limiter.limit("60/minute")
def trends(request: Request, asset: str, window: str = Query("7d"), db: Session = Depends(get_db)) -> TrendResponseOut:
    w = window.strip().lower()
    if w not in _ALLOWED_TREND_WINDOWS:
        raise HTTPException(status_code=400, detail="Invalid window. Use 24h, 7d, or 30d.")
    sym = asset.strip().upper()
    selected = get_asset_by_symbol(sym)
    if selected is None or not bool(selected.get("enabled")):
        raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")

    now = datetime.now(timezone.utc)
    cutoff = now - window_delta(w)
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


@app.get("/api/trends/export")
@limiter.limit("30/minute")
def trends_export_route(
    request: Request,
    asset: str,
    window: str = Query("7d"),
    format: str = Query("csv", alias="format"),
    db: Session = Depends(get_db),
):
    return trends_export(db, asset=asset, window=window, fmt=format)


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


@app.get("/api/trends/chains", response_model=ChainTrendResponseOut)
@limiter.limit("60/minute")
def trends_chains(request: Request, asset: str, window: str = Query("7d"), db: Session = Depends(get_db)) -> ChainTrendResponseOut:
    w = window.strip().lower()
    if w not in _ALLOWED_TREND_WINDOWS:
        raise HTTPException(status_code=400, detail="Invalid window. Use 24h, 7d, or 30d.")
    sym = asset.strip().upper()
    selected = get_asset_by_symbol(sym)
    if selected is None or not bool(selected.get("enabled")):
        raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")

    now = datetime.now(timezone.utc)
    cutoff = now - window_delta(w)
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


@app.get("/api/events", response_model=SignalEventsResponseOut)
@limiter.limit("60/minute")
def events(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    asset: str | None = None,
    db: Session = Depends(get_db),
) -> SignalEventsResponseOut:
    now = datetime.now(timezone.utc)
    q = db.query(SignalEvent)
    if asset:
        sym = asset.strip().upper()
        selected = get_asset_by_symbol(sym)
        if selected is None or not bool(selected.get("enabled")):
            raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")
        q = q.filter(or_(SignalEvent.asset_symbol == sym, SignalEvent.asset_symbol == "ALL"))
    rows = q.order_by(desc(SignalEvent.timestamp)).limit(limit).all()
    return SignalEventsResponseOut(generated_at=now, events=signal_event_rows_to_out(rows))


@app.get("/api/events/export")
@limiter.limit("30/minute")
def events_export_route(
    request: Request,
    limit: int = Query(500, ge=1, le=10000),
    asset: str | None = None,
    format: str = Query("csv", alias="format"),
    db: Session = Depends(get_db),
):
    return events_export(db, asset=asset, limit=limit, fmt=format)


@app.get("/api/compare")
@limiter.limit("60/minute")
def compare(request: Request, assets: str, window: str = Query("7d"), db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_compare_payload(db, assets_csv=assets, window=window)


@app.get("/api/chains/{chain_key}")
@limiter.limit("60/minute")
def chain_detail(request: Request, chain_key: str, asset: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_chain_detail(db, chain_key=chain_key, asset=asset)


@app.post("/api/admin/backfill")
@limiter.limit("5/minute")
def admin_backfill(request: Request, asset: str, days: int = Query(7, ge=7, le=30), db: Session = Depends(get_db)) -> dict[str, Any]:
    return run_backfill(db, asset=asset, days=days)


@app.get("/api/alerts/config")
def get_alert_config(request: Request) -> list[dict[str, Any]]:
    return load_alert_rules()


@app.get("/api/governance")
def api_governance(request: Request, asset: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_governance_payload(db, asset=asset)


@app.get("/api/osint/feed")
@limiter.limit("60/minute")
def api_osint_feed(
    request: Request,
    asset: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return get_osint_feed(db, asset=asset, limit=limit)


@app.get("/api/osint/sentiment")
def api_osint_sentiment(
    request: Request,
    asset: str | None = Query(None),
    window_days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return get_sentiment_timeseries(db, asset=asset, window_days=window_days)


@app.get("/api/osint/attestation")
def api_osint_attestation(request: Request) -> dict[str, Any]:
    return get_attestation_status()


@app.get("/api/osint/correlate")
def api_osint_correlate(
    request: Request,
    asset: str = Query(...),
    window_hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return correlate_sentiment_depeg(db, asset=asset, window_hours=window_hours)


@app.get("/api/anomaly/detect")
def api_anomaly_detect(request: Request, asset: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    return detect_anomalies(db, asset_symbol=asset)


@app.get("/api/anomaly/forecast")
def api_anomaly_forecast(
    request: Request,
    asset: str = Query(...),
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return forecast_supply(db, asset_symbol=asset, hours=hours)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
