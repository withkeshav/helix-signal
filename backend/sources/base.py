from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import httpx


class SourceError(Exception):
    """Raised when a source cannot fetch or parse data."""


class AbstractSource(ABC):
    name: str = "abstract"

    def __init__(self) -> None:
        self._session: httpx.Client | None = None

    def get_http_session(self) -> httpx.Client:
        if self._session is None:
            transport = httpx.HTTPTransport(retries=3)
            self._session = httpx.Client(
                transport=transport,
                timeout=httpx.Timeout(20),
            )
        return self._session

    @abstractmethod
    def fetch(self, **kwargs: Any) -> Any:
        ...

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def validate(self, raw: Any) -> bool:
        return raw is not None

    @abstractmethod
    def transform(self, raw: Any) -> dict[str, Any]:
        ...

    def status_payload(self, ok: bool, error: str | None = None) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "source_name": self.name,
            "status": "ok" if ok else "error",
            "last_attempted_fetch": now,
            "last_successful_fetch": now if ok else None,
            "last_error": error,
            "updated_at": now,
        }


def http_get_with_retry(
    url: str,
    *,
    timeout: float = 20,
    max_retries: int = 3,
    base_delay: float = 5.0,
) -> httpx.Response:
    """HTTP GET with exponential backoff for 429/503 responses.

    Connection errors are handled by httpx.HTTPTransport(retries=3).
    This handles HTTP-level rate limiting and server errors.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=timeout) as session:
                resp = session.get(url)
                if resp.status_code in (429, 502, 503, 504):
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 2)
                    time.sleep(delay)
                    continue
                resp.raise_for_status()
                return resp
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt) + random.uniform(0, 2)
            time.sleep(delay)
            continue
    raise last_exc or httpx.HTTPError(f"Request failed after {max_retries} retries: {url}")
