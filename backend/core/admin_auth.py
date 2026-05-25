"""Shared admin token validation for protected API routes."""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def require_admin_token(token: str | None = Header(None, alias="X-Admin-Token")) -> None:
    expected = os.getenv("HELIX_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Admin token not configured. Set HELIX_ADMIN_TOKEN in the environment.",
        )
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Forbidden")
