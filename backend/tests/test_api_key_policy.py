"""Scoped API key policy tests (Phase 5)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.api_auth import (
    AuthContext,
    clamp_history_hours,
    filter_assets,
    generate_api_key,
    hash_api_key,
    require_bundle,
)
from database import ApiKey
from providers.settings import set_setting


@pytest.fixture
def key_required(db_session):
    set_setting("api_auth_mode", "key_required", db_session)


def _insert_key(db_session, *, scopes, access_policy=None):
    raw, prefix, digest = generate_api_key()
    row = ApiKey(
        name="policy-test",
        key_prefix=prefix,
        key_hash=digest,
        scopes=scopes,
        access_policy=access_policy,
        enabled=True,
        rate_limit_rpm=120,
    )
    db_session.add(row)
    db_session.commit()
    return raw


def test_trends_only_key_cannot_hit_forensics(client: TestClient, db_session, key_required):
    raw = _insert_key(db_session, scopes=["trends:read"])
    headers = {"X-API-Key": raw}
    assert client.get("/api/trends?asset=USDT&window=24h", headers=headers).status_code in (200, 404)
    r = client.get("/api/v1/blacklist/events", headers=headers)
    assert r.status_code == 403
    assert "forensics:read" in r.json()["detail"] or "scope" in r.json()["detail"].lower()


def test_history_clamp_on_trends(client: TestClient, db_session, key_required):
    raw = _insert_key(
        db_session,
        scopes=["trends:read"],
        access_policy={"allowed_bundles": ["trends:read"], "max_history_hours": 24},
    )
    headers = {"X-API-Key": raw}
    assert client.get("/api/trends?asset=USDT&window=24h", headers=headers).status_code in (200, 404)
    r = client.get("/api/trends?asset=USDT&window=7d", headers=headers)
    assert r.status_code == 403
    assert "history limit" in r.json()["detail"].lower()


def test_asset_filter_on_trends(client: TestClient, db_session, key_required):
    raw = _insert_key(
        db_session,
        scopes=["trends:read"],
        access_policy={"allowed_bundles": ["trends:read"], "allowed_assets": ["USDT"]},
    )
    headers = {"X-API-Key": raw}
    assert client.get("/api/trends?asset=USDT&window=24h", headers=headers).status_code in (200, 404)
    r = client.get("/api/trends?asset=USDC&window=24h", headers=headers)
    assert r.status_code == 403
    assert "USDC" in r.json()["detail"]


def test_admin_session_unrestricted(client: TestClient, db_session, key_required, admin_headers):
    assert client.get("/api/v1/blacklist/events", headers=admin_headers).status_code == 200
    assert client.get("/api/trends?asset=USDC&window=7d", headers=admin_headers).status_code in (200, 404)


def test_intelligence_read_back_compat(client: TestClient, db_session, key_required):
    raw = _insert_key(db_session, scopes=["intelligence:read"])
    headers = {"X-API-Key": raw}
    assert client.get("/api/v1/blacklist/events", headers=headers).status_code == 200
    assert client.get("/api/events", headers=headers).status_code == 200


def test_create_key_default_core_read(client: TestClient, admin_headers):
    r = client.post(
        "/api/v1/api-keys",
        json={"name": "default-scope", "rate_limit_rpm": 30},
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["scopes"] == ["core:read"]
    assert body["access_policy"]["allowed_bundles"] == ["core:read"]


def test_create_key_with_access_policy(client: TestClient, admin_headers):
    r = client.post(
        "/api/v1/api-keys",
        json={
            "name": "scoped",
            "scopes": ["trends:read"],
            "access_policy": {
                "allowed_bundles": ["trends:read"],
                "allowed_assets": ["USDT"],
                "max_history_hours": 48,
            },
        },
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["access_policy"]["allowed_assets"] == ["USDT"]
    assert body["access_policy"]["max_history_hours"] == 48


def test_clamp_history_hours_helper():
    ctx = AuthContext(
        kind="api_key",
        scopes={"trends:read"},
        access_policy={"max_history_hours": 24},
    )
    assert clamp_history_hours(ctx, 168) == 24
    assert clamp_history_hours(AuthContext(kind="admin_session"), 168) == 168


def test_filter_assets_helper():
    ctx = AuthContext(
        kind="api_key",
        scopes={"trends:read"},
        access_policy={"allowed_assets": ["USDT", "USDC"]},
    )
    assert filter_assets(ctx, ["USDT", "DAI"]) == ["USDT"]
    assert filter_assets(AuthContext(kind="admin_session"), ["USDT", "DAI"]) == ["USDT", "DAI"]


def test_require_bundle_helper():
    ctx = AuthContext(kind="api_key", scopes={"trends:read"})
    require_bundle(ctx, "trends:read")
    with pytest.raises(Exception) as exc:
        require_bundle(ctx, "forensics:read")
    assert exc.value.status_code == 403
