"""Health check assembly."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.cache_manager import cache
from database import SourceStatus
from services.retention import HELIX_VERSION


def build_health_payload(
    db: Session,
    *,
    scheduler: BackgroundScheduler | None,
) -> dict[str, Any]:
    db_connected = False
    try:
        db.execute(text("SELECT 1"))
        db_connected = True
    except Exception:
        db_connected = False

    redis_connected = False
    if cache._redis:
        try:
            cache._redis.ping()
            redis_connected = True
        except Exception:
            redis_connected = False

    defillama = db.query(SourceStatus).filter(SourceStatus.source_name == "defillama").first()
    last_fetch: str | None = None
    if defillama and defillama.last_successful_fetch:
        ts = defillama.last_successful_fetch
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        last_fetch = ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    scheduler_running = bool(scheduler and scheduler.running)
    status = "ok" if db_connected and scheduler_running else "degraded"
    if defillama and defillama.status == "error":
        status = "degraded"

    return {
        "status": status,
        "db": db_connected,
        "db_connected": db_connected,
        "redis_connected": redis_connected,
        "last_successful_fetch": last_fetch,
        "scheduler_running": scheduler_running,
        "version": HELIX_VERSION,
    }
