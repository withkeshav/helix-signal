"""Settings import/export routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json

from database import get_db
from services.settings_import_export import (
    export_settings,
    import_settings,
    export_settings_to_json,
    import_settings_from_json,
)
from core.admin_auth import require_admin_token
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.post("/settings/import", response_model=ImportResponse)
@limiter.limit("5/minute")
async def import_settings_endpoint(
    request: Request,
    settings_data: dict,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Import settings from JSON data (admin only)."""
    try:
        # Get user information for audit logging
        user = None  # In a real implementation, you would get the current user
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        
        results = import_settings(db, settings_data, user, ip_address, user_agent)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


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
        # Read the uploaded file
        content = await file.read()
        json_data = content.decode("utf-8")
        
        # Get user information for audit logging
        user = None  # In a real implementation, you would get the current user
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        
        results = import_settings_from_json(db, json_data, user, ip_address, user_agent)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")