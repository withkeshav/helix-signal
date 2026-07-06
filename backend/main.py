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
import sys
import traceback
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from structlog import get_logger
from sqlalchemy.orm import Session

from database import AssetTrendSnapshot, SessionLocal, get_db, init_db
from logging_config import configure_logging
from middleware.security import SecurityValidationMiddleware
from middleware.observability import ObservabilityMiddleware
from services.backfill import run_backfill
from services.scheduler import (
    register_scheduler_jobs,
    _osint_job,
    _osint_attestation_refresh,
    _refresh_job,
)
from signal_engine.core import load_enabled_assets, refresh_chain_data

from core.admin_auth import require_admin_token
from core.limiter import limiter
from core.registry import discover_plugins
from routes import register_routes

configure_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()

        try:
            from scripts.seed_admin import ensure_admin_user
            if ensure_admin_user():
                log.info("admin_user.seeded")
        except Exception as exc:
            log.warning("admin_user.seed_failed", error=str(exc))

        try:
            from scripts.train_anomaly import train_anomaly_detector
            if train_anomaly_detector():
                log.info("anomaly_detector.trained")
        except Exception as exc:
            log.warning("anomaly_detector.train_failed", error=str(exc))

        discover_plugins()

        from providers.settings import get_setting

        scheduler = AsyncIOScheduler()
        disable_bg = os.getenv("HELIX_DISABLE_BACKGROUND_TASKS", "").strip().lower() in ("1", "true", "yes")
        listener_task = None
        fred_task = None

        with SessionLocal() as setup_db:
            skip_refresh = os.getenv("HELIX_SKIP_STARTUP_REFRESH", "").strip().lower() in ("1", "true", "yes")
            register_scheduler_jobs(scheduler, setup_db, skip_refresh=skip_refresh)
        scheduler.start()
        app.state.scheduler = scheduler

        loop = asyncio.get_running_loop()
        if not skip_refresh and not disable_bg:
            loop.create_task(asyncio.to_thread(_osint_job))
            loop.create_task(_osint_attestation_refresh())

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
    except Exception:
        log.exception("lifespan.startup_failed")
        traceback.print_exc(file=sys.stderr)
        raise

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        for task in (listener_task, fred_task):
            if task and not task.done():
                task.cancel()
        tasks_to_await = [t for t in (listener_task, fred_task) if t]
        if tasks_to_await:
            await asyncio.gather(*tasks_to_await, return_exceptions=True)


app = FastAPI(
    title="Helix-Signal API",
    description="Stablecoin intelligence platform — on-chain surveillance, anomaly detection, "
                "and market-wide early warning for the stablecoin ecosystem. "
                "Provides REST endpoints for alerts, forensics, OSINT, address tagging, "
                "and real-time signal streaming.",
    version="4.0.0",
    contact={
        "name": "Helix Signal Team",
        "url": "https://github.com/anomalyco/Helix-Signal",
    },
    license_info={
        "name": "MIT",
        "identifier": "MIT",
    },
    lifespan=lifespan,
    swagger_ui_parameters={
        "syntaxHighlight.theme": "monokai",
        "defaultModelsExpandDepth": 3,
        "docExpansion": "list",
        "filter": True,
        "deepLinking": True,
        "displayRequestDuration": True,
    },
)
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
if "*" in _cors_origins:
    import logging
    logging.warning("CORS_ORIGINS contains '*' — wide open. Set explicit origins in production.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "X-Admin-Token", "Authorization", "X-Request-ID"],
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
