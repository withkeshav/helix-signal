"""Telegram bot routes for Helix Signal."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

# Add review queue imports
from helix_telegram.review import review_queue, ReviewItem

from database import get_db
from core.admin_auth import require_admin_token
from core.limiter import limiter
from helix_telegram.models import TelegramUser, get_all_users, get_user_by_id, update_user, delete_user
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

class ReviewItemResponse(BaseModel):
    id: str
    alert_data: dict
    created_at: float
    score: float
    reviewed: bool
    approved: Optional[bool]
    reviewed_at: Optional[float]

class ReviewStatsResponse(BaseModel):
    total: int
    pending: int
    approved: int
    rejected: int

class ReviewActionRequest(BaseModel):
    action: str  # "approve" or "reject"

@router.get("/telegram/stats", response_model=TelegramStatsResponse)
@limiter.limit("30/minute")
def get_telegram_stats_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Get Telegram bot statistics (admin only)."""
    return get_telegram_stats()

@router.get("/telegram/users", response_model=List[TelegramUserResponse])
@limiter.limit("30/minute")
def list_telegram_users(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """List all Telegram users (admin only)."""
    users = get_all_users(db, skip=skip, limit=limit)
    return [_user_to_response(user) for user in users]

@router.get("/telegram/users/{user_id}", response_model=TelegramUserResponse)
@limiter.limit("30/minute")
def get_telegram_user(
    request: Request,
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
@limiter.limit("30/minute")
def update_telegram_user(
    request: Request,
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
@limiter.limit("30/minute")
def delete_telegram_user(
    request: Request,
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
@limiter.limit("30/minute")
async def send_test_digest(
    request: Request,
    body: SendTestDigestRequest,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Send a test digest to a user (admin only)."""
    user = get_user_by_id(db, body.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Fetch real market data
    market_data = DigestService._fetch_real_market_data(db)
    
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

# ===================================================================
# Review Queue Endpoints
# ===================================================================

@router.get("/telegram/review/pending", response_model=List[ReviewItemResponse])
@limiter.limit("30/minute")
def get_pending_reviews(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Get all pending review items (admin only)."""
    pending_items = review_queue.get_pending()
    return [
        ReviewItemResponse(
            id=item.id,
            alert_data=item.alert_data,
            created_at=item.created_at,
            score=item.score,
            reviewed=item.reviewed,
            approved=item.approved,
            reviewed_at=item.reviewed_at
        )
        for item in pending_items
    ]

@router.post("/telegram/review/{review_id}/action")
@limiter.limit("30/minute")
def review_action(
    request: Request,
    review_id: str,
    body: ReviewActionRequest,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Approve or reject a review item (admin only)."""
    if body.action == "approve":
        success = review_queue.approve(review_id)
        if success:
            return {"ok": True, "message": "Review approved"}
        else:
            raise HTTPException(status_code=404, detail="Review not found or already processed")
    elif body.action == "reject":
        success = review_queue.reject(review_id)
        if success:
            return {"ok": True, "message": "Review rejected"}
        else:
            raise HTTPException(status_code=404, detail="Review not found or already processed")
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'")

@router.get("/telegram/review/stats", response_model=ReviewStatsResponse)
@limiter.limit("30/minute")
def get_review_stats(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
):
    """Get review queue statistics (admin only)."""
    stats = review_queue.get_stats()
    return ReviewStatsResponse(**stats)