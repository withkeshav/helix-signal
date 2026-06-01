"""Telegram bot routes for Helix Signal."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from backend.core.admin_auth import require_admin_token
from helix_telegram.models import TelegramUser, get_all_users, get_user_by_id, update_user
from helix_telegram.service import get_telegram_stats
from helix_telegram.digest import DigestService

router = APIRouter()

class TelegramUserResponse(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    is_subscribed: bool
    preferred_assets: Optional[str]
    alert_types: Optional[str]
    min_severity: Optional[str]
    timezone: Optional[str]
    receive_digest: bool
    digest_time: Optional[str]
    created_at: str
    updated_at: str

class TelegramStatsResponse(BaseModel):
    total_users: int
    subscribed_users: int
    unsubscribed_users: int
    error: Optional[str] = None

class TelegramUserUpdate(BaseModel):
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_subscribed: Optional[bool] = None
    preferred_assets: Optional[str] = None
    alert_types: Optional[str] = None
    min_severity: Optional[str] = None
    timezone: Optional[str] = None
    receive_digest: Optional[bool] = None
    digest_time: Optional[str] = None

class SendTestDigestRequest(BaseModel):
    user_id: int

@router.get("/telegram/stats", response_model=TelegramStatsResponse)
def get_telegram_stats_endpoint(
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Get Telegram bot statistics (admin only)."""
    return get_telegram_stats()

@router.get("/telegram/users", response_model=List[TelegramUserResponse])
def list_telegram_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """List all Telegram users (admin only)."""
    users = get_all_users(db, skip=skip, limit=limit)
    return [_user_to_response(user) for user in users]

@router.get("/telegram/users/{user_id}", response_model=TelegramUserResponse)
def get_telegram_user(
    user_id: int,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Get a specific Telegram user (admin only)."""
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_response(user)

@router.put("/telegram/users/{user_id}", response_model=TelegramUserResponse)
def update_telegram_user(
    user_id: int,
    user_data: TelegramUserUpdate,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Update a Telegram user (admin only)."""
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update user fields
    updated_user = update_user(
        db,
        user.telegram_id,
        username=user_data.username,
        first_name=user_data.first_name,
        last_name=user_data.last_name
    )
    
    # Update subscription status if provided
    if user_data.is_subscribed is not None:
        from helix_telegram.models import update_user_subscription
        update_user_subscription(db, user.telegram_id, user_data.is_subscribed)
    
    # Update other fields
    if user_data.preferred_assets is not None:
        user.preferred_assets = user_data.preferred_assets
    if user_data.alert_types is not None:
        user.alert_types = user_data.alert_types
    if user_data.min_severity is not None:
        user.min_severity = user_data.min_severity
    if user_data.timezone is not None:
        user.timezone = user_data.timezone
    if user_data.receive_digest is not None:
        user.receive_digest = user_data.receive_digest
    if user_data.digest_time is not None:
        user.digest_time = user_data.digest_time
    
    db.commit()
    db.refresh(user)
    
    return _user_to_response(user)

@router.delete("/telegram/users/{user_id}")
def delete_telegram_user(
    user_id: int,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Delete a Telegram user (admin only)."""
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    success = delete_user(db, user.telegram_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"ok": True}

@router.post("/telegram/test-digest")
async def send_test_digest(
    request: SendTestDigestRequest,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Send a test digest to a user (admin only)."""
    user = get_user_by_id(db, request.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get mock market data
    market_data = DigestService._get_mock_market_data()
    
    # Send test digest
    success = await DigestService.send_daily_digest(user, market_data)
    
    if success:
        return {"ok": True, "message": "Test digest sent successfully"}
    else:
        return {"ok": False, "message": "Failed to send test digest"}

def _user_to_response(user: TelegramUser) -> TelegramUserResponse:
    """Convert TelegramUser model to response model."""
    return TelegramUserResponse(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        is_subscribed=user.is_subscribed,
        preferred_assets=user.preferred_assets,
        alert_types=user.alert_types,
        min_severity=user.min_severity,
        timezone=user.timezone,
        receive_digest=user.receive_digest,
        digest_time=user.digest_time,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
    )