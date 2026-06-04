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
_LOCKOUT_REDIS_PREFIX = "helix:auth:lockout:"


def _ip_key(request: Request) -> str:
    cidr = os.getenv("TRUSTED_PROXY_CIDR", "").strip()
    if cidr and request.client:
        from ipaddress import ip_address, ip_network
        if ip_address(request.client.host) not in ip_network(cidr, strict=False):
            return hashlib.sha256(request.client.host.encode()).hexdigest()[:16]
    forwarded = request.headers.get("X-Forwarded-For", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _redis_client():
    try:
        from cache_manager import cache
        return cache._redis if cache._redis else None
    except Exception:
        return None


def _prune_failed() -> None:
    now = time.time()
    stale = [k for k, v in _FAILED_ATTEMPTS.items() if v and (now - v[-1]) > _LOCKOUT_WINDOW_SECONDS]
    for k in stale:
        del _FAILED_ATTEMPTS[k]


def _check_lockout(request: Request) -> None:
    key = _ip_key(request)
    rc = _redis_client()
    if rc:
        count = rc.get(_LOCKOUT_REDIS_PREFIX + key)
        if count and int(count) >= _LOCKOUT_THRESHOLD:
            raise HTTPException(status_code=429, detail="Too many failed auth attempts. Try again later.")
        return
    _prune_failed()
    attempts = [t for t in _FAILED_ATTEMPTS.get(key, []) if (time.time() - t) < _LOCKOUT_WINDOW_SECONDS]
    _FAILED_ATTEMPTS[key] = attempts
    if len(attempts) >= _LOCKOUT_THRESHOLD:
        raise HTTPException(status_code=429, detail="Too many failed auth attempts. Try again later.")


def _record_failure(request: Request) -> None:
    key = _ip_key(request)
    rc = _redis_client()
    if rc:
        pipe = rc.pipeline()
        pipe.incr(_LOCKOUT_REDIS_PREFIX + key)
        pipe.expire(_LOCKOUT_REDIS_PREFIX + key, _LOCKOUT_WINDOW_SECONDS)
        pipe.execute()
        return
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
