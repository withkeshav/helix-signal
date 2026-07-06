"""On-chain whale flow and holder concentration API (transform.md §4.2, §5.1–5.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from core.limiter import limiter
from database import get_db
from services.onchain import get_holder_concentration, get_whale_flow

router = APIRouter()


@router.get("/onchain/whale-flow")
@limiter.limit("60/minute")
def api_whale_flow(
    request: Request,
    asset: str = Query("USDT"),
    db: Session = Depends(get_db),
) -> dict:
    return get_whale_flow(asset, db)


@router.get("/onchain/holder-concentration")
@limiter.limit("60/minute")
def api_holder_concentration(
    request: Request,
    asset: str = Query("USDT"),
    db: Session = Depends(get_db),
) -> dict:
    return get_holder_concentration(asset, db)
