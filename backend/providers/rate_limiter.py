from __future__ import annotations

import time
from threading import Lock


class TokenBucket:
    """Thread-safe token bucket rate limiter.

    Each provider gets its own bucket. If the bucket is empty the
    caller can skip the request instead of hammering the API.
    """

    def __init__(self, rate: float, burst: int) -> None:
        self._lock = Lock()
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to consume *tokens* from the bucket. Returns True if allowed."""
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def wait_time(self) -> float:
        """Seconds until the bucket has enough tokens for one request."""
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                return 0.0
            return (1.0 - self._tokens) / self._rate if self._rate > 0 else float("inf")

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(float(self._burst), self._tokens + elapsed * self._rate)
        self._last_refill = now
