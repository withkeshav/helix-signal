from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from services.osint import (
    get_osint_feed,
    get_sentiment_timeseries,
    get_attestation_status,
    correlate_sentiment_depeg,
)

from backend.core.limiter import limiter

router = APIRouter()


@router.get("/osint/feed")
@limiter.limit("60/minute")
def api_osint_feed(
    request: Request,
    asset: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return get_osint_feed(db, asset=asset, limit=limit)


@router.get("/osint/sentiment")
@limiter.limit("60/minute")
def api_osint_sentiment(
    request: Request,
    asset: str | None = Query(None),
    window_days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return get_sentiment_timeseries(db, asset=asset, window_days=window_days)


@router.get("/osint/attestation")
@limiter.limit("60/minute")
def api_osint_attestation(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_attestation_status(db=db)


@router.get("/osint/correlate")
@limiter.limit("60/minute")
def api_osint_correlate(
    request: Request,
    asset: str = Query(...),
    window_hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return correlate_sentiment_depeg(db, asset=asset, window_hours=window_hours)
