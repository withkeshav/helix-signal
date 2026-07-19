"""Authentication API endpoints."""

from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.admin_auth import (
    SESSION_COOKIE_NAME,
    _extract_admin_token,
    _sign_session_token,
    _verify_session_token,
    require_admin_token,
)
from core.limiter import limiter
from database import User, get_db
from services.user_service import authenticate_user

router = APIRouter()
security = HTTPBearer()


@router.post("/auth/login")
@limiter.limit("10/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """User login endpoint."""
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    session_token = _sign_session_token({"sub": user.id, "role": user.role})
    body = {"access_token": session_token, "token_type": "bearer", "username": user.username, "role": user.role}
    response = JSONResponse(content=body)
    secure = os.getenv("HELIX_COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes")
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=1800,
        secure=secure,
    )
    return response


@router.post("/auth/logout")
@limiter.limit("30/minute")
def logout(
    request: Request,
    _auth=Depends(require_admin_token),
) -> Dict[str, Any]:
    """User logout endpoint."""
    response = JSONResponse(content={"status": "logged_out"})
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response


@router.get("/auth/me")
@limiter.limit("30/minute")
def get_current_user(
    request: Request,
    _auth=Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get current user information."""
    token = _extract_admin_token(request, request.headers.get("X-Admin-Token")) or ""
    payload = _verify_session_token(token)
    if payload is not None:
        user = db.execute(select(User).where(User.id == payload["sub"])).scalars().first()
        if user:
            return {"username": user.username, "role": user.role}
    admin_user = db.execute(select(User).where(User.username == "admin")).scalars().first()
    if admin_user:
        return {"username": admin_user.username, "role": admin_user.role}
    raise HTTPException(
        status_code=404,
        detail={"error": "user_record_not_found", "message": "Token valid but user record missing — check DB migration."},
    )