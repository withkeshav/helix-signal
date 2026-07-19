"""Event label routes — operator labeling corpus (WO-DA-5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.admin_auth import _extract_admin_token, _verify_session_token, require_admin_token
from core.api_auth import require_read_open
from core.limiter import limiter
from database import User, get_db
from services.event_labels import add_label, list_labels

router = APIRouter()


class EventLabelIn(BaseModel):
    label: str
    tags: list[str] = Field(default_factory=list)
    note: str | None = None


@router.get(
    "/events/{event_type}/{event_id}/labels",
    dependencies=[Depends(require_read_open("intelligence:read"))],
)
@limiter.limit("120/minute")
def get_event_labels(
    request: Request,
    event_type: str,
    event_id: str,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return list_labels(db, event_type=event_type, event_id=event_id)


@router.post(
    "/events/{event_type}/{event_id}/labels",
    dependencies=[Depends(require_admin_token)],
)
@limiter.limit("30/minute")
def post_event_label(
    request: Request,
    event_type: str,
    event_id: str,
    body: EventLabelIn,
    db: Session = Depends(get_db),
    token: str | None = Header(None, alias="X-Admin-Token"),
) -> dict[str, Any]:
    user_id: int | None = None
    user_username: str | None = None
    raw = _extract_admin_token(request, token)
    payload = _verify_session_token(raw) if raw else None
    if payload and payload.get("sub") is not None:
        user_id = int(payload["sub"])
        row = db.get(User, user_id)
        if row:
            user_username = row.username
    return add_label(
        db,
        event_type=event_type,
        event_id=event_id,
        label=body.label,
        tags=body.tags,
        note=body.note,
        user_id=user_id,
        user_username=user_username,
    )
