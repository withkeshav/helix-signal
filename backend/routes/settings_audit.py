"""Settings audit log routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List

from database import get_db
from services.settings_audit import (
    get_settings_audit_logs,
    get_settings_history,
    get_user_settings_changes,
    get_recent_settings_changes,
)
from core.admin_auth import require_admin_token
from core.limiter import limiter

router = APIRouter()


class SettingsAuditLogResponse(BaseModel):
    id: int
    setting_key: str
    old_value: Optional[str]
    new_value: Optional[str]
    user_id: Optional[int]
    user_username: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: str


@router.get("/settings/audit", response_model=List[SettingsAuditLogResponse])
@limiter.limit("30/minute")
def get_audit_logs(
    request: Request,
    setting_key: Optional[str] = None,
    user_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Get settings audit logs (admin only)."""
    logs = get_settings_audit_logs(
        db=db,
        setting_key=setting_key,
        user_id=user_id,
        limit=min(limit, 1000),  # Cap at 1000 for performance
        offset=offset,
    )
    
    return [
        SettingsAuditLogResponse(
            id=log.id,
            setting_key=log.setting_key,
            old_value=log.old_value,
            new_value=log.new_value,
            user_id=log.user_id,
            user_username=log.user_username,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.get("/settings/audit/history/{setting_key}", response_model=List[SettingsAuditLogResponse])
@limiter.limit("30/minute")
def get_setting_history(
    request: Request,
    setting_key: str,
    limit: int = 100,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Get history of changes for a specific setting (admin only)."""
    logs = get_settings_history(
        db=db,
        setting_key=setting_key,
        limit=min(limit, 1000),  # Cap at 1000 for performance
    )
    
    return [
        SettingsAuditLogResponse(
            id=log.id,
            setting_key=log.setting_key,
            old_value=log.old_value,
            new_value=log.new_value,
            user_id=log.user_id,
            user_username=log.user_username,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.get("/settings/audit/user/{user_id}", response_model=List[SettingsAuditLogResponse])
@limiter.limit("30/minute")
def get_user_changes(
    request: Request,
    user_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Get all settings changes made by a specific user (admin only)."""
    logs = get_user_settings_changes(
        db=db,
        user_id=user_id,
        limit=min(limit, 1000),  # Cap at 1000 for performance
    )
    
    return [
        SettingsAuditLogResponse(
            id=log.id,
            setting_key=log.setting_key,
            old_value=log.old_value,
            new_value=log.new_value,
            user_id=log.user_id,
            user_username=log.user_username,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.get("/settings/audit/recent", response_model=List[SettingsAuditLogResponse])
@limiter.limit("30/minute")
def get_recent_changes(
    request: Request,
    limit: int = 50,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Get the most recent settings changes (admin only)."""
    logs = get_recent_settings_changes(
        db=db,
        limit=min(limit, 1000),  # Cap at 1000 for performance
    )
    
    return [
        SettingsAuditLogResponse(
            id=log.id,
            setting_key=log.setting_key,
            old_value=log.old_value,
            new_value=log.new_value,
            user_id=log.user_id,
            user_username=log.user_username,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]