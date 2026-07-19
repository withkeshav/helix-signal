"""API key + tiered intelligence auth (self-host first, SaaS-ready).

Tiers (final.md):
  - public: always anonymous (health/version)
  - read_open: anonymous when api_auth_mode=open; key/admin when key_required
  - keyed_always: key or admin in both modes (investigate, alerts, blacklist, tags write)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.admin_auth import (
    SESSION_COOKIE_NAME,
    _extract_admin_token,
    _verify_session_token,
)
from database import ApiKey, get_db

log = logging.getLogger(__name__)

VALID_SCOPES = frozenset({"intelligence:read", "investigate:write", "admin"})
DEFAULT_SCOPES = ["intelligence:read"]

# In-process RPM fallback when Redis is absent (lock rule 12).
_RPM_BUCKETS: dict[int, list[float]] = {}
_LAST_USED_THROTTLE: dict[int, float] = {}
_LAST_USED_MIN_INTERVAL = 60.0
_REDIS_WARNED = False


@dataclass
class AuthContext:
    kind: str  # anonymous | api_key | admin_session | legacy_token
    scopes: set[str] = field(default_factory=set)
    api_key_id: int | None = None
    api_key_name: str | None = None


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Return (raw_key, key_prefix, key_hash). Raw is shown once to the caller."""
    raw = f"hx_{secrets.token_urlsafe(32)}"
    prefix = raw[:12]
    return raw, prefix, hash_api_key(raw)


def _get_auth_mode(db: Session | None) -> str:
    try:
        from providers.settings import get_setting

        mode = str(get_setting("api_auth_mode", db) or "open").strip().lower()
        if mode in ("open", "key_required"):
            return mode
    except Exception:
        pass
    env = os.getenv("API_AUTH_MODE", "open").strip().lower()
    return env if env in ("open", "key_required") else "open"


def _extract_api_key_header(request: Request, authorization: str | None, x_api_key: str | None) -> str | None:
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    if authorization:
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
            if token.startswith("hx_"):
                return token
    return None


def _lookup_api_key(db: Session, raw_key: str) -> ApiKey | None:
    prefix = raw_key[:12]
    digest = hash_api_key(raw_key)
    candidates = db.execute(
        select(ApiKey).where(
            ApiKey.key_prefix == prefix,
            ApiKey.enabled.is_(True),
            ApiKey.revoked_at.is_(None),
        )
    ).scalars().all()
    for row in candidates:
        if hmac.compare_digest(row.key_hash, digest):
            return row
    return None


def _check_rpm(api_key: ApiKey) -> None:
    global _REDIS_WARNED
    rpm = max(1, int(api_key.rate_limit_rpm or 60))
    key_id = api_key.id
    now = time.time()
    window = 60.0

    rc = None
    try:
        from core.cache_manager import cache

        rc = cache._redis if cache._redis else None
    except Exception:
        rc = None

    if rc is not None:
        try:
            rkey = f"helix:api_key_rpm:{key_id}"
            count = rc.incr(rkey)
            if count == 1:
                rc.expire(rkey, 60)
            if int(count) > rpm:
                raise HTTPException(status_code=429, detail="API key rate limit exceeded")
            return
        except HTTPException:
            raise
        except Exception:
            rc = None

    if not _REDIS_WARNED:
        log.warning("Redis unavailable for per-key RPM — using in-process counter (not shared across workers)")
        _REDIS_WARNED = True

    bucket = [t for t in _RPM_BUCKETS.get(key_id, []) if now - t < window]
    if len(bucket) >= rpm:
        _RPM_BUCKETS[key_id] = bucket
        raise HTTPException(status_code=429, detail="API key rate limit exceeded")
    bucket.append(now)
    _RPM_BUCKETS[key_id] = bucket


def _schedule_last_used(background_tasks: BackgroundTasks | None, key_id: int) -> None:
    if background_tasks is None:
        return
    now = time.time()
    last = _LAST_USED_THROTTLE.get(key_id, 0.0)
    if now - last < _LAST_USED_MIN_INTERVAL:
        return
    _LAST_USED_THROTTLE[key_id] = now

    def _write() -> None:
        from database import SessionLocal

        with SessionLocal() as db:
            row = db.get(ApiKey, key_id)
            if row is None:
                return
            row.last_used_at = datetime.now(timezone.utc)
            db.commit()

    background_tasks.add_task(_write)


def resolve_auth(
    request: Request,
    db: Session,
    background_tasks: BackgroundTasks | None = None,
    authorization: str | None = None,
    x_api_key: str | None = None,
    x_admin_token: str | None = None,
) -> AuthContext:
    raw_key = _extract_api_key_header(request, authorization, x_api_key)
    if raw_key:
        row = _lookup_api_key(db, raw_key)
        if row is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        _check_rpm(row)
        _schedule_last_used(background_tasks, row.id)
        scopes = {str(s) for s in (row.scopes or []) if str(s) in VALID_SCOPES}
        return AuthContext(kind="api_key", scopes=scopes, api_key_id=row.id, api_key_name=row.name)

    token = _extract_admin_token(request, x_admin_token)
    if token:
        payload = _verify_session_token(token)
        if payload is not None and payload.get("role") == "admin":
            return AuthContext(kind="admin_session", scopes=set(VALID_SCOPES))
        legacy = os.getenv("HELIX_ADMIN_TOKEN", "").strip()
        if legacy and hmac.compare_digest(token, legacy):
            return AuthContext(kind="legacy_token", scopes=set(VALID_SCOPES))

    return AuthContext(kind="anonymous", scopes=set())


def _enforce_scopes(ctx: AuthContext, needed: tuple[str, ...]) -> None:
    if ctx.kind in ("admin_session", "legacy_token"):
        return
    if ctx.kind == "api_key":
        if "admin" in ctx.scopes:
            return
        if needed and not any(s in ctx.scopes for s in needed):
            raise HTTPException(
                status_code=403,
                detail=f"API key missing required scope: one of {', '.join(needed)}",
            )
        return
    raise HTTPException(status_code=401, detail="Authentication required")


def require_read_open(*scopes: str) -> Callable:
    """Anonymous OK in open mode; otherwise key/admin with scopes."""

    needed = scopes or ("intelligence:read",)

    def dependency(
        request: Request,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        authorization: str | None = Header(None, alias="Authorization"),
        x_api_key: str | None = Header(None, alias="X-API-Key"),
        x_admin_token: str | None = Header(None, alias="X-Admin-Token"),
    ) -> AuthContext:
        ctx = resolve_auth(request, db, background_tasks, authorization, x_api_key, x_admin_token)
        mode = _get_auth_mode(db)
        if mode == "open" and ctx.kind == "anonymous":
            return ctx
        _enforce_scopes(ctx, needed)
        return ctx

    return dependency


def require_keyed_always(*scopes: str) -> Callable:
    """Key or admin required in both auth modes — never anonymous."""

    needed = scopes or ("intelligence:read",)

    def dependency(
        request: Request,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        authorization: str | None = Header(None, alias="Authorization"),
        x_api_key: str | None = Header(None, alias="X-API-Key"),
        x_admin_token: str | None = Header(None, alias="X-Admin-Token"),
    ) -> AuthContext:
        ctx = resolve_auth(request, db, background_tasks, authorization, x_api_key, x_admin_token)
        if ctx.kind == "anonymous":
            raise HTTPException(status_code=401, detail="Authentication required")
        _enforce_scopes(ctx, needed)
        return ctx

    return dependency
