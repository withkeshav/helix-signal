"""Settings audit service for tracking changes to settings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from database import SettingsAuditLog, User


def log_settings_change(
    db: Session,
    setting_key: str,
    old_value: str,
    new_value: str,
    user: User | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SettingsAuditLog:
    """Log a settings change to the audit log."""
    audit_log = SettingsAuditLog(
        setting_key=setting_key,
        old_value=old_value,
        new_value=new_value,
        user_id=user.id if user else None,
        user_username=user.username if user else None,
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=datetime.now(timezone.utc),
    )
    
    db.add(audit_log)
    db.commit()
    db.refresh(audit_log)
    
    return audit_log


def get_settings_audit_logs(
    db: Session,
    setting_key: str | None = None,
    user_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[SettingsAuditLog]:
    """Get settings audit logs, optionally filtered by setting key or user."""
    query = db.query(SettingsAuditLog)
    
    if setting_key:
        query = query.filter(SettingsAuditLog.setting_key == setting_key)
    
    if user_id:
        query = query.filter(SettingsAuditLog.user_id == user_id)
    
    return query.order_by(SettingsAuditLog.created_at.desc()).offset(offset).limit(limit).all()


def get_settings_history(
    db: Session,
    setting_key: str,
    limit: int = 100,
) -> list[SettingsAuditLog]:
    """Get the history of changes for a specific setting."""
    return get_settings_audit_logs(db, setting_key=setting_key, limit=limit)


def get_user_settings_changes(
    db: Session,
    user_id: int,
    limit: int = 100,
) -> list[SettingsAuditLog]:
    """Get all settings changes made by a specific user."""
    return get_settings_audit_logs(db, user_id=user_id, limit=limit)


def get_recent_settings_changes(
    db: Session,
    limit: int = 50,
) -> list[SettingsAuditLog]:
    """Get the most recent settings changes."""
    return get_settings_audit_logs(db, limit=limit)