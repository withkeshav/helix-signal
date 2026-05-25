import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Gauge, generate_latest
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.orm import Session
from structlog import get_logger

from database import AssetTrendSnapshot, Base, SessionLocal, SourceStatus, engine, get_db, init_db
from logging_config import configure_logging
from middleware.security import SecurityValidationMiddleware
from middleware.observability import ObservabilityMiddleware, METRIC_REQUEST_COUNT, METRIC_REQUEST_LATENCY, METRIC_SOURCE_HEALTH
from services.backfill import run_backfill
from services.osint import ingest_osint_feed, refresh_attestation_reports
from services.retention import prune_old_history
from signal_engine.core import get_asset_by_symbol, load_enabled_assets, refresh_chain_data

from backend.core.admin_auth import require_admin_token
from backend.core.limiter import limiter
from backend.core.registry import discover_plugins
from routes import register_routes

configure_logging()
log = get_logger(__name__)

METRIC_SCHEDULER_RUNNING = Gauge("helix_scheduler_running", "Scheduler is running (1/0)")
METRIC_LAST_REFRESH_AGE = Gauge("helix_last_refresh_age_seconds", "Seconds since last successful refresh")
METRIC_TREND_ROWS = Gauge("helix_trend_snapshot_rows", "Number of trend snapshot rows")

_last_successful_refresh: float | None = None


def _refresh_job() -> None:
    global _last_successful_refresh
    log.info("refresh_job.start")
    db = SessionLocal()
    try:
        refresh_chain_data(db)
        _last_successful_refresh = time.time()
        log.info("refresh_job.complete")
    except Exception:
        log.exception("refresh_job.failed")
        raise
    finally:
        db.close()


def _retention_job() -> None:
    db = SessionLocal()
    try:
        prune_old_history(db)
    finally:
        db.close()


def _osint_job() -> None:
    from providers.settings import get_setting
    db = SessionLocal()
    try:
        if not get_setting("feature_osint_feed", db):
            return
        count = ingest_osint_feed(db)
        refresh_attestation_reports(force=True)
        if count:
            log.info("osint_job.complete", articles_ingested=count)
    except Exception:
        log.exception("osint_job.failed")
    finally:
        db.close()


def _forecast_job() -> None:
    from providers.settings import get_setting
    from services.forecast import run_all_forecasts

    db = SessionLocal()
    try:
        if not get_setting("feature_forecasting", db):
            log.info("forecast_job.skipped", reason="feature_forecasting_disabled")
            return
    finally:
        db.close()

    log.info("forecast_job.start")
    try:
        result = run_all_forecasts()
        log.info("forecast_job.complete", tasks=result.get("tasks"))
    except Exception:
        log.exception("forecast_job.failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    discover_plugins()

    from providers.settings import get_setting

    scheduler = BackgroundScheduler()
    with SessionLocal() as setup_db:
        skip_refresh = os.getenv("HELIX_SKIP_STARTUP_REFRESH", "").strip().lower() in ("1", "true", "yes")
        if not skip_refresh:
            interval_seconds = max(60, get_setting("refresh_core_seconds", setup_db) or int(os.getenv("REFRESH_INTERVAL_SECONDS", "300")))
            scheduler.add_job(
                _refresh_job,
                "interval",
                seconds=interval_seconds,
                id="defillama-refresh",
                replace_existing=True,
            )
        osint_minutes = max(15, get_setting("refresh_osint_minutes", setup_db) or 60)
        forecast_minutes = max(15, get_setting("refresh_forecast_minutes", setup_db) or 30)

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
        minutes=osint_minutes,
        id="osint-ingest",
        replace_existing=True,
    )
    scheduler.add_job(
        _forecast_job,
        "interval",
        minutes=forecast_minutes,
        id="forecast-generation",
        replace_existing=True,
    )
    scheduler.start()
    app.state.scheduler = scheduler

    _osint_job()  # immediate first run, no waiting 1 hour

    if not skip_refresh:
        _refresh_job()

    if not skip_refresh:
        db = SessionLocal()
        try:
            row_count = db.query(AssetTrendSnapshot).count()
            if row_count < 24:
                log.info("auto_backfill.start", reason="fresh_db", current_rows=row_count)
                enabled = load_enabled_assets()
                for asset in enabled:
                    sym = asset.get("symbol", "")
                    if sym:
                        try:
                            run_backfill(db, asset=sym, days=7, _internal=True)
                            log.info("auto_backfill.complete", asset=sym)
                        except Exception as exc:
                            log.warning("auto_backfill.failed", asset=sym, error=str(exc))
                db.commit()
        finally:
            db.close()

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Helix-Signal API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityValidationMiddleware)
app.add_middleware(ObservabilityMiddleware)
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


register_routes(app)


@app.get("/metrics")
def prometheus_metrics(request: Request, _auth=Depends(require_admin_token)) -> Response:
    db = SessionLocal()
    try:
        scheduler = getattr(app.state, "scheduler", None)
        METRIC_SCHEDULER_RUNNING.set(1 if scheduler and scheduler.running else 0)

        if _last_successful_refresh is not None:
            METRIC_LAST_REFRESH_AGE.set(time.time() - _last_successful_refresh)

        source_count = db.query(AssetTrendSnapshot).count()
        METRIC_TREND_ROWS.set(source_count)

        for src in ("defillama", "coingecko", "dexscreener"):
            row = db.query(SourceStatus).filter(SourceStatus.source_name == src).first()
            healthy = 1 if row and row.status == "ok" else 0
            METRIC_SOURCE_HEALTH.labels(source=src).set(healthy)

        return Response(content=generate_latest(), media_type="text/plain; charset=utf-8")
    finally:
        db.close()


@app.get("/")
@limiter.limit("60/minute")
def root(request: Request) -> str:
    return "Hello Helix-Signal!"


@app.post("/api/refresh")
@limiter.limit("10/minute")
def api_refresh(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, bool]:
    refresh_chain_data(db)
    return {"ok": True}


@app.get("/api/ai/explain")
@limiter.limit("30/minute")
def api_ai_explain(
    request: Request,
    asset: str = Query("USDT"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from services.ai_router import enrich_with_ai
    from services.predictive import run_predictive_bundle

    pred = run_predictive_bundle(db, asset_symbol=asset.upper(), log_to_mlflow=False)
    context = {
        "asset_symbol": asset.upper(),
        "signal_score": pred.get("signal_score"),
        "signal_band": "Risk" if (pred.get("signal_score") or 0) >= 70 else "Watch" if (pred.get("signal_score") or 0) >= 40 else "Normal",
        "regime": pred.get("regime"),
    }
    return enrich_with_ai(feature="risk_explain", context=context)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
