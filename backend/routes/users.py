"""User management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from providers.settings import get_setting
from services.user_service import (
    authenticate_user,
    create_user,
    delete_user,
    get_user,
    get_user_by_username,
    get_users,
    update_user,
)
from backend.core.admin_auth import require_admin_token


def require_multi_user_enabled(db: Session = Depends(get_db)):
    """Dependency: reject if multi-user support is not enabled in settings."""
    if not get_setting("feature_multi_user", db):
        raise HTTPException(
            status_code=404,
            detail="Multi-user support is not enabled. Enable 'Multi-User Support' in Settings.",
        )
    return True

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    is_admin: bool = False
    role: str = "user"


class UserUpdate(BaseModel):
    username: str | None = None
    email: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None
    role: str | None = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool
    role: str
    created_at: str
    updated_at: str


@router.post("/users", response_model=UserResponse)
def create_new_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
    _multi=Depends(require_multi_user_enabled),
):
    """Create a new user (admin only)."""
    # Check if user already exists
    if get_user_by_username(db, user.username):
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # Create user
    db_user = create_user(
        db=db,
        username=user.username,
        email=user.email,
        password=user.password,
        is_admin=user.is_admin,
        role=user.role,
    )
    
    return UserResponse(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        is_active=db_user.is_active,
        is_admin=db_user.is_admin,
        role=db_user.role,
        created_at=db_user.created_at.isoformat(),
        updated_at=db_user.updated_at.isoformat(),
    )


@router.get("/users", response_model=list[UserResponse])
def read_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
    _multi=Depends(require_multi_user_enabled),
):
    """Get all users (admin only)."""
    users = get_users(db, skip=skip, limit=limit)
    return [
        UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at.isoformat(),
            updated_at=user.updated_at.isoformat(),
        )
        for user in users
    ]


@router.get("/users/{user_id}", response_model=UserResponse)
def read_user(
    user_id: int,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
    _multi=Depends(require_multi_user_enabled),
):
    """Get a specific user (admin only)."""
    db_user = get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        is_active=db_user.is_active,
        is_admin=db_user.is_admin,
        role=db_user.role,
        created_at=db_user.created_at.isoformat(),
        updated_at=db_user.updated_at.isoformat(),
    )


@router.put("/users/{user_id}", response_model=UserResponse)
def update_existing_user(
    user_id: int,
    user: UserUpdate,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
    _multi=Depends(require_multi_user_enabled),
):
    """Update a user (admin only)."""
    db_user = update_user(
        db=db,
        user_id=user_id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
        role=user.role,
    )
    
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        is_active=db_user.is_active,
        is_admin=db_user.is_admin,
        role=db_user.role,
        created_at=db_user.created_at.isoformat(),
        updated_at=db_user.updated_at.isoformat(),
    )


@router.delete("/users/{user_id}")
def delete_existing_user(
    user_id: int,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
    _multi=Depends(require_multi_user_enabled),
):
    """Delete a user (admin only)."""
    if not delete_user(db, user_id=user_id):
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"ok": True}


@router.post("/auth/login")
def login(
    request: Request,
    credentials: UserLogin,
    db: Session = Depends(get_db),
    _multi=Depends(require_multi_user_enabled),
):
    """Authenticate a user and return a token."""
    user = authenticate_user(db, credentials.username, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive")
    
    # In a real application, you would generate a JWT token here
    # For now, we'll just return a success message
    return {
        "access_token": "mock_token",  # In a real app, this would be a JWT
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
    }