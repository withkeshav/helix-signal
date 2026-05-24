from __future__ import annotations

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
            transport = httpx.HTTPTransport()
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
