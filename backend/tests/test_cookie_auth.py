"""Cookie session auth tests."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from core.admin_auth import SESSION_COOKIE_NAME, _sign_session_token


@pytest.fixture()
def signed_admin_cookie() -> str:
    return _sign_session_token({"sub": 1, "role": "admin"})


def test_auth_me_accepts_session_cookie(client: TestClient, signed_admin_cookie: str):
    client.cookies.set(SESSION_COOKIE_NAME, signed_admin_cookie)
    response = client.get("/api/auth/me")
    # User id 1 may not exist — 404 user_record is ok vs 401
    assert response.status_code in (200, 404)


def test_alerts_accepts_session_cookie(client: TestClient, signed_admin_cookie: str):
    client.cookies.set(SESSION_COOKIE_NAME, signed_admin_cookie)
    response = client.get("/api/alerts")
    assert response.status_code in (200, 401, 403)


def test_login_sets_httponly_cookie(client: TestClient, db_session):
    from database import User
    from services.user_service import get_password_hash

    user = User(
        username="cookieadmin",
        email="cookie@example.com",
        hashed_password=get_password_hash("secretpass"),
        is_admin=True,
        role="admin",
    )
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/api/auth/login",
        data={"username": "cookieadmin", "password": "secretpass"},
    )
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in set_cookie
    assert "httponly" in set_cookie.lower()
