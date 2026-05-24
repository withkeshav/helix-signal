"""Source health and status endpoints."""

from fastapi import APIRouter, HTTPException, Request

from backend.core.limiter import limiter
from backend.core.registry import SOURCES_REGISTRY, get_source

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


@router.get("/sources/{name}/config")
@limiter.limit("60/minute")
def get_source_config(request: Request, name: str):
    if name not in SOURCES_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Source '{name}' not found")
    return {"name": name}
