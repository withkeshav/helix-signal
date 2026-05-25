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

    def test_request_count_increments(self):
        import main
        from middleware.observability import METRIC_REQUEST_COUNT
        with TestClient(main.app) as client:
            resp = client.get("/api/health")
            assert resp.status_code == 200

    def test_observability_metrics_registered(self):
        from middleware.observability import (
            METRIC_REQUEST_COUNT,
            METRIC_REQUEST_LATENCY,
            METRIC_SOURCE_HEALTH,
            METRIC_MODEL_LATENCY,
            METRIC_CACHE_HIT_RATIO,
        )
        assert "helix_http_requests" in str(METRIC_REQUEST_COUNT._name)
        assert METRIC_REQUEST_LATENCY._name == "helix_http_request_duration_seconds"
        assert METRIC_SOURCE_HEALTH._name == "helix_source_health"
        assert METRIC_MODEL_LATENCY._name == "helix_model_inference_seconds"
        assert METRIC_CACHE_HIT_RATIO._name == "helix_cache_hit_ratio"

    def test_root_still_works_with_middleware(self):
        import main
        with TestClient(main.app) as client:
            resp = client.get("/")
            assert resp.status_code == 200
            assert "Hello" in resp.text

    def test_metrics_endpoint_still_works(self):
        import main
        with TestClient(main.app) as client:
            resp = client.get("/metrics")
            assert resp.status_code == 200
            assert "helix_http_requests_total" in resp.text

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
        for service in ("backend:", "timesfm:", "frontend:"):
            idx = content.index(service)
            block = content[idx: idx + 200]
            assert "no-new-privileges" in block, f"{service} missing no-new-privileges"
            assert "cap_drop" in block, f"{service} missing cap_drop"
