"""Authentication API endpoints."""

from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from core.limiter import limiter
from database import get_db
from services.user_service import authenticate_user

router = APIRouter()
security = HTTPBearer()


@router.post("/auth/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """User login endpoint."""
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = os.getenv("HELIX_ADMIN_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="Admin token not configured")
    return {"access_token": token, "token_type": "bearer", "username": user.username, "role": user.role}


@router.post("/auth/logout")
@limiter.limit("30/minute")
async def logout(
    request: Request,
    _auth=Depends(require_admin_token),
) -> Dict[str, Any]:
    """User logout endpoint."""
    return {"status": "logged_out"}


@router.get("/auth/me")
@limiter.limit("30/minute")
async def get_current_user(
    request: Request,
    _auth=Depends(require_admin_token),
) -> Dict[str, Any]:
    """Get current user information."""
    return {"username": "admin", "role": "administrator"}