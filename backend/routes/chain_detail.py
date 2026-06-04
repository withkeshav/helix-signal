from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from services.chain_detail import build_chain_detail

from core.limiter import limiter

router = APIRouter()


@router.get("/chains/{chain_key}")
@limiter.limit("60/minute")
def chain_detail(request: Request, chain_key: str, asset: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_chain_detail(db, chain_key=chain_key, asset=asset)
