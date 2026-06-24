from __future__ import annotations

import os
import platform
import sys
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

# Safe env vars — allowlist only, never expose secrets
_DIAGNOSTICS_ALLOWLIST = frozenset({
    "HELIX_VERSION", "HELIX_ENV", "AI_MODE", "PYTHON_VERSION",
    "ENABLE_CHAINLINK", "ENABLE_REDIS_CACHE",
    "HELIX_DISABLE_BACKGROUND_TASKS",
})

from core.admin_auth import require_admin_token
from core.limiter import limiter
from services.retention import HELIX_VERSION
from database import get_db
from providers.settings import get_all_settings
from services.backfill import run_backfill
from services.governance import build_governance_payload
from services.source_usage import get_source_usage_summary
from core.registry import SOURCES_REGISTRY, get_source

router = APIRouter()


_TABLE_NAMES = [
    "asset_chain_snapshots", "source_status", "asset_freshness",
    "asset_trend_snapshots", "chain_trend_snapshots", "osint_articles",
    "forecast_runs", "forecast_points", "signal_events", "source_usage",
]


@router.get("/admin/diagnostics")
@limiter.limit("10/minute")
def admin_diagnostics(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    return _build_diagnostics(db)


def _build_diagnostics(db: Session) -> dict[str, Any]:
    health = _get_health(db)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": HELIX_VERSION,
        "system": {
            "python_version": sys.version,
            "platform": platform.platform(),
        },
        "environment": {
            key: os.getenv(key, "")
            for key in sorted(os.environ.keys())
            if key in _DIAGNOSTICS_ALLOWLIST
        },
        "health": health,
        "sources": _get_source_statuses(),
        "source_usage": get_source_usage_summary(db),
        "settings": get_all_settings(db),
        "database_tables": _get_table_counts(db),
    }


def _get_health(db: Session) -> dict[str, Any]:
    db_ok = False
    scheduler_running = False
    redis_connected = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    try:
        from core.cache_manager import cache
        if cache._redis:
            redis_connected = True
    except Exception:
        pass
    pass  # scheduler status unavailable — no standalone scheduler module
    return {
        "db": db_ok,
        "redis_connected": redis_connected,
        "scheduler_running": scheduler_running,
    }


def _get_source_statuses() -> dict[str, Any]:
    statuses = {}
    for name in SOURCES_REGISTRY:
        source = get_source(name)
        if source and hasattr(source, "health_check"):
            statuses[name] = source.health_check()
        else:
            statuses[name] = {"source": name, "state": "unknown"}
    return statuses


def _get_table_counts(db: Session) -> dict[str, int]:
    counts = {}
    for table in _TABLE_NAMES:
        try:
            result = db.execute(text(f"SELECT COUNT(*) FROM {table}"))  # nosec: _TABLE_NAMES is a hardcoded constant (line 33)
            counts[table] = result.scalar() or 0
        except Exception:
            counts[table] = -1
    return counts


@router.post("/admin/backfill")
@limiter.limit("5/minute")
def admin_backfill(
    request: Request,
    asset: str,
    days: int = Query(7, ge=7, le=30),
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    return run_backfill(db, asset=asset, days=days)


@router.get("/governance")
@limiter.limit("10/minute")
def api_governance(
    request: Request,
    asset: str = Query(...),
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    return build_governance_payload(db, asset=asset)
