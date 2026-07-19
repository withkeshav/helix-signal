"""Settings import/export routes."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import User, get_db
from services.settings_import_export import (
    export_settings,
    import_settings,
    export_settings_to_json,
    import_settings_from_json,
)
from core.admin_auth import _verify_session_token, require_admin_token
from core.limiter import limiter

router = APIRouter()


class ImportResponse(BaseModel):
    imported: int
    skipped: int
    errors: list[str]


@router.get("/settings/export")
@limiter.limit("30/minute")
def export_settings_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Export all settings as JSON (admin only)."""
    try:
        export_data = export_settings(db)
        return export_data
    except Exception:
        logging.getLogger(__name__).error("Export failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Export failed. Check server logs.")


@router.post("/settings/import", response_model=ImportResponse)
@limiter.limit("5/minute")
def import_settings_endpoint(
    request: Request,
    settings_data: dict,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Import settings from JSON data (admin only)."""
    try:
        # Get user information for audit logging
        token = request.headers.get("X-Admin-Token", "")
        payload = _verify_session_token(token)
        user = db.execute(select(User).where(User.id == payload["sub"])).scalars().first() if payload else None
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        results = import_settings(db, settings_data, user, ip_address, user_agent)
        return results
    except Exception:
        logging.getLogger(__name__).error("Import failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Import failed. Check server logs.")


@router.get("/settings/export/json")
@limiter.limit("30/minute")
def export_settings_json_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Export all settings as downloadable JSON file (admin only)."""
    try:
        json_data = export_settings_to_json(db)
        return {
            "content": json_data,
            "filename": f"helix-settings-export-{int(datetime.now().timestamp())}.json"
        }
    except Exception:
        logging.getLogger(__name__).error("Export JSON failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Export failed. Check server logs.")


@router.post("/settings/import/json", response_model=ImportResponse)
@limiter.limit("5/minute")
async def import_settings_json_endpoint(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Import settings from uploaded JSON file (admin only)."""
    try:
        # Read the uploaded file (limit 1 MB)
        MAX_IMPORT_SIZE = 1 * 1024 * 1024
        content = await file.read(MAX_IMPORT_SIZE + 1)
        if len(content) > MAX_IMPORT_SIZE:
            raise HTTPException(status_code=413, detail="Import file too large (max 1 MB)")
        json_data = content.decode("utf-8")
        
        # Get user information for audit logging
        token = request.headers.get("X-Admin-Token", "")
        payload = _verify_session_token(token)
        user = db.execute(select(User).where(User.id == payload["sub"])).scalars().first() if payload else None
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        
        results = import_settings_from_json(db, json_data, user, ip_address, user_agent)
        return results
    except Exception:
        logging.getLogger(__name__).error("Import JSON failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Import failed. Check server logs.")