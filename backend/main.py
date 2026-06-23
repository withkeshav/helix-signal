"""Main FastAPI application for Helix Signal.

This is the entry point for the Helix Signal backend. It sets up the FastAPI
application with all required routes, middleware, and background tasks.

Key components:
- FastAPI application setup
- Background job scheduling (data refresh, retention, OSINT)
- Route registration
- Middleware configuration
- Application lifecycle management

The application follows a modular architecture where routes are registered
from separate modules in the routes/ directory.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.orm import Session
from structlog import get_logger

from database import AssetTrendSnapshot, SessionLocal, get_db, init_db
from logging_config import configure_logging
from middleware.security import SecurityValidationMiddleware
from middleware.observability import ObservabilityMiddleware
from services.backfill import run_backfill
from services.osint import ingest_osint_feed
from services.retention import prune_old_history
from signal_engine.core import load_enabled_assets, refresh_chain_data

from core.admin_auth import require_admin_token
from core.limiter import limiter
from core.registry import discover_plugins
from routes import register_routes

configure_logging()
log = get_logger(__name__)


async def _refresh_job() -> None:
    log.info("refresh_job.start")
    db = SessionLocal()
    try:
        await refresh_chain_data(db)
        log.info("refresh_job.data_refresh_complete")
        _run_anomaly_circuit_breaker(db)
        log.info("refresh_job.complete")
    except Exception:
        log.exception("refresh_job.failed")
        raise
    finally:
        db.close()


def _run_anomaly_circuit_breaker(db: Session) -> None:
    from agents.anomaly_agent import run_circuit_breaker_cycle
    results = run_circuit_breaker_cycle(db)
    if results:
        triggered = [r["asset_symbol"] for r in results if r.get("investigated")]
        if triggered:
            log.info("circuit_breaker.triggered", assets=triggered)


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
        if count:
            log.info("osint_job.complete", articles_ingested=count)
    except Exception:
        log.exception("osint_job.failed")
    finally:
        db.close()


async def _osint_attestation_refresh() -> None:
    """Async background job to keep attestation cache fresh."""
    try:
        from services.osint import _refresh_attestation_reports_async
        await _refresh_attestation_reports_async()
        log.info("osint_attestation_refresh.complete", cache_fresh=True)
    except Exception:
        log.exception("osint_attestation_refresh.failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    discover_plugins()

    from providers.settings import get_setting

    scheduler = AsyncIOScheduler()
    disable_bg = os.getenv("HELIX_DISABLE_BACKGROUND_TASKS", "").strip().lower() in ("1", "true", "yes")
    listener_task = None
    fred_task = None
    telegram_app = None
    telegram_task = None

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

        # Wire up Telegram bot if enabled
        if not disable_bg and get_setting("feature_telegram_bot", setup_db):
            try:
                from helix_telegram.bot import create_bot_application
                telegram_app = create_bot_application()
                if telegram_app:
                    from helix_telegram.digest import add_digest_scheduler
                    add_digest_scheduler(scheduler)
                    loop = asyncio.get_running_loop()
                    telegram_task = loop.create_task(telegram_app.run_polling())
                    log.info("telegram_bot.started")
            except Exception as exc:
                log.warning("telegram_bot.start_failed", error=str(exc))

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
        _osint_attestation_refresh,
        "interval",
        minutes=osint_minutes,
        id="osint-attestation-refresh",
        replace_existing=True,
    )
    scheduler.start()
    app.state.scheduler = scheduler

    loop = asyncio.get_running_loop()
    loop.create_task(asyncio.to_thread(_osint_job))

    if not skip_refresh:
        await _refresh_job()

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

    if not disable_bg:
        try:
            from chain.web3_listener import start_block_listener
            listener_task = await start_block_listener()
        except Exception as exc:
            log.warning("block_listener.start_failed", error=str(exc))

        try:
            from chain.fred_api import start_fred_poller
            loop = asyncio.get_running_loop()
            fred_task = loop.create_task(start_fred_poller())
        except Exception as exc:
            log.warning("fred_poller.start_failed", error=str(exc))

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        if telegram_app and telegram_task and not telegram_task.done():
            telegram_task.cancel()
            try:
                await asyncio.wait_for(telegram_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            log.info("telegram_bot.stopped")
        for task in (listener_task, fred_task):
            if task and not task.done():
                task.cancel()
        tasks_to_await = [t for t in (listener_task, fred_task) if t]
        if tasks_to_await:
            await asyncio.gather(*tasks_to_await, return_exceptions=True)


app = FastAPI(title="Helix-Signal API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityValidationMiddleware)
app.add_middleware(ObservabilityMiddleware)
try:
    from providers.settings import get_setting
    _cors_raw = get_setting("cors_origins") or os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost")
except Exception:
    _cors_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost")
_cors_origins = [o.strip() for o in str(_cors_raw).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


register_routes(app)


@app.get("/")
@limiter.limit("60/minute")
def root(request: Request) -> str:
    return "Hello Helix-Signal!"


@app.post("/api/refresh")
@limiter.limit("10/minute")
async def api_refresh(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, bool]:
    await refresh_chain_data(db)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)  # nosec: dev-only, Docker overrides host in production
