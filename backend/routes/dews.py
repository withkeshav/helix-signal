"""DEWS — tiered explainable depeg watch score (transform.md §4.3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from structlog import get_logger

from core.limiter import limiter
from database import get_db
from core.api_auth import require_read_open
from services.dews_payload import build_dews_payload

log = get_logger(__name__)
router = APIRouter()


@router.get("/dews", dependencies=[Depends(require_read_open("intelligence:read"))])
@limiter.limit("60/minute")
def get_dews(
    request: Request,
    asset: str = Query("USDT"),
    db: Session = Depends(get_db),
) -> dict:
    """Explainable depeg-watch score per asset with tier traceability."""
    return build_dews_payload(db, asset.upper())
