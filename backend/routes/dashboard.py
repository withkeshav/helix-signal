from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from database import get_db
from schemas import AssetConfigOut, DashboardResponse
from services.dashboard import build_dashboard_response
from services.cache import get_or_build_dashboard
from signal_engine.core import load_enabled_assets

from core.limiter import limiter

router = APIRouter()


@router.get("/dashboard", response_model=DashboardResponse)
@limiter.limit("60/minute")
def dashboard(request: Request, asset: str | None = None, db: Session = Depends(get_db)) -> DashboardResponse:
    def _build() -> dict[str, Any]:
        return build_dashboard_response(db, asset).model_dump(mode="json")

    payload = get_or_build_dashboard(asset, _build)
    payload.pop("_cache", None)
    return DashboardResponse.model_validate(payload)


@router.get("/assets", response_model=list[AssetConfigOut])
@limiter.limit("60/minute")
def assets(request: Request) -> list[AssetConfigOut]:
    enabled_assets = load_enabled_assets()
    return [AssetConfigOut(**asset) for asset in enabled_assets]
