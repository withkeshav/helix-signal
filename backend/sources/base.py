from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx


class AbstractSource(ABC):
    name: str = "abstract"

    def __init__(self) -> None:
        self._session: httpx.Client | None = None
        self._async_session: httpx.AsyncClient | None = None

    def get_http_session(self) -> httpx.Client:
        if self._session is None:
            transport = httpx.HTTPTransport(retries=3)
            self._session = httpx.Client(
                transport=transport,
                timeout=httpx.Timeout(20),
                follow_redirects=False,
            )
        return self._session

    async def get_async_http_session(self) -> httpx.AsyncClient:
        if self._async_session is None:
            self._async_session = httpx.AsyncClient(
                timeout=httpx.Timeout(20),
                follow_redirects=False,
            )
        return self._async_session

    @abstractmethod
    def fetch(self, **kwargs: Any) -> Any:
        ...

    async def async_fetch(self, **kwargs: Any) -> Any:
        return self.fetch(**kwargs)

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    async def aclose(self) -> None:
        if self._async_session is not None:
            await self._async_session.aclose()
            self._async_session = None

    @abstractmethod
    def transform(self, raw: Any) -> dict[str, Any]:
        ...


def http_get_with_retry(
    url: str,
    *,
    timeout: float = 20,
    max_retries: int = 3,
    base_delay: float = 5.0,
) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False) as session:
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


async def async_http_get_with_retry(
    url: str,
    *,
    timeout: float = 20,
    max_retries: int = 3,
    base_delay: float = 5.0,
) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as session:
                resp = await session.get(url)
                if resp.status_code in (429, 502, 503, 504):
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 2)
                    await _async_sleep(delay)
                    continue
                resp.raise_for_status()
                return resp
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt) + random.uniform(0, 2)
            await _async_sleep(delay)
            continue
    raise last_exc or httpx.HTTPError(f"Request failed after {max_retries} retries: {url}")


async def _async_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
