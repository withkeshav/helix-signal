"""Tests for rate limiting infrastructure: TokenBucket, source rate limits,
CircuitBreaker, and HTTP retry logic."""

from __future__ import annotations

import time
from unittest.mock import patch, MagicMock, AsyncMock

import httpx
import pytest

from core.circuit_breaker import CircuitBreaker, CircuitState
from providers.rate_limiter import TokenBucket
from services.source_usage import _check_source_rate_limit, _record_source_call, _SOURCE_RATE_LIMITS


# ---------------------------------------------------------------------------
# TokenBucket
# ---------------------------------------------------------------------------

class TestTokenBucket:
    def test_consume_allows_with_tokens(self):
        bucket = TokenBucket(rate=10, burst=5)
        for _ in range(5):
            assert bucket.consume(), "should allow while tokens remain"

    def test_consume_blocks_when_empty(self):
        bucket = TokenBucket(rate=10, burst=3)
        for _ in range(3):
            bucket.consume()
        assert not bucket.consume(), "should deny when bucket is empty"

    def test_wait_time_zero_when_tokens_available(self):
        bucket = TokenBucket(rate=1, burst=5)
        assert bucket.wait_time() == 0.0

    def test_wait_time_positive_when_empty(self):
        bucket = TokenBucket(rate=2, burst=1)
        bucket.consume()
        wt = bucket.wait_time()
        assert wt > 0, "wait_time should be positive when bucket is empty"

    def test_refill_over_time(self):
        bucket = TokenBucket(rate=10, burst=5)
        for _ in range(5):
            bucket.consume()
        assert not bucket.consume(1.0)
        time.sleep(0.15)
        assert bucket.consume(1.0)

    def test_consume_multiple_tokens(self):
        bucket = TokenBucket(rate=10, burst=5)
        assert bucket.consume(3)
        assert bucket.consume(2)
        assert not bucket.consume(1)

    def test_wait_time_infinite_with_zero_rate(self):
        bucket = TokenBucket(rate=0, burst=0)
        assert bucket.wait_time() == float("inf")

    def test_thread_safety(self):
        import threading
        bucket = TokenBucket(rate=1000, burst=100)
        errors = []
        def hammer():
            for _ in range(50):
                try:
                    bucket.consume()
                except Exception as e:
                    errors.append(e)
        threads = [threading.Thread(target=hammer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


# ---------------------------------------------------------------------------
# _check_source_rate_limit / _record_source_call
# ---------------------------------------------------------------------------

class TestSourceRateLimit:
    def setup_method(self):
        _SOURCE_RATE_LIMITS.clear()

    def test_within_limit(self):
        assert _check_source_rate_limit("coingecko")  # 50 RPM, 0 calls

    def test_near_limit(self):
        for _ in range(49):
            _record_source_call("coingecko")
        assert _check_source_rate_limit("coingecko")

    def test_at_limit(self):
        for _ in range(100):
            _record_source_call("coingecko")
        assert not _check_source_rate_limit("coingecko")

    def test_over_limit(self):
        for _ in range(105):
            _record_source_call("coingecko")
        assert not _check_source_rate_limit("coingecko")

    def test_unknown_source_returns_true(self):
        assert _check_source_rate_limit("nonexistent_source")

    def test_dexscreener_limit(self):
        for _ in range(119):
            _record_source_call("dexscreener")
        assert _check_source_rate_limit("dexscreener")
        _record_source_call("dexscreener")
        assert not _check_source_rate_limit("dexscreener")

    def test_window_slides(self):
        now = time.time()
        _SOURCE_RATE_LIMITS["coingecko"] = [now - 61] * 50 + [now - 30]
        assert _check_source_rate_limit("coingecko")

    def test_separate_trackers_per_source(self):
        _record_source_call("coingecko")
        assert _check_source_rate_limit("dexscreener")


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_closed_state_on_success(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(name="test", failure_threshold=2)
        for _ in range(2):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")), fallback=lambda: "fb")
        assert cb.state == CircuitState.OPEN

    def test_fallback_returned_on_failure(self):
        cb = CircuitBreaker(name="test", failure_threshold=1)
        result = cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")), fallback=lambda: "fallback_val")
        assert result == "fallback_val"

    def test_half_open_transition_after_recovery(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0)
        cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")), fallback=lambda: "fb")
        assert cb.state == CircuitState.OPEN
        result = cb.call(lambda: "recovered", fallback=lambda: "fb")
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED

    def test_half_open_limited_requests(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=10, half_open_max_requests=1)
        cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")), fallback=lambda: "fb")
        cb.last_failure_time = 0
        assert cb.call(lambda: "ok1") == "ok1"
        assert cb.state == CircuitState.CLOSED

    def test_half_open_rejects_excess_requests(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=10, half_open_max_requests=1)
        cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")), fallback=lambda: "fb")
        cb.last_failure_time = 0
        cb.state = CircuitState.HALF_OPEN
        cb.half_open_requests = 1
        result = cb.call(lambda: "should_not_run", fallback=lambda: "fb")
        assert result == "fb"

    def test_closes_after_half_open_success(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0)
        cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")), fallback=lambda: "fb")
        assert cb.state == CircuitState.OPEN
        cb.call(lambda: "success")
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_fallback_none_by_default(self):
        cb = CircuitBreaker(name="test", failure_threshold=1)
        result = cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert result is None

    def test_to_dict(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        d = cb.to_dict()
        assert d["source"] == "test"
        assert d["state"] == "closed"
        assert d["failure_count"] == 0

    def test_concurrent_safety(self):
        import threading
        cb = CircuitBreaker(name="test", failure_threshold=3)
        errors = []
        def hit():
            try:
                cb.call(lambda: (_ for _ in ()).throw(ValueError("x")), fallback=lambda: None)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=hit) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


# ---------------------------------------------------------------------------
# HTTP retry logic (http_get_with_retry)
# ---------------------------------------------------------------------------

class TestHttpRetry:
    def _make_client_mock(self, get_return=None, side_effect=None):
        mock = MagicMock()
        mock.get.return_value = get_return
        if side_effect is not None:
            mock.get.side_effect = side_effect
        mock.__enter__.return_value = mock
        return mock

    def _make_resp_mock(self, status_code: int, raises: bool = False):
        mock = MagicMock()
        mock.status_code = status_code
        if raises:
            mock.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"{status_code} error", request=MagicMock(), response=mock
            )
        else:
            mock.raise_for_status.return_value = None
        return mock

    def test_success_on_first_try(self):
        resp = self._make_resp_mock(200)
        client = self._make_client_mock(get_return=resp)

        with patch("httpx.Client", return_value=client):
            from sources.base import http_get_with_retry
            result = http_get_with_retry("http://example.com/api")
            assert result.status_code == 200

    def test_retry_on_429_then_success(self):
        resp_429 = self._make_resp_mock(429)
        resp_200 = self._make_resp_mock(200)
        client = self._make_client_mock(side_effect=[resp_429, resp_200])

        with patch("httpx.Client", return_value=client), \
             patch("time.sleep", return_value=None):
            from sources.base import http_get_with_retry
            resp = http_get_with_retry("http://example.com/api", max_retries=3)
            assert resp.status_code == 200
            assert client.get.call_count == 2

    def test_retry_on_503_then_success(self):
        resp_503 = self._make_resp_mock(503)
        resp_200 = self._make_resp_mock(200)
        client = self._make_client_mock(side_effect=[resp_503, resp_503, resp_200])

        with patch("httpx.Client", return_value=client), \
             patch("time.sleep", return_value=None):
            from sources.base import http_get_with_retry
            resp = http_get_with_retry("http://example.com/api", max_retries=3)
            assert resp.status_code == 200
            assert client.get.call_count == 3

    def test_exhaust_retries_raises(self):
        resp = self._make_resp_mock(429)
        client = self._make_client_mock(get_return=resp)

        with patch("httpx.Client", return_value=client), \
             patch("time.sleep", return_value=None):
            from sources.base import http_get_with_retry
            with pytest.raises(httpx.HTTPError):
                http_get_with_retry("http://example.com/api", max_retries=2)

    def test_retry_on_connection_error(self):
        client = self._make_client_mock()
        resp_200 = self._make_resp_mock(200)
        client.get.side_effect = [
            httpx.ConnectError("connection refused"),
            resp_200,
        ]

        with patch("httpx.Client", return_value=client), \
             patch("time.sleep", return_value=None):
            from sources.base import http_get_with_retry
            resp = http_get_with_retry("http://example.com/api", max_retries=3)
            assert resp.status_code == 200

    def test_retry_on_timeout(self):
        client = self._make_client_mock()
        resp_200 = self._make_resp_mock(200)
        client.get.side_effect = [
            httpx.TimeoutException("timed out"),
            resp_200,
        ]

        with patch("httpx.Client", return_value=client), \
             patch("time.sleep", return_value=None):
            from sources.base import http_get_with_retry
            resp = http_get_with_retry("http://example.com/api", max_retries=3)
            assert resp.status_code == 200

    def test_retry_on_all_http_errors(self):
        resp = MagicMock()
        resp.status_code = 400
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400 Bad Request", request=MagicMock(), response=resp
        )

        client = self._make_client_mock(get_return=resp)

        with patch("httpx.Client", return_value=client), \
             patch("time.sleep", return_value=None):
            from sources.base import http_get_with_retry
            with pytest.raises(httpx.HTTPError):
                http_get_with_retry("http://example.com/api", max_retries=3)
            assert client.get.call_count == 3

    def _make_async_client_mock(self, side_effect=None):
        mock = AsyncMock()
        mock.get = AsyncMock(side_effect=side_effect)
        mock.__aenter__.return_value = mock
        return mock

    def test_async_retry_on_429_then_success(self):
        import asyncio
        resp_429 = self._make_resp_mock(429)
        resp_200 = self._make_resp_mock(200)
        client = self._make_async_client_mock(side_effect=[resp_429, resp_200])

        with patch("httpx.AsyncClient", return_value=client), \
             patch("asyncio.sleep", return_value=None):
            from sources.base import async_http_get_with_retry
            resp = asyncio.run(async_http_get_with_retry("http://example.com/api", max_retries=3))
            assert resp.status_code == 200
            assert client.get.call_count == 2
