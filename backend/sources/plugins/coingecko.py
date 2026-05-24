from datetime import datetime, timezone
from typing import Any

from backend.core.circuit_breaker import CircuitBreaker
from backend.core.registry import register_source
from sources.base import AbstractSource
from sources.coingecko import CoinGeckoSource as _LegacyCoinGeckoSource


@register_source("coingecko")
class CoinGeckoSource(AbstractSource):
    name = "coingecko"

    def __init__(self):
        super().__init__()
        self._inner = _LegacyCoinGeckoSource()
        self.circuit_breaker = CircuitBreaker(name="coingecko", failure_threshold=3)

    def fetch(self, **kwargs: Any) -> dict[str, Any]:
        def _do_fetch():
            return self._inner.fetch(**kwargs)

        def _fallback():
            return {"status": "degraded", "source": "coingecko", "data": None}

        return self.circuit_breaker.call(_do_fetch, fallback=_fallback)

    def transform(self, raw: dict[str, Any]) -> dict[str, Any]:
        return self._inner.transform(raw)

    def health_check(self) -> dict:
        return self.circuit_breaker.to_dict()
