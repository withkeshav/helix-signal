"""Health check assembly."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SourceStatus
from services.retention import HELIX_VERSION


def _celery_running() -> bool:
    try:
        from celery_app import celery_app
        insp = celery_app.control.inspect(timeout=2.0)
        return bool(insp.ping())
    except Exception:
        return False


def build_health_payload(
    db: Session,
    *,
    scheduler: BackgroundScheduler | None,
) -> dict[str, Any]:
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    defillama = db.query(SourceStatus).filter(SourceStatus.source_name == "defillama").first()
    last_fetch: str | None = None
    if defillama and defillama.last_successful_fetch:
        ts = defillama.last_successful_fetch
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        last_fetch = ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    use_celery = os.getenv("HELIX_USE_CELERY_REFRESH", "").strip().lower() in ("1", "true", "yes")
    scheduler_running = bool(scheduler and scheduler.running) if not use_celery else _celery_running()
    status = "ok" if db_ok and scheduler_running else "degraded"
    if defillama and defillama.status == "error":
        status = "degraded"

    return {
        "status": status,
        "db": db_ok,
        "last_successful_fetch": last_fetch,
        "scheduler_running": scheduler_running,
        "use_celery": use_celery,
        "version": HELIX_VERSION,
    }
