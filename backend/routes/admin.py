from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from services.alerts import load_alert_rules
from services.backfill import run_backfill
from services.governance import build_governance_payload

from backend.core.admin_auth import require_admin_token
from backend.core.limiter import limiter

router = APIRouter()


@router.post("/admin/backfill")
@limiter.limit("5/minute")
def admin_backfill(
    request: Request,
    asset: str,
    days: int = Query(7, ge=7, le=30),
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    return run_backfill(db, asset=asset, days=days)


@router.get("/alerts/config")
@limiter.limit("10/minute")
def get_alert_config(
    request: Request,
    _auth=Depends(require_admin_token),
) -> list[dict[str, Any]]:
    return load_alert_rules()


@router.get("/reports/summary")
@limiter.limit("10/minute")
def api_report_summary(
    request: Request,
    asset: str = Query(...),
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    from services.reports import generate_summary_report
    return generate_summary_report(db, asset_symbol=asset, days=days)


@router.get("/governance")
@limiter.limit("10/minute")
def api_governance(
    request: Request,
    asset: str = Query(...),
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    return build_governance_payload(db, asset=asset)
