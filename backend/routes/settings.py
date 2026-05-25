from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from providers.settings import get_all_settings, set_setting

router = APIRouter()


class SettingUpdate(BaseModel):
    key: str
    value: bool | int | str


@router.get("/settings")
def api_get_settings(db: Session = Depends(get_db)) -> list[dict]:
    return get_all_settings(db)


@router.put("/settings")
def api_update_setting(body: SettingUpdate, db: Session = Depends(get_db)) -> dict:
    try:
        set_setting(body.key, body.value, db)
        return {"ok": True, "key": body.key, "value": body.value}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
