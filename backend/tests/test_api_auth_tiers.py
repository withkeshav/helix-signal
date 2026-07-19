"""Table-driven auth tier tests for intelligence API (Phase 3)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.api_auth import generate_api_key, hash_api_key
from database import ApiKey, SessionLocal
from providers.settings import set_setting


@pytest.fixture
def api_key_row(db_session):
    raw, prefix, digest = generate_api_key()
    row = ApiKey(
        name="test-key",
        key_prefix=prefix,
        key_hash=digest,
        scopes=["intelligence:read", "investigate:write"],
        enabled=True,
        rate_limit_rpm=120,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return raw, row


@pytest.mark.parametrize(
    "path,mode,headers,expected",
    [
        ("/api/health", "open", {}, 200),
        ("/api/version", "open", {}, 200),
        ("/api/health", "key_required", {}, 200),
        ("/api/dashboard", "open", {}, 200),
        ("/api/dashboard", "key_required", {}, 401),
        ("/api/alerts", "open", {}, 401),
        ("/api/alerts", "key_required", {}, 401),
        ("/api/v1/investigate", "open", {}, 401),  # POST without body may 401/422 before — auth first
    ],
)
def test_auth_tiers_matrix(client: TestClient, db_session, path, mode, headers, expected, monkeypatch):
    set_setting("api_auth_mode", mode, db_session)
    if path == "/api/v1/investigate":
        r = client.post(path, json={"address": "0x" + "11" * 20, "chain": "ethereum"}, headers=headers)
    else:
        r = client.get(path, headers=headers)
    assert r.status_code == expected, (path, mode, r.status_code, r.text[:200])


def test_dashboard_key_required_with_bearer(client: TestClient, db_session, api_key_row):
    raw, _ = api_key_row
    set_setting("api_auth_mode", "key_required", db_session)
    r = client.get("/api/dashboard", headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 200


def test_dashboard_key_required_with_x_api_key(client: TestClient, db_session, api_key_row):
    raw, _ = api_key_row
    set_setting("api_auth_mode", "key_required", db_session)
    r = client.get("/api/dashboard", headers={"X-API-Key": raw})
    assert r.status_code == 200


def test_alerts_never_anonymous_even_in_open(client: TestClient, db_session, api_key_row):
    raw, _ = api_key_row
    set_setting("api_auth_mode", "open", db_session)
    assert client.get("/api/alerts").status_code == 401
    assert client.get("/api/alerts", headers={"X-API-Key": raw}).status_code == 200


def test_create_api_key_admin_only(client: TestClient, admin_headers):
    r = client.post(
        "/api/v1/api-keys",
        json={"name": "ci", "scopes": ["intelligence:read"], "rate_limit_rpm": 30},
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["api_key"].startswith("hx_")
    assert body["key_prefix"]
    assert "key_hash" not in body


def test_hash_api_key_sha256():
    assert len(hash_api_key("hx_test")) == 64
