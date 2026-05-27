"""Tests for Phase 6 — Security, Stability & Observability."""

import os

import pytest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REFRESH_INTERVAL_SECONDS"] = "300"
os.environ["HELIX_SKIP_STARTUP_REFRESH"] = "1"

from fastapi import HTTPException
from starlette.testclient import TestClient


class TestSecurityMiddleware:
    def test_validate_asset_symbol_valid(self):
        from middleware.security import validate_asset_symbol
        assert validate_asset_symbol("usdt") == "USDT"
        assert validate_asset_symbol(" USDC ") == "USDC"
        assert validate_asset_symbol("DAI") == "DAI"

    def test_validate_asset_symbol_invalid(self):
        from middleware.security import validate_asset_symbol
        with pytest.raises(HTTPException):
            validate_asset_symbol("")
        with pytest.raises(HTTPException):
            validate_asset_symbol("A" * 20)
        with pytest.raises(HTTPException):
            validate_asset_symbol("test!@#")

    def test_validate_window_valid(self):
        from middleware.security import validate_window
        assert validate_window("24h") == "24h"
        assert validate_window("7d") == "7d"
        assert validate_window("30d") == "30d"
        assert validate_window("90d") == "90d"
        assert validate_window(" 7D ") == "7d"

    def test_validate_window_invalid(self):
        from middleware.security import validate_window
        with pytest.raises(HTTPException):
            validate_window("1d")
        with pytest.raises(HTTPException):
            validate_window("year")
        with pytest.raises(HTTPException):
            validate_window("")

    def test_sanitize_query_params(self):
        from middleware.security import sanitize_query_params
        params = {"asset": "USDT", "api_key": "secret123", "token": "abc", "window": "7d"}
        sanitized = sanitize_query_params(params)
        assert sanitized["asset"] == "USDT"
        assert sanitized["api_key"] == "[REDACTED]"
        assert sanitized["token"] == "[REDACTED]"
        assert sanitized["window"] == "7d"


class TestObservabilityMiddleware:
    def test_middleware_adds_metrics_to_response(self):
        import main
        with TestClient(main.app) as client:
            resp = client.get("/api/health")
            assert resp.status_code == 200

    def test_root_still_works_with_middleware(self):
        import main
        with TestClient(main.app) as client:
            resp = client.get("/")
            assert resp.status_code == 200
            assert "Hello" in resp.text

    def test_invalid_asset_rejected(self):
        import main
        with TestClient(main.app) as client:
            resp = client.get("/api/dashboard?asset=INVALID!@#")
            assert resp.status_code == 400


class TestContainerSecurity:
    def test_docker_compose_has_security_opt(self):
        import os
        compose_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docker-compose.yml"
        )
        with open(compose_path) as f:
            content = f.read()
        assert "no-new-privileges:true" in content
        assert "cap_drop:" in content
        assert "read_only: true" in content
        assert "tmpfs:" in content

    def test_all_services_have_hardening(self):
        import os
        compose_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docker-compose.yml"
        )
        with open(compose_path) as f:
            content = f.read()
        for service in ("backend:", "frontend:"):
            idx = content.index(service)
            block = content[idx: idx + 200]
            assert "no-new-privileges" in block, f"{service} missing no-new-privileges"
            assert "cap_drop" in block, f"{service} missing cap_drop"


class TestSettingsAuth:
    """PR1: GET /api/settings requires admin token."""

    def test_get_settings_403_without_token(self, client):
        resp = client.get("/api/settings")
        assert resp.status_code == 403

    def test_get_settings_200_with_token(self, client, admin_headers):
        resp = client.get("/api/settings", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_settings_strips_key_env(self, client, admin_headers):
        resp = client.get("/api/settings", headers=admin_headers)
        assert resp.status_code == 200
        for item in resp.json():
            assert "key_env" not in item, f"{item.get('key')} still has key_env"

    def test_put_settings_403_without_token(self, client):
        resp = client.put("/api/settings", json={"key": "test", "value": True})
        assert resp.status_code == 403
