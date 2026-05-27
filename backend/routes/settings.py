from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.admin_auth import require_admin_token
from backend.core.limiter import limiter
from database import get_db
from providers.settings import get_all_settings, set_setting

router = APIRouter()


class SettingUpdate(BaseModel):
    key: str
    value: bool | int | str


@router.get("/settings")
@limiter.limit("60/minute")
def api_get_settings(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> list[dict]:
    settings = get_all_settings(db)
    for s in settings:
        s.pop("key_env", None)
    return settings


@router.put("/settings")
@limiter.limit("30/minute")
def api_update_setting(
    request: Request,
    body: SettingUpdate,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict:
    try:
        set_setting(body.key, body.value, db)
        return {"ok": True, "key": body.key, "value": body.value}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
