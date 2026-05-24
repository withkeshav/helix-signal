import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from services.alerts import load_alert_rules
from services.backfill import run_backfill
from services.governance import build_governance_payload

from backend.core.limiter import limiter

router = APIRouter()


def _admin_token_valid(token: str = Header(None, alias="X-Admin-Token")) -> None:
    import hmac
    expected = os.getenv("HELIX_ADMIN_TOKEN", "")
    if not expected:
        return
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/admin/backfill")
@limiter.limit("5/minute")
def admin_backfill(
    request: Request,
    asset: str,
    days: int = Query(7, ge=7, le=30),
    db: Session = Depends(get_db),
    _auth=Depends(_admin_token_valid),
) -> dict[str, Any]:
    return run_backfill(db, asset=asset, days=days)


@router.get("/alerts/config")
@limiter.limit("60/minute")
def get_alert_config(request: Request) -> list[dict[str, Any]]:
    return load_alert_rules()


@router.get("/governance")
@limiter.limit("60/minute")
def api_governance(request: Request, asset: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_governance_payload(db, asset=asset)
