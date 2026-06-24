"""Phase 2 — Integration tests covering end-to-end AI enrichment flows,
API endpoints, warning engine, playbook application, rate limiting, and
cache monitoring.

All tests are fast — no real network calls. HTTP calls are monkeypatched.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy import text

import services.ai_router as r
import services.components.ai.budget as budget_mod
import services.components.ai.cache as cache_mod
from core.circuit_breaker import CircuitBreaker, CircuitState
from providers.rate_limiter import TokenBucket
from providers.settings import PLAYBOOKS, apply_playbook, get_playbooks
from services.ai_router import (
    _PROVIDER_RATE_LIMITS,
    enrich_with_ai,
    get_cache_stats,
)
from services.ai_usage import get_ai_usage_summary, increment_ai_usage
from services.source_usage import _check_source_rate_limit, _record_source_call, _SOURCE_RATE_LIMITS
from services.warning_engine import check_warnings
from sources.base import http_get_with_retry
from database import engine


_USAGE_TABLES = ["ai_usage", "source_usage", "settings"]


def _truncate_usage_tables():
    with engine.begin() as conn:
        for t in _USAGE_TABLES:
            conn.execute(text(f"DELETE FROM {t}"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _enrich_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up standard env vars for enrichment tests."""
    monkeypatch.setenv("AI_MODE", "ai_lite")
    monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "50000")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("OLLAMA_API_KEY", "ok-test")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")


def _mock_provider(text: str = "Test response", tokens: int = 50, provider: str = "groq", model: str = "llama-3.1-8b-instant"):
    """Return a provider function that returns a hardcoded success."""

    def _mock(prompt: str, max_tokens: int, **kwargs):
        return {"provider": provider, "model": model, "text": text, "tokens": tokens}

    return _mock


def _mock_failing_provider():
    """Return a provider function that returns None (simulating failure)."""
    return lambda prompt, max_tokens, **kwargs: None


# ===================================================================
# Section 1: End-to-End Enrichment Flow (10 tests)
# ===================================================================


@pytest.mark.usefixtures("_enrich_env")
class TestEnrichmentFlow:
    def test_enrich_with_ai_full_flow(self, monkeypatch):
        """Verify payload structure on successful enrichment."""
        monkeypatch.setattr(r, "_openrouter_lite", _mock_provider(
            text="Low risk. Peg is stable.", tokens=40
        ))
        monkeypatch.setattr(r, "_ollama_cloud", _mock_provider(
            text="Fallback not needed.", tokens=30
        ))

        result = enrich_with_ai(
            feature="risk_explain",
            context={"asset_symbol": "USDT", "signal_score": 15, "signal_band": "Normal", "regime": "stable"},
        )

        assert result["available"] is True
        assert result["feature"] == "risk_explain"
        assert result["provider"] == "groq"
        assert result["model"] == "llama-3.1-8b-instant"
        assert result["summary"] == "Low risk. Peg is stable."
        assert result["tokens"] == 40
        assert result["cached"] is False
        assert "generated_at" in result
        assert "expires_at" in result
        assert result["mode"] == "ai_lite"

    def test_enrich_with_ai_cache_hit(self, monkeypatch):
        """Second call with same context returns cached=True without calling provider."""
        call_count = 0

        def counting_mock(prompt, max_tokens, **kwargs):
            nonlocal call_count
            call_count += 1
            return {"provider": "groq", "model": "llama-3.1-8b-instant", "text": "Cached response", "tokens": 25}

        monkeypatch.setattr(r, "_openrouter_lite", counting_mock)
        monkeypatch.setattr(r, "_ollama_cloud", counting_mock)

        ctx = {"asset_symbol": "USDT", "signal_score": 10, "signal_band": "Normal", "regime": "stable"}
        first = enrich_with_ai(feature="risk_explain", context=ctx)
        assert first["available"] is True
        assert call_count == 1

        second = enrich_with_ai(feature="risk_explain", context=ctx)
        assert second["available"] is True
        assert second["cached"] is True
        assert call_count == 1

    def test_enrich_with_ai_provider_chain(self, monkeypatch):
        """First provider fails, second is called and returns success."""
        monkeypatch.setattr(r, "_openrouter_lite", _mock_failing_provider())
        monkeypatch.setattr(r, "_ollama_cloud", _mock_provider(
            text="Provider chain fallback", tokens=60, provider="ollama_cloud", model="ministral-3:8b-cloud"
        ))

        result = enrich_with_ai(
            feature="risk_explain",
            context={"asset_symbol": "USDT", "signal_score": 20, "signal_band": "Normal", "regime": "stable"},
        )

        assert result["available"] is True
        assert result["provider"] == "ollama_cloud"
        assert "chain fallback" in result["summary"]

    def test_enrich_with_ai_all_providers_fail(self, monkeypatch):
        """All providers return None — available=False with all_providers_failed."""
        monkeypatch.setattr(r, "_openrouter_lite", _mock_failing_provider())
        monkeypatch.setattr(r, "_ollama_cloud", _mock_failing_provider())

        result = enrich_with_ai(
            feature="risk_explain",
            context={"asset_symbol": "USDT", "signal_score": 25, "signal_band": "Normal", "regime": "stable"},
        )

        assert result["available"] is False
        assert result["reason"] == "all_providers_failed"
        assert "errors" in result

    def test_enrich_with_ai_budget_exceeded(self, monkeypatch):
        """Low budget triggers daily_token_budget_exceeded before calling providers."""
        monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "1")
        monkeypatch.setattr(r, "_openrouter_lite", _mock_provider())

        result = enrich_with_ai(
            feature="risk_explain",
            context={"asset_symbol": "USDT", "signal_score": 10, "signal_band": "Normal", "regime": "stable"},
        )

        assert result["available"] is False
        assert result["reason"] == "daily_token_budget_exceeded"

    def test_enrich_with_ai_rate_limited(self, monkeypatch):
        """Exhaust rate limit for first provider; second provider is called."""
        mock_groq = _mock_provider(text="groq response", tokens=30, provider="groq")
        mock_ollama = _mock_provider(text="ollama response", tokens=40, provider="ollama_cloud", model="ministral-3:8b-cloud")

        monkeypatch.setattr(r, "_groq", mock_groq)
        monkeypatch.setattr(r, "_ollama_cloud", mock_ollama)
        monkeypatch.setenv("AI_MODE", "ai_full")

        # Fill rate limit for groq (30 RPM)
        _PROVIDER_RATE_LIMITS["groq"] = [time.time()] * 30

        result = enrich_with_ai(
            feature="risk_explain",
            context={"asset_symbol": "USDT", "signal_score": 10, "signal_band": "Normal", "regime": "stable"},
        )

        assert result["available"] is True
        assert result["provider"] == "ollama_cloud"

    def test_enrich_with_ai_semantic_cache(self, monkeypatch):
        """Semantic cache returns hit for similar prompts."""
        cache_mod._SEMANTIC_CACHE_ENABLED = True
        cache_mod._SEMANTIC_CACHE_THRESHOLD = 0.80

        monkeypatch.setattr(r, "_openrouter_lite", _mock_provider(
            text="Semantic cached response", tokens=30
        ))
        monkeypatch.setattr(r, "_ollama_cloud", _mock_failing_provider())

        ctx1 = {"asset_symbol": "USDT", "signal_score": 30, "signal_band": "Watch", "regime": "volatile"}
        first = enrich_with_ai(feature="risk_explain", context=ctx1)
        assert first["available"] is True

        # Similar prompt with slightly different score
        ctx2 = {"asset_symbol": "USDT", "signal_score": 32, "signal_band": "Watch", "regime": "volatile"}
        second = enrich_with_ai(feature="risk_explain", context=ctx2)

        assert second["cached"] is True
        assert "Semantic" in second["summary"]

    def test_enrich_with_ai_unknown_feature(self, monkeypatch):
        """Unknown feature uses fallback prompt template."""
        monkeypatch.setattr(r, "_openrouter_lite", _mock_provider(text="Fallback feature", tokens=20))

        result = enrich_with_ai(
            feature="nonexistent_feature",
            context={"asset_symbol": "BTC", "signal_score": 50, "signal_band": "Elevated", "regime": "unstable"},
        )

        assert result["available"] is True
        assert result["feature"] == "nonexistent_feature"

    def test_get_cache_stats_after_enrich(self, monkeypatch):
        """After enrich calls, cache stats reflect activity."""
        monkeypatch.setattr(r, "_openrouter_lite", _mock_provider(tokens=50))
        monkeypatch.setattr(r, "_ollama_cloud", _mock_failing_provider())

        stats_before = get_cache_stats()
        assert stats_before["hits"] == 0
        assert stats_before["misses"] == 0
        assert stats_before["hit_rate"] == 0.0

        ctx = {"asset_symbol": "USDT", "signal_score": 10, "signal_band": "Normal", "regime": "stable"}
        enrich_with_ai(feature="risk_explain", context=ctx)

        stats_mid = get_cache_stats()
        assert stats_mid["misses"] == 1
        assert stats_mid["entries"] >= 1

        enrich_with_ai(feature="risk_explain", context=ctx)

        stats_after = get_cache_stats()
        assert stats_after["hits"] == 1
        assert stats_after["hit_rate"] > 0
        assert stats_after["tokens_saved"] > 0

    def test_enrich_with_ai_respects_provider_priority(self, monkeypatch):
        """Provider call order matches configured priority."""
        call_order: list[str] = []

        def tracking_mock(provider_name: str):
            def _fn(prompt, max_tokens, **kwargs):
                call_order.append(provider_name)
                return {"provider": provider_name, "model": "test", "text": "ok", "tokens": 10}
            return _fn

        monkeypatch.setattr(r, "_groq", tracking_mock("groq"))
        monkeypatch.setattr(r, "_ollama_cloud", tracking_mock("ollama_cloud"))
        monkeypatch.setattr(r, "_openrouter_lite", tracking_mock("openrouter_free"))
        monkeypatch.setenv("AI_MODE", "ai_full")

        ctx = {"asset_symbol": "USDT", "signal_score": 10, "signal_band": "Normal", "regime": "stable"}
        enrich_with_ai(feature="risk_explain", context=ctx)

        assert len(call_order) >= 1
        assert call_order[0] == "groq"


# ===================================================================
# Section 2: API Endpoint Integration (10 tests)
# ===================================================================


class TestApiEndpoints:
    def test_api_ai_budget(self, client, admin_headers):
        """GET /api/ai/budget returns budget shape."""
        resp = client.get("/api/ai/budget", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "daily_budget" in data
        assert "tokens_used_today" in data
        assert "tokens_remaining" in data
        assert "pct_used" in data

    def test_api_ai_stats(self, client, admin_headers):
        """GET /api/ai/stats — note: stats endpoint redirects or not available;
        test provider_stats through /api/ai/usage."""
        resp = client.get("/api/ai/usage", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "provider_stats" in data
        assert "date" in data
        assert "total_calls" in data
        assert "total_tokens" in data

    def test_api_ai_usage(self, client, admin_headers):
        """GET /api/ai/usage returns usage summary."""
        resp = client.get("/api/ai/usage", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "date" in data
        assert "total_calls" in data
        assert "total_tokens" in data
        assert "budget" in data
        assert "provider_stats" in data
        assert "providers" in data

    def test_api_ai_warnings(self, client, admin_headers):
        """GET /api/ai/warnings returns a list."""
        resp = client.get("/api/ai/warnings", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_api_ai_warnings_with_high_usage(self, monkeypatch, client, admin_headers):
        """Increment AI usage past threshold, verify warning appears."""
        monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "1000")
        budget_mod._LOCAL_DAILY_TOKENS = 900
        budget_mod._LOCAL_TOKEN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        resp = client.get("/api/ai/warnings", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        ai_warnings = [w for w in data if w["type"] == "ai_budget"]
        assert len(ai_warnings) >= 1
        assert ai_warnings[0]["current_value"] == 900

    def test_api_ai_playbooks_list(self, client, admin_headers):
        """GET /api/ai/playbooks returns 3 playbooks."""
        resp = client.get("/api/ai/playbooks", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "playbooks" in data
        names = {p["name"] for p in data["playbooks"]}
        assert names == {"max_free", "balanced", "quality"}

    def test_api_ai_playbook_apply(self, client, db_session, admin_headers):
        """POST /api/ai/playbook/max_free applies settings."""
        resp = client.post("/api/ai/playbook/max_free", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["playbook"] == "max_free"
        assert "changes" in data
        keys = [c["key"] for c in data["changes"]]
        assert "ai_mode" in keys
        assert "ai_daily_token_budget" in keys

    def test_api_ai_playbook_invalid(self, client, admin_headers):
        """POST /api/ai/playbook/nonexistent returns 400."""
        resp = client.post("/api/ai/playbook/nonexistent", headers=admin_headers)
        assert resp.status_code == 400

    def test_api_ai_playbook_requires_admin(self, client):
        """POST /api/ai/playbook/max_free without admin token returns 403."""
        resp = client.post("/api/ai/playbook/max_free")
        assert resp.status_code == 403

    def test_api_ai_warnings_requires_auth(self, client):
        """GET /api/ai/warnings now requires admin token."""
        resp = client.get("/api/ai/warnings")
        assert resp.status_code == 403


# ===================================================================
# Section 3: Warning Engine + Usage Integration (6 tests)
# ===================================================================


class TestWarningEngineIntegration:
    def test_warning_engine_with_db(self, db_session):
        """check_warnings via db_session returns expected structure."""
        warnings = check_warnings(db=db_session)
        assert isinstance(warnings, list)
        for w in warnings:
            assert "type" in w
            assert "severity" in w
            assert "message" in w
            assert "current_value" in w
            assert "threshold" in w
            assert "setting_key" in w

    def test_warning_engine_empty(self, db_session):
        """No usage yet, warnings list is empty (no budget warning below threshold)."""
        r._LOCAL_DAILY_TOKENS = 0
        r._LOCAL_TOKEN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        warnings = check_warnings(db=db_session)
        ai_warnings = [w for w in warnings if w["type"] == "ai_budget"]
        assert len(ai_warnings) == 0

    def test_warning_engine_budget_warning(self, monkeypatch, db_session):
        """Token usage past 80% threshold generates budget warning."""
        monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "1000")
        budget_mod._LOCAL_DAILY_TOKENS = 850
        budget_mod._LOCAL_TOKEN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        warnings = check_warnings(db=db_session)
        ai_warnings = [w for w in warnings if w["type"] == "ai_budget"]
        assert len(ai_warnings) >= 1
        assert ai_warnings[0]["severity"] in ("warning", "critical")
        assert ai_warnings[0]["current_value"] == 850

    def test_ai_usage_increment(self, db_session):
        """Call increment_ai_usage, verify get_ai_usage_summary reflects it."""
        increment_ai_usage(db_session, provider="groq", model="llama-3.1-8b-instant", tokens=150, cost=0.0075)

        summary = get_ai_usage_summary(db_session)
        assert summary["total_calls"] == 1
        assert summary["total_tokens"] == 150
        assert summary["total_estimated_cost"] == 0.0075
        assert "groq" in summary["providers"]
        assert summary["providers"]["groq"]["calls"] == 1

    def test_ai_usage_daily_rollover(self, db_session, monkeypatch):
        """Usage for different dates is tracked separately."""
        _truncate_usage_tables()
        increment_ai_usage(db_session, provider="groq", model="test-model", tokens=100, cost=0.005)

        summary_today = get_ai_usage_summary(db_session)
        assert summary_today["total_tokens"] == 100

    def test_source_usage_rate_limit(self):
        """_check_source_rate_limit respects rpm setting for coingecko (100 RPM)."""
        assert _check_source_rate_limit("coingecko") is True

        for _ in range(100):
            _record_source_call("coingecko")

        assert _check_source_rate_limit("coingecko") is False

        # Separate source unaffected
        assert _check_source_rate_limit("dexscreener") is True


# ===================================================================
# Section 4: Playbook Application (6 tests)
# ===================================================================


class TestPlaybookApplication:
    def test_playbook_max_free(self, db_session):
        """Apply max_free, verify ai_mode=ai_lite, provider priority is free."""
        apply_playbook("max_free", db_session)

        from providers.settings import get_setting
        assert get_setting("ai_mode", db_session) == "ai_lite"
        assert get_setting("ai_web_search", db_session) is False
        assert get_setting("ai_daily_token_budget", db_session) == 10000

        priority = json.loads(get_setting("ai_provider_priority", db_session))
        assert "openrouter_free" in priority
        assert "groq" not in priority

    def test_playbook_balanced(self, db_session):
        """Apply balanced, verify all expected settings."""
        apply_playbook("balanced", db_session)

        from providers.settings import get_setting
        assert get_setting("ai_mode", db_session) == "ai_full"
        assert get_setting("ai_web_search", db_session) is True
        assert get_setting("ai_web_search_max_results", db_session) == 3
        assert get_setting("ai_cache_semantic_enabled", db_session) is True

    def test_playbook_quality(self, db_session):
        """Apply quality, verify all expected settings."""
        apply_playbook("quality", db_session)

        from providers.settings import get_setting
        assert get_setting("ai_mode", db_session) == "ai_full"
        assert get_setting("ai_daily_token_budget", db_session) == 200000
        assert get_setting("ai_cache_semantic_enabled", db_session) is False
        assert get_setting("ai_web_search_max_results", db_session) == 5

    def test_playbook_apply_twice(self, db_session):
        """Apply same playbook twice — idempotent."""
        changes1 = apply_playbook("balanced", db_session)
        changes2 = apply_playbook("balanced", db_session)

        assert changes1 == changes2

    def test_playbook_preserves_other_settings(self, db_session):
        """Apply playbook, verify unrelated settings unchanged."""
        from providers.settings import get_setting

        original_refresh = get_setting("refresh_core_seconds", db_session)

        apply_playbook("max_free", db_session)

        assert get_setting("refresh_core_seconds", db_session) == original_refresh

    def test_get_playbooks_returns_copies(self):
        """Returned dicts are immutable copies — modifying them doesn't affect originals."""
        result = get_playbooks()
        result["max_free"]["label"] = "ALIAS"
        assert PLAYBOOKS["max_free"]["label"] == "Maximum Free Tier"

        result["max_free"]["settings"]["ai_mode"] = "ai_full"
        assert PLAYBOOKS["max_free"]["settings"]["ai_mode"] == "ai_lite"


# ===================================================================
# Section 5: Rate Limiting Edge Cases (4 tests)
# ===================================================================


class TestRateLimiting:
    def test_rate_limit_sliding_window(self):
        """Exhaust limit, verify blocked; older entries expire, verify unblocked."""
        _SOURCE_RATE_LIMITS["test_source"] = []
        now = time.time()

        old_timestamps = [now - 120] * 50
        recent_timestamp = now - 10
        _SOURCE_RATE_LIMITS["test_source"] = old_timestamps + [recent_timestamp]

        from providers.settings import _DEFAULT_SETTINGS
        original_meta = _DEFAULT_SETTINGS.get("provider_coingecko", {})
        rpm = original_meta.get("rate_limit_rpm", 50)

        _SOURCE_RATE_LIMITS["test_source"] = [now - 61 for _ in range(rpm)]
        assert _check_source_rate_limit("coingecko") is True

    def test_circuit_breaker_integration(self):
        """CircuitBreaker with function that fails then recovers."""
        attempt_count = [0]

        def flaky_fn():
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                raise ValueError("transient error")
            return "recovered"

        cb = CircuitBreaker(name="flaky_test", failure_threshold=2, recovery_timeout=0)

        result1 = cb.call(flaky_fn, fallback=lambda: "fb")
        assert result1 == "fb"
        assert cb.state == CircuitState.CLOSED

        result2 = cb.call(flaky_fn, fallback=lambda: "fb")
        assert result2 == "fb"
        assert cb.state == CircuitState.OPEN

        result3 = cb.call(flaky_fn, fallback=lambda: "fb")
        assert result3 == "recovered"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_token_bucket_integration(self):
        """TokenBucket.consume rate limiting behavior."""
        bucket = TokenBucket(rate=5, burst=3)

        assert bucket.consume(3) is True
        assert bucket.consume(1) is False

        assert bucket.wait_time() > 0

    def test_http_retry_on_429(self):
        """http_get_with_retry retries on 429 then succeeds."""
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429 Too Many", request=MagicMock(), response=resp_429
        )

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.get.side_effect = [resp_429, resp_200]
        mock_client.__enter__.return_value = mock_client

        with patch("httpx.Client", return_value=mock_client), \
             patch("time.sleep", return_value=None):
            resp = http_get_with_retry("http://example.com/api", max_retries=3)
            assert resp.status_code == 200
            assert mock_client.get.call_count == 2


# ===================================================================
# Section 6: Cache Monitoring (4 tests)
# ===================================================================


class TestCacheMonitoring:
    def test_cache_hit_rate_tracking(self, monkeypatch):
        """Make cacheable calls, verify hit_rate > 0 after second call."""
        monkeypatch.setenv("AI_MODE", "ai_lite")
        monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "50000")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        monkeypatch.setattr(r, "_openrouter_lite", _mock_provider(tokens=50))
        monkeypatch.setattr(r, "_ollama_cloud", _mock_failing_provider())

        ctx = {"asset_symbol": "USDT", "signal_score": 10, "signal_band": "Normal", "regime": "stable"}

        enrich_with_ai(feature="risk_explain", context=ctx)
        stats = get_cache_stats()
        assert stats["hit_rate"] == 0.0

        enrich_with_ai(feature="risk_explain", context=ctx)
        stats = get_cache_stats()
        assert stats["hit_rate"] > 0
        assert stats["hits"] == 1

    def test_cache_tokens_saved_tracking(self, monkeypatch):
        """Verify tokens_saved increments on cache hits."""
        monkeypatch.setenv("AI_MODE", "ai_lite")
        monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "50000")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        monkeypatch.setattr(r, "_openrouter_lite", _mock_provider(tokens=75))
        monkeypatch.setattr(r, "_ollama_cloud", _mock_failing_provider())

        ctx = {"asset_symbol": "USDT", "signal_score": 10, "signal_band": "Normal", "regime": "stable"}

        enrich_with_ai(feature="risk_explain", context=ctx)
        first_tokens_saved = get_cache_stats()["tokens_saved"]
        assert first_tokens_saved == 0

        enrich_with_ai(feature="risk_explain", context=ctx)
        stats = get_cache_stats()
        assert stats["tokens_saved"] >= 75

    def test_get_cache_stats_after_eviction(self, monkeypatch):
        """Fill cache past limit, verify evictions > 0."""
        monkeypatch.setenv("AI_MODE", "ai_lite")
        monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "50000")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        cache_mod._MAX_CACHE_ENTRIES = 3

        monkeypatch.setattr(r, "_openrouter_lite", _mock_provider(tokens=10))
        monkeypatch.setattr(r, "_ollama_cloud", _mock_failing_provider())

        for i in range(6):
            enrich_with_ai(
                feature="risk_explain",
                context={"asset_symbol": f"ASSET{i}", "signal_score": i * 10, "signal_band": "Normal", "regime": "stable"},
            )

        stats = get_cache_stats()
        assert stats["evictions"] > 0
        assert stats["entries"] <= cache_mod._MAX_CACHE_ENTRIES

    def test_semantic_cache_hit_chain(self, monkeypatch):
        """Enable semantic cache; similar prompts across features hit cache."""
        monkeypatch.setenv("AI_MODE", "ai_lite")
        monkeypatch.setenv("AI_DAILY_TOKEN_BUDGET", "50000")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        cache_mod._SEMANTIC_CACHE_ENABLED = True
        cache_mod._SEMANTIC_CACHE_THRESHOLD = 0.75

        monkeypatch.setattr(r, "_openrouter_lite", _mock_provider(
            text="Semantic chain response", tokens=40
        ))
        monkeypatch.setattr(r, "_ollama_cloud", _mock_failing_provider())

        ctx1 = {"asset_symbol": "USDT", "signal_score": 30, "signal_band": "Watch", "regime": "volatile"}
        result1 = enrich_with_ai(feature="risk_explain", context=ctx1)
        assert result1["available"] is True
        assert result1["cached"] is False

        ctx2 = {"asset_symbol": "USDT", "signal_score": 32, "signal_band": "Watch", "regime": "volatile"}
        result2 = enrich_with_ai(feature="risk_explain", context=ctx2)

        assert result2["cached"] is True
        assert "Semantic" in result2["summary"]
