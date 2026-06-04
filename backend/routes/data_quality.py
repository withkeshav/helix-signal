"""Data quality dashboard routes."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from typing import Dict, Any

from database import get_db
from core.admin_auth import require_admin_token
from core.limiter import limiter
from data_quality.metrics import get_all_data_quality_metrics, get_data_quality_report

router = APIRouter()

@router.get("/data-quality/overview")
@limiter.limit("30/minute")
def get_data_quality_overview(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> Dict[str, Any]:
    """Get data quality overview (admin only)."""
    return get_all_data_quality_metrics(db)

@router.get("/data-quality/report")
@limiter.limit("30/minute")
def get_data_quality_report_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> Dict[str, Any]:
    """Get complete data quality report (admin only)."""
    return get_data_quality_report(db)

@router.get("/data-quality/sources")
@limiter.limit("30/minute")
def get_source_quality(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> Dict[str, Any]:
    """Get source quality metrics (admin only)."""
    from data_quality.metrics import DataQualityMetrics
    return DataQualityMetrics.get_source_quality_metrics(db)

@router.get("/data-quality/assets")
@limiter.limit("30/minute")
def get_asset_quality(
    request: Request,
    asset: str = None,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> Dict[str, Any]:
    """Get asset quality metrics (admin only)."""
    from data_quality.metrics import DataQualityMetrics
    return DataQualityMetrics.get_asset_data_quality(db, asset)