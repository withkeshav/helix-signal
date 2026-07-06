"""Reports API endpoints — summary only. CRUD stubs removed (Phase 1.1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from core.limiter import limiter
from database import get_db

router = APIRouter()


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
