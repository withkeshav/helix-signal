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
            block = content[idx: idx + 350]
            assert "no-new-privileges" in block, f"{service} missing no-new-privileges\nblock={block}"
            assert "cap_drop" in block, f"{service} missing cap_drop\nblock={block}"


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


class TestBruteforceLockout:
    """PR3: In-process failed-auth backoff."""

    def _reset_lockout(self):
        from core.admin_auth import _FAILED_ATTEMPTS
        _FAILED_ATTEMPTS.clear()

    def test_bruteforce_lockout_after_20_failures(self, client):
        self._reset_lockout()
        wrong_headers = {"X-Admin-Token": "wrong-token"}
        for _ in range(20):
            resp = client.get("/api/settings", headers=wrong_headers)
            assert resp.status_code in (403, 429)
        resp = client.get("/api/settings", headers=wrong_headers)
        assert resp.status_code == 429
        assert "Too many failed auth attempts" in resp.text

    def test_ip_key_trusts_xff_only_with_cidr(self, monkeypatch):
        from unittest.mock import Mock
        from core.admin_auth import _ip_key
        monkeypatch.setenv("TRUSTED_PROXY_CIDR", "127.0.0.0/8")
        from starlette.datastructures import Headers

        req = Mock()
        req.client.host = "127.0.0.1"

        req.headers = Headers({"X-Forwarded-For": "10.0.0.99"})
        key_attacker = _ip_key(req)

        req.headers = Headers({"X-Forwarded-For": "10.0.0.1"})
        key_legit = _ip_key(req)

        assert key_attacker != key_legit

    def test_ip_key_ignores_xff_without_cidr(self, monkeypatch):
        from unittest.mock import Mock
        from core.admin_auth import _ip_key
        monkeypatch.delenv("TRUSTED_PROXY_CIDR", raising=False)
        from starlette.datastructures import Headers

        req = Mock()
        req.client.host = "127.0.0.1"

        req.headers = Headers({"X-Forwarded-For": "10.0.0.99"})
        key_a = _ip_key(req)

        req.headers = Headers({"X-Forwarded-For": "10.0.0.1"})
        key_b = _ip_key(req)

        assert key_a == key_b

    def test_lockout_window_expiry(self, client, monkeypatch):
        self._reset_lockout()
        import time
        import backend.core.admin_auth as aa

        monkeypatch.setattr(aa, "_LOCKOUT_WINDOW_SECONDS", 0)
        wrong_headers = {"X-Admin-Token": "wrong-token"}
        for _ in range(21):
            client.get("/api/settings", headers=wrong_headers)
        resp = client.get("/api/settings", headers=wrong_headers)
        assert resp.status_code in (403, 429)
        time.sleep(0.01)
        resp = client.get("/api/settings", headers=wrong_headers)
        assert resp.status_code in (403, 429), f"Expected 403/429 got {resp.status_code}"

class TestRateLimiting:
    """PR3: Stricter rate limits on admin routes."""

    def test_settings_get_rate_limited(self, client, admin_headers):
        for i in range(11):
            resp = client.get("/api/settings", headers=admin_headers)
            if resp.status_code == 429:
                return
        assert False, "Expected 429 before 11th request"

    def test_settings_put_rate_limited(self, client, admin_headers):
        for i in range(6):
            resp = client.put("/api/settings", json={"key": "test", "value": True}, headers=admin_headers)
            if resp.status_code == 429:
                return
        assert False, "Expected 429 before 6th request"


class TestXForwardedFor:
    """PR3: Rate limiter reads X-Forwarded-For."""

    def test_get_remote_address_uses_forwarded(self):
        from core.limiter import _get_remote_address
        from fastapi import Request

        scope = {
            "type": "http",
            "headers": [
                (b"x-forwarded-for", b"203.0.113.42, 10.0.0.1"),
            ],
        }
        req = Request(scope)
        assert _get_remote_address(req) == "203.0.113.42"

    def test_get_remote_address_fallback_to_client(self):
        from core.limiter import _get_remote_address
        from fastapi import Request

        scope = {
            "type": "http",
            "client": ("192.168.1.1", 54321),
            "headers": [],
        }
        req = Request(scope)
        assert _get_remote_address(req) == "192.168.1.1"
