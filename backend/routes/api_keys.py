"""API key management REST — admin session only; raw key returned once on create."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from core.api_auth import DEFAULT_SCOPES, VALID_SCOPES, generate_api_key
from core.limiter import limiter
from database import ApiKey, get_db

router = APIRouter()


class AccessPolicyIn(BaseModel):
    allowed_bundles: list[str] = Field(default_factory=list)
    allowed_assets: list[str] = Field(default_factory=list)
    max_history_hours: int | None = Field(default=None, ge=1, le=8760)


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=lambda: list(DEFAULT_SCOPES))
    rate_limit_rpm: int = Field(default=60, ge=1, le=10000)
    access_policy: AccessPolicyIn | None = None


class ApiKeyOut(BaseModel):
    id: int
    name: str
    key_prefix: str
    scopes: list[str]
    access_policy: dict[str, Any] | None
    enabled: bool
    rate_limit_rpm: int
    created_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


def _normalize_policy_dict(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw:
        return None
    out: dict[str, Any] = {}
    if raw.get("allowed_bundles") is not None:
        out["allowed_bundles"] = list(raw.get("allowed_bundles") or [])
    if raw.get("allowed_assets") is not None:
        out["allowed_assets"] = [str(a).upper() for a in (raw.get("allowed_assets") or [])]
    if raw.get("max_history_hours") is not None:
        out["max_history_hours"] = raw["max_history_hours"]
    return out or None


def _serialize(row: ApiKey) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "key_prefix": row.key_prefix,
        "scopes": list(row.scopes or []),
        "access_policy": _normalize_policy_dict(row.access_policy),
        "enabled": row.enabled,
        "rate_limit_rpm": row.rate_limit_rpm,
        "created_at": row.created_at,
        "last_used_at": row.last_used_at,
        "revoked_at": row.revoked_at,
    }


def _build_access_policy(body: ApiKeyCreate, scopes: list[str]) -> dict[str, Any] | None:
    if body.access_policy is not None:
        policy = body.access_policy.model_dump(exclude_none=True)
        bundles = [b for b in policy.get("allowed_bundles", []) if b in VALID_SCOPES]
        if bundles:
            policy["allowed_bundles"] = bundles
        elif "allowed_bundles" in policy:
            policy["allowed_bundles"] = scopes
        assets = [str(a).strip().upper() for a in policy.get("allowed_assets", []) if str(a).strip()]
        if assets:
            policy["allowed_assets"] = assets
        elif "allowed_assets" in policy:
            del policy["allowed_assets"]
        return policy or None
    return {"allowed_bundles": scopes}


@router.get("/v1/api-keys", response_model=list[ApiKeyOut])
@limiter.limit("30/minute")
def list_api_keys(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> list[dict[str, Any]]:
    rows = db.execute(select(ApiKey).order_by(ApiKey.id.desc())).scalars().all()
    return [_serialize(r) for r in rows]


@router.post("/v1/api-keys")
@limiter.limit("10/minute")
def create_api_key(
    request: Request,
    body: ApiKeyCreate,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    scopes = [s for s in body.scopes if s in VALID_SCOPES]
    if not scopes:
        raise HTTPException(status_code=400, detail=f"scopes must include one of: {', '.join(sorted(VALID_SCOPES))}")
    raw, prefix, digest = generate_api_key()
    row = ApiKey(
        name=body.name.strip(),
        key_prefix=prefix,
        key_hash=digest,
        scopes=scopes,
        access_policy=_build_access_policy(body, scopes),
        enabled=True,
        rate_limit_rpm=body.rate_limit_rpm,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    out = _serialize(row)
    out["api_key"] = raw  # shown once
    return out


@router.delete("/v1/api-keys/{key_id}")
@limiter.limit("10/minute")
def revoke_api_key(
    request: Request,
    key_id: int,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    row = db.get(ApiKey, key_id)
    if row is None:
        raise HTTPException(status_code=404, detail="API key not found")
    row.enabled = False
    row.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "id": key_id, "status": "revoked"}
