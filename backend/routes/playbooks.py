"""Playbooks API endpoints — full CRUD for custom configuration playbooks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from core.limiter import limiter
from database import Playbook, get_db
from providers.settings import PLAYBOOKS as BUILTIN_PLAYBOOKS, apply_playbook as apply_builtin_playbook

router = APIRouter()


class PlaybookCreate(BaseModel):
    name: str
    label: str
    description: str
    settings: dict[str, Any]


class PlaybookUpdate(BaseModel):
    label: str | None = None
    description: str | None = None
    settings: dict[str, Any] | None = None


def _serialize(pb: Playbook) -> dict[str, Any]:
    return {
        "id": pb.id,
        "name": pb.name,
        "label": pb.label,
        "description": pb.description,
        "settings": pb.settings,
        "is_builtin": pb.is_builtin,
        "created_at": pb.created_at.isoformat() if pb.created_at else None,
        "updated_at": pb.updated_at.isoformat() if pb.updated_at else None,
    }


def seed_builtin_playbooks(db: Session) -> None:
    existing = {p.name for p in db.execute(select(Playbook).where(Playbook.is_builtin)).scalars().all()}
    now = datetime.now(timezone.utc)
    for name, data in BUILTIN_PLAYBOOKS.items():
        if name not in existing:
            pb = Playbook(
                name=name,
                label=data["label"],
                description=data["description"],
                settings=data["settings"],
                is_builtin=True,
                created_at=now,
                updated_at=now,
            )
            db.add(pb)
    db.commit()


def get_all_playbooks(db: Session) -> list[dict[str, Any]]:
    """Return all playbooks (built-in + custom), with built-in first."""
    rows = db.execute(select(Playbook).order_by(Playbook.is_builtin.desc(), Playbook.label.asc())).scalars().all()
    return [_serialize(r) for r in rows]


def apply_playbook_by_name(name: str, db: Session) -> list[dict[str, Any]]:
    """Apply a playbook by name (checks DB first, falls back to built-in)."""
    pb = db.execute(select(Playbook).where(Playbook.name == name)).scalars().first()
    if pb is None:
        return apply_builtin_playbook(name, db)
    changes: list[dict[str, Any]] = []
    for key, value in pb.settings.items():
        from providers.settings import set_setting
        set_setting(key, value, db)
        changes.append({"key": key, "value": value})
    return changes


@router.get("/playbooks")
@limiter.limit("30/minute")
async def list_playbooks(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> list[dict[str, Any]]:
    """List all playbooks (built-in + custom)."""
    return get_all_playbooks(db)


@router.post("/playbooks")
@limiter.limit("10/minute")
async def create_playbook(
    request: Request,
    body: PlaybookCreate,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    """Create a new custom playbook."""
    name = body.name.strip().lower().replace(" ", "_")
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    existing = db.execute(select(Playbook).where(Playbook.name == name)).scalars().first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Playbook '{name}' already exists")
    if name in BUILTIN_PLAYBOOKS:
        raise HTTPException(status_code=409, detail=f"Cannot override built-in playbook '{name}'")
    if not body.settings:
        raise HTTPException(status_code=400, detail="At least one setting is required")
    now = datetime.now(timezone.utc)
    pb = Playbook(
        name=name,
        label=body.label or body.name,
        description=body.description or "",
        settings=body.settings,
        is_builtin=False,
        created_at=now,
        updated_at=now,
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)
    return _serialize(pb)


@router.get("/playbooks/{playbook_id}")
@limiter.limit("30/minute")
async def get_playbook(
    request: Request,
    playbook_id: str,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    """Get a specific playbook by id (int) or name (str)."""
    try:
        pb_id = int(playbook_id)
        pb = db.execute(select(Playbook).where(Playbook.id == pb_id)).scalars().first()
    except ValueError:
        pb = db.execute(select(Playbook).where(Playbook.name == playbook_id)).scalars().first()
    if pb is None:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return _serialize(pb)


@router.put("/playbooks/{playbook_id}")
@limiter.limit("10/minute")
async def update_playbook(
    request: Request,
    playbook_id: str,
    body: PlaybookUpdate,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    """Update a custom playbook."""
    try:
        pb_id = int(playbook_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Playbook ID must be an integer")
    pb = db.execute(select(Playbook).where(Playbook.id == pb_id, Playbook.is_builtin.is_(False))).scalars().first()
    if pb is None:
        raise HTTPException(status_code=404, detail="Custom playbook not found")
    if body.label is not None:
        pb.label = body.label
    if body.description is not None:
        pb.description = body.description
    if body.settings is not None:
        if not body.settings:
            raise HTTPException(status_code=400, detail="At least one setting is required")
        pb.settings = body.settings
    pb.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pb)
    return _serialize(pb)


@router.delete("/playbooks/{playbook_id}")
@limiter.limit("10/minute")
async def delete_playbook(
    request: Request,
    playbook_id: str,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    """Delete a custom playbook. Built-in playbooks cannot be deleted."""
    try:
        pb_id = int(playbook_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Playbook ID must be an integer")
    pb = db.execute(select(Playbook).where(Playbook.id == pb_id, Playbook.is_builtin.is_(False))).scalars().first()
    if pb is None:
        raise HTTPException(status_code=404, detail="Custom playbook not found")
    db.delete(pb)
    db.commit()
    return {"ok": True, "id": pb_id, "status": "deleted"}
