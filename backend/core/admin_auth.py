"""Shared admin token validation for protected API routes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Header, HTTPException, Request

_FAILED_ATTEMPTS: dict[str, list[float]] = {}
_LOCKOUT_THRESHOLD = 20
_LOCKOUT_WINDOW_SECONDS = 900  # 15 min
_LOCKOUT_REDIS_PREFIX = "helix:auth:lockout:"
_SIGNING_KEY_ENV = "SESSION_SIGNING_KEY"


def _ip_key(request: Request) -> str:
    import ipaddress as _ipa
    cidr = os.getenv("TRUSTED_PROXY_CIDR", "").strip()
    raw = request.client.host if request.client else "unknown"

    if cidr and raw != "unknown":
        try:
            client_ip = _ipa.ip_address(raw)
            if client_ip in _ipa.ip_network(cidr, strict=False):
                forwarded = request.headers.get("X-Forwarded-For", "")
                if forwarded:
                    raw = forwarded.split(",")[0].strip()
        except ValueError:
            pass

    try:
        raw = str(_ipa.ip_address(raw))
    except ValueError:
        pass

    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _redis_client():
    try:
        from core.cache_manager import cache
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


def _get_signing_key() -> str:
    """Return the dedicated session-signing key, or raise 503 if missing."""
    key = os.getenv(_SIGNING_KEY_ENV, "").strip()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="SESSION_SIGNING_KEY not configured. Generate one with: openssl rand -hex 32",
        )
    return key


def _sign_session_token(payload: dict) -> str:
    """Create a short-lived signed session token (HMAC-SHA256), expiring in 30 min.

    Reads the dedicated SESSION_SIGNING_KEY env var and fails CLOSED (raises 503)
    if it is missing or empty.
    """
    secret = _get_signing_key()
    payload = {**payload, "exp": int(time.time()) + 1800}
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def _verify_session_token(token: str) -> dict | None:
    """Verify a signed session token and return its payload, or None if invalid/expired.

    Uses constant-time HMAC comparison via hmac.compare_digest.
    Rejects expired tokens (exp claim check).
    Fails CLOSED: if SESSION_SIGNING_KEY is missing/empty, ALL signed tokens are rejected.
    """
    secret = os.getenv(_SIGNING_KEY_ENV, "").strip()
    if not secret:
        return None  # fail closed — cannot verify without a key

    try:
        body, sig = token.rsplit(".", 1)
        expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        padding = 4 - len(body) % 4
        if padding != 4:
            body += "=" * padding
        payload: dict = json.loads(base64.urlsafe_b64decode(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def require_admin_token(
    request: Request,
    token: str | None = Header(None, alias="X-Admin-Token"),
) -> None:
    """Dependency: require a valid admin session token or legacy X-Admin-Token.

    Verification order:
    1. Absent token → 401 (no lockout increment — fixes R-1b self-DoS).
    2. Signed session token → HMAC-verify + enforce role=="admin".
    3. Legacy X-Admin-Token → constant-time compare with HELIX_ADMIN_TOKEN (rollout-safe).
    4. Otherwise → record failure + 403.
    """
    _check_lockout(request)

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Signed session token path — validates HMAC, expiry, and admin role
    payload = _verify_session_token(token)
    if payload is not None:
        if payload.get("role") != "admin":
            _record_failure(request)
            raise HTTPException(status_code=403, detail="Forbidden: admin role required")
        return

    # Legacy static X-Admin-Token fallback
    legacy = os.getenv("HELIX_ADMIN_TOKEN", "").strip()
    if legacy and hmac.compare_digest(token, legacy):
        return

    _record_failure(request)
    raise HTTPException(status_code=403, detail="Forbidden")
