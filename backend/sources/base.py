from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


class SourceError(Exception):
    """Raised when a source cannot fetch or parse data."""


class AbstractSource(ABC):
    name: str = "abstract"

    def __init__(self) -> None:
        self._session: Session | None = None

    def get_http_session(self) -> Session:
        if self._session is None:
            self._session = Session()
            retries = Retry(
                total=3,
                backoff_factor=1.0,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
            )
            adapter = HTTPAdapter(max_retries=retries)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)
        return self._session

    @abstractmethod
    def fetch(self, **kwargs: Any) -> Any:
        ...

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
