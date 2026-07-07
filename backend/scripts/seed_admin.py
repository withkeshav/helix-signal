"""Idempotent single-admin seed for OSS deployments.

Env: HELIX_ADMIN_USERNAME, HELIX_ADMIN_PASSWORD (both required to seed).
See transform.md §2.3 Layer B — migration b2c3d4e5f6a7 creates users table but no row.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal, User, init_db
from services.user_service import create_user, get_user_by_username
from sqlalchemy import select


def ensure_admin_user() -> bool:
    """Create the bootstrap admin if none exists. Returns True if a new user was created."""
    username = os.getenv("HELIX_ADMIN_USERNAME", "").strip()
    password = os.getenv("HELIX_ADMIN_PASSWORD", "").strip()
    if not username or not password:
        return False

    init_db()
    db = SessionLocal()
    try:
        if db.execute(select(User).where(User.role == "admin")).scalars().first():
            return False
        if get_user_by_username(db, username):
            return False
        create_user(
            db,
            username=username,
            email=f"{username}@helix.local",
            password=password,
            is_admin=True,
            role="admin",
        )
        return True
    finally:
        db.close()


if __name__ == "__main__":
    print("seeded" if ensure_admin_user() else "skipped")
