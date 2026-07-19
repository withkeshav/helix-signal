"""Operator event labeling — append-only training corpus (WO-DA-5)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import EventLabel, OsintArticle

VALID_EVENT_TYPES = frozenset({"osint", "anomaly"})
VALID_LABELS = frozenset({"confirmed", "rejected", "noise", "tagged"})


def anomaly_event_id(*, asset_symbol: str, metric: str, timestamp: str) -> str:
    return f"{asset_symbol.upper()}:{metric}:{timestamp}"


def list_labels(db: Session, *, event_type: str, event_id: str) -> list[dict[str, Any]]:
    et = event_type.strip().lower()
    if et not in VALID_EVENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid event_type. Use: {', '.join(sorted(VALID_EVENT_TYPES))}")
    rows = db.execute(
        select(EventLabel)
        .where(EventLabel.event_type == et, EventLabel.event_id == event_id)
        .order_by(EventLabel.created_at.asc())
    ).scalars().all()
    return [_row_to_dict(r) for r in rows]


def add_label(
    db: Session,
    *,
    event_type: str,
    event_id: str,
    label: str,
    tags: list[str] | None = None,
    note: str | None = None,
    user_id: int | None = None,
    user_username: str | None = None,
) -> dict[str, Any]:
    et = event_type.strip().lower()
    if et not in VALID_EVENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid event_type. Use: {', '.join(sorted(VALID_EVENT_TYPES))}")
    lab = label.strip().lower()
    if lab not in VALID_LABELS:
        raise HTTPException(status_code=400, detail=f"Invalid label. Use: {', '.join(sorted(VALID_LABELS))}")
    _validate_event_exists(db, event_type=et, event_id=event_id)
    clean_tags = [t.strip() for t in (tags or []) if t and t.strip()]
    row = EventLabel(
        event_type=et,
        event_id=event_id,
        user_id=user_id,
        user_username=user_username,
        label=lab,
        tags=clean_tags,
        note=(note or "").strip() or None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


def labels_for_export(db: Session, *, event_type: str, event_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not event_ids:
        return {}
    et = event_type.strip().lower()
    rows = db.execute(
        select(EventLabel)
        .where(EventLabel.event_type == et, EventLabel.event_id.in_(event_ids))
        .order_by(EventLabel.created_at.asc())
    ).scalars().all()
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r.event_id, []).append(_row_to_dict(r))
    return out


def _validate_event_exists(db: Session, *, event_type: str, event_id: str) -> None:
    if event_type == "osint":
        try:
            article_id = int(event_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="OSINT event_id must be numeric article id") from exc
        row = db.get(OsintArticle, article_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"OSINT article {event_id} not found")
        return
    if event_type == "anomaly":
        parts = event_id.split(":", 2)
        if len(parts) != 3 or not parts[0] or not parts[1] or not parts[2]:
            raise HTTPException(
                status_code=400,
                detail="Anomaly event_id must be ASSET:metric:ISO-timestamp",
            )


def _row_to_dict(row: EventLabel) -> dict[str, Any]:
    return {
        "id": row.id,
        "event_type": row.event_type,
        "event_id": row.event_id,
        "user_id": row.user_id,
        "user_username": row.user_username,
        "label": row.label,
        "tags": row.tags or [],
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
