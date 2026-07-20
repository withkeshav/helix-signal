"""Admin CRUD for ai_providers registry."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from core.limiter import limiter
from database import AiProvider, get_db
from providers.settings_crypto import encrypt_secret
from services.llm_client import seed_default_providers, test_provider_connection

router = APIRouter()


class AiProviderCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    label: str = Field(..., min_length=1, max_length=128)
    base_url: str = Field(..., min_length=8, max_length=512)
    api_key: str = Field(..., min_length=1)
    enabled: bool = True


class AiProviderUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, min_length=8, max_length=512)
    api_key: str | None = None
    enabled: bool | None = None


def _serialize(row: AiProvider) -> dict[str, Any]:
    return {
        "id": row.id,
        "label": row.label,
        "base_url": row.base_url,
        "enabled": row.enabled,
        "api_key_configured": bool(row.api_key_enc),
        "last_test_at": row.last_test_at.isoformat() if row.last_test_at else None,
        "last_test_ok": row.last_test_ok,
        "last_test_error": row.last_test_error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/v1/ai-providers")
@limiter.limit("30/minute")
def list_ai_providers(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> list[dict[str, Any]]:
    seed_default_providers(db)
    rows = db.execute(select(AiProvider).order_by(AiProvider.id.asc())).scalars().all()
    return [_serialize(r) for r in rows]


@router.post("/v1/ai-providers")
@limiter.limit("20/minute")
def create_ai_provider(
    request: Request,
    body: AiProviderCreate,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    if db.get(AiProvider, body.id):
        raise HTTPException(status_code=409, detail=f"Provider {body.id} already exists")
    row = AiProvider(
        id=body.id,
        label=body.label,
        base_url=body.base_url.rstrip("/"),
        api_key_enc=encrypt_secret(body.api_key.strip()),
        enabled=body.enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.get("/v1/ai-providers/{provider_id}")
@limiter.limit("30/minute")
def get_ai_provider(
    request: Request,
    provider_id: str,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    row = db.get(AiProvider, provider_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")
    return _serialize(row)


@router.put("/v1/ai-providers/{provider_id}")
@limiter.limit("20/minute")
def update_ai_provider(
    request: Request,
    provider_id: str,
    body: AiProviderUpdate,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    row = db.get(AiProvider, provider_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")
    if body.label is not None:
        row.label = body.label
    if body.base_url is not None:
        row.base_url = body.base_url.rstrip("/")
    if body.api_key is not None and body.api_key.strip():
        row.api_key_enc = encrypt_secret(body.api_key.strip())
    if body.enabled is not None:
        row.enabled = body.enabled
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.delete("/v1/ai-providers/{provider_id}")
@limiter.limit("20/minute")
def delete_ai_provider(
    request: Request,
    provider_id: str,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, str]:
    row = db.get(AiProvider, provider_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")
    db.delete(row)
    db.commit()
    return {"deleted": provider_id}


@router.post("/v1/ai-providers/{provider_id}/test")
@limiter.limit("10/minute")
def test_ai_provider(
    request: Request,
    provider_id: str,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    row = db.get(AiProvider, provider_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")
    return test_provider_connection(db, provider_id)
