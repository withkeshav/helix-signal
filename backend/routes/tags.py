"""Address tag API — CRUD for AddressTag intelligence tags."""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from database import AddressTag, get_db
from schemas import AddressTagCreate, AddressTagOut

router = APIRouter()


@router.get("/v1/tags/export", dependencies=[Depends(require_admin_token)])
def export_tags_csv(db: Session = Depends(get_db)):
    stmt = select(AddressTag).order_by(AddressTag.created_at.desc())
    tags = db.execute(stmt).scalars().all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "address", "chain", "source", "label", "category", "confidence", "created_at"])
    for t in tags:
        writer.writerow([t.id, t.address, t.chain, t.source, t.label, t.category, t.confidence, t.created_at.isoformat() if t.created_at else ""])
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=address_tags.csv"})


@router.get("/v1/tags/{address}", response_model=list[AddressTagOut])
def get_tags_for_address(address: str, chain: str | None = None, db: Session = Depends(get_db)):
    stmt = select(AddressTag).where(AddressTag.address == address.lower())
    if chain:
        stmt = stmt.where(AddressTag.chain == chain.lower())
    return db.execute(stmt).scalars().all()


@router.post("/v1/tags", response_model=AddressTagOut, dependencies=[Depends(require_admin_token)])
def create_tag(body: AddressTagCreate, db: Session = Depends(get_db)):
    tag = AddressTag(
        address=body.address.lower(),
        chain=body.chain.lower() if body.chain else None,
        source="manual",
        label=body.label,
        category=body.category,
        confidence=body.confidence,
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/v1/tags/{tag_id}", dependencies=[Depends(require_admin_token)])
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    stmt = select(AddressTag).where(AddressTag.id == tag_id)
    tag = db.execute(stmt).scalar_one_or_none()
    if not tag:
            raise HTTPException(status_code=404, detail="Tag not found")
    db.delete(tag)
    db.commit()
    return {"ok": True}
