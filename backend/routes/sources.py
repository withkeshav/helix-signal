"""Source health and status endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from services.source_usage import get_source_usage_summary
from core.admin_auth import require_admin_token
from core.limiter import limiter
from core.registry import SOURCES_REGISTRY, SOURCE_INSTANCES, get_source

router = APIRouter()


@router.get("/sources/status")
@limiter.limit("60/minute")
def get_source_status(request: Request, _auth=Depends(require_admin_token)):
    statuses = {}
    for name in SOURCES_REGISTRY:
        try:
            source = get_source(name)
            if source and hasattr(source, "health_check"):
                statuses[name] = source.health_check()
            else:
                statuses[name] = {"source": name, "state": "unknown"}
        except Exception:
            statuses[name] = {"source": name, "state": "error", "error": "health check failed"}
    return {
        "sources": statuses,
        "healthy_count": sum(
            1 for s in statuses.values() if s.get("state") == "closed"
        ),
        "total_count": len(statuses),
    }


@router.get("/sources/usage")
@limiter.limit("60/minute")
def get_sources_usage(request: Request, db: Session = Depends(get_db), _auth=Depends(require_admin_token)) -> dict[str, Any]:
    """Get usage stats for all data sources."""
    return get_source_usage_summary(db)


@router.get("/sources/{name}/config")
@limiter.limit("60/minute")
def get_source_config(request: Request, name: str, _auth=Depends(require_admin_token)):
    if name not in SOURCES_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Source '{name}' not found")
    source = get_source(name)
    return {
        "name": name,
        "registered": True,
        "class": SOURCES_REGISTRY[name].__name__,
        "module": SOURCES_REGISTRY[name].__module__,
        "has_health_check": hasattr(source, "health_check") if source else False,
        "instance_loaded": name in SOURCE_INSTANCES,
    }
