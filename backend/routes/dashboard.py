from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from core.api_auth import require_read_open, require_keyed_always
from core.limiter import limiter
from database import get_db
from schemas import AssetConfigOut, DashboardResponse, DashboardSummaryItemOut
from services.asset_overlay import catalog_assets, set_asset_enabled
from services.asset_overlay import load_enabled_assets_with_overrides as load_enabled_assets
from services.cache import get_or_build_dashboard
from services.dashboard import build_dashboard_response, build_dashboard_summary

router = APIRouter()


class AssetEnabledBody(BaseModel):
    enabled: bool


@router.get("/dashboard", response_model=DashboardResponse)
@limiter.limit("60/minute")
def dashboard(
    request: Request,
    asset: str | None = None,
    db: Session = Depends(get_db),
    _auth=Depends(require_read_open("intelligence:read")),
) -> DashboardResponse:
    def _build() -> dict[str, Any]:
        return build_dashboard_response(db, asset).model_dump(mode="json")

    payload = get_or_build_dashboard(asset, _build)
    payload.pop("_cache", None)
    return DashboardResponse.model_validate(payload)


@router.get("/dashboard/summary", response_model=list[DashboardSummaryItemOut])
@limiter.limit("60/minute")
def dashboard_summary(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_read_open("intelligence:read")),
) -> list[DashboardSummaryItemOut]:
    return [DashboardSummaryItemOut.model_validate(row) for row in build_dashboard_summary(db)]


@router.get("/assets", response_model=list[AssetConfigOut])
@limiter.limit("60/minute")
def assets(request: Request, db: Session = Depends(get_db), _auth=Depends(require_read_open("intelligence:read"))) -> list[AssetConfigOut]:
    enabled_assets = load_enabled_assets(db)
    return [AssetConfigOut(**asset) for asset in enabled_assets]


@router.get("/assets/catalog")
@limiter.limit("30/minute")
def assets_catalog(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_keyed_always("admin")),
) -> list[dict[str, Any]]:
    return catalog_assets(db)


@router.put("/assets/{symbol}/enabled")
@limiter.limit("30/minute")
def put_asset_enabled(
    request: Request,
    symbol: str,
    body: AssetEnabledBody,
    db: Session = Depends(get_db),
    _auth=Depends(require_keyed_always("admin")),
) -> dict[str, Any]:
    try:
        overrides = set_asset_enabled(db, symbol, body.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return {"ok": True, "symbol": symbol.upper(), "enabled": body.enabled, "overrides": overrides}
