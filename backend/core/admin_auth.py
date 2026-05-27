"""Shared admin token validation for protected API routes."""

from __future__ import annotations

import hashlib
import hmac
import os
import time

from fastapi import Header, HTTPException, Request

_FAILED_ATTEMPTS: dict[str, list[float]] = {}
_LOCKOUT_THRESHOLD = 20
_LOCKOUT_WINDOW_SECONDS = 900  # 15 min


def _ip_key(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _prune_failed() -> None:
    now = time.time()
    stale = [k for k, v in _FAILED_ATTEMPTS.items() if v and (now - v[-1]) > _LOCKOUT_WINDOW_SECONDS]
    for k in stale:
        del _FAILED_ATTEMPTS[k]


def _check_lockout(request: Request) -> None:
    _prune_failed()
    key = _ip_key(request)
    attempts = [t for t in _FAILED_ATTEMPTS.get(key, []) if (time.time() - t) < _LOCKOUT_WINDOW_SECONDS]
    _FAILED_ATTEMPTS[key] = attempts
    if len(attempts) >= _LOCKOUT_THRESHOLD:
        raise HTTPException(status_code=429, detail="Too many failed auth attempts. Try again later.")


def _record_failure(request: Request) -> None:
    key = _ip_key(request)
    _FAILED_ATTEMPTS.setdefault(key, []).append(time.time())


def require_admin_token(
    request: Request,
    token: str | None = Header(None, alias="X-Admin-Token"),
) -> None:
    _check_lockout(request)
    expected = os.getenv("HELIX_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Admin token not configured in the environment.",
        )
    if not token or not hmac.compare_digest(token, expected):
        _record_failure(request)
        raise HTTPException(status_code=403, detail="Forbidden")
