from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from prometheus_client import generate_latest
from sqlalchemy.orm import Session

from database import AssetTrendSnapshot, SourceStatus, get_db
from services.health import build_health_payload

from backend.core.limiter import limiter

router = APIRouter()


@router.get("/health")
@limiter.limit("60/minute")
def api_health(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    scheduler = getattr(request.app.state, "scheduler", None)
    return build_health_payload(db, scheduler=scheduler)
