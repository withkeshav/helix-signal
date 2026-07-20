"""User service — single seeded admin for operator login and SQLAdmin."""

from __future__ import annotations

from typing import Optional

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import User


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def get_user(db: Session, user_id: int) -> Optional[User]:
    """Get a user by ID."""
    return db.execute(select(User).where(User.id == user_id)).scalars().first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Get a user by username."""
    return db.execute(select(User).where(User.username == username)).scalars().first()


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Authenticate a user by username and password."""
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_user(
    db: Session,
    username: str,
    email: str,
    password: str,
    is_admin: bool = False,
    role: str = "user",
) -> User:
    """Create the seeded admin user (seed_admin.py only)."""
    hashed_password = get_password_hash(password)
    db_user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        is_admin=is_admin,
        role=role,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user
