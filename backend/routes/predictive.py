from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from database import get_db

from core.limiter import limiter

router = APIRouter()


@router.get("/predictive")
@limiter.limit("60/minute")
def api_predictive(
    request: Request,
    asset: str = Query("USDT"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from services.predictive import run_predictive_bundle

    return run_predictive_bundle(db, asset_symbol=asset.upper())
