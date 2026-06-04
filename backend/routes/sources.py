"""Source health and status endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from services.source_usage import get_source_usage, get_source_usage_summary
from core.limiter import limiter
from core.registry import SOURCES_REGISTRY, get_source

router = APIRouter()


@router.get("/sources/status")
@limiter.limit("60/minute")
def get_source_status(request: Request):
    statuses = {}
    for name in SOURCES_REGISTRY:
        source = get_source(name)
        if source and hasattr(source, "health_check"):
            statuses[name] = source.health_check()
        else:
            statuses[name] = {"source": name, "state": "unknown"}
    return {
        "sources": statuses,
        "healthy_count": sum(
            1 for s in statuses.values() if s.get("state") == "closed"
        ),
        "total_count": len(statuses),
    }


@router.get("/sources/usage")
@limiter.limit("60/minute")
def get_sources_usage(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get usage stats for all data sources."""
    return get_source_usage_summary(db)


@router.get("/sources/{name}/config")
@limiter.limit("60/minute")
def get_source_config(request: Request, name: str):
    if name not in SOURCES_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Source '{name}' not found")
    return {"name": name}
