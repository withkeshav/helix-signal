from datetime import datetime, timezone
from typing import Any

from backend.core.circuit_breaker import CircuitBreaker
from backend.core.registry import register_source
from sources.base import AbstractSource
from sources.dexscreener import DexScreenerSource as _LegacyDexScreenerSource


@register_source("dexscreener")
class DexScreenerSource(AbstractSource):
    name = "dexscreener"

    def __init__(self):
        super().__init__()
        self._inner = _LegacyDexScreenerSource()
        self.circuit_breaker = CircuitBreaker(name="dexscreener", failure_threshold=3)

    def fetch(self, **kwargs: Any) -> list[dict[str, Any]]:
        def _do_fetch():
            return self._inner.fetch(**kwargs)

        def _fallback():
            return []

        return self.circuit_breaker.call(_do_fetch, fallback=_fallback)

    def transform(self, raw: list[dict[str, Any]]) -> dict[str, Any]:
        return self._inner.transform(raw)

    def health_check(self) -> dict:
        return self.circuit_breaker.to_dict()
