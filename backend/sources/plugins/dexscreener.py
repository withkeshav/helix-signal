from typing import Any

from core.circuit_breaker import CircuitBreaker
from core.registry import register_source
from services.source_usage import increment_source_usage
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
        db = kwargs.pop("db", None)

        def _do_fetch():
            return self._inner.fetch(**kwargs)

        def _fallback():
            return []

        result = self.circuit_breaker.call(_do_fetch, fallback=_fallback)
        if db is not None:
            increment_source_usage(db, self.name)
        return result

    def transform(self, raw: list[dict[str, Any]]) -> dict[str, Any]:
        return self._inner.transform(raw)

    def health_check(self) -> dict:
        return self.circuit_breaker.to_dict()
