from datetime import datetime, timezone
from typing import Any

from backend.core.circuit_breaker import CircuitBreaker
from backend.core.registry import register_source
from sources.base import AbstractSource
from sources.defillama import (
    _DefiLlamaSource as _LegacyDefiLlamaSource,
    _discover_chain_ids,
    fetch_chain_tvl_by_defillama_name,
    fetch_stablecoin_chart_points,
    DefiLlamaError,
)


@register_source("defillama")
class DefiLlamaSource(AbstractSource):
    name = "defillama"

    def __init__(self):
        super().__init__()
        self._inner = _LegacyDefiLlamaSource()
        self.circuit_breaker = CircuitBreaker(name="defillama", failure_threshold=3)

    def fetch(self, **kwargs: Any) -> dict[str, Any]:
        def _do_fetch():
            return self._inner.fetch(**kwargs)

        def _fallback():
            return {
                "status": "degraded",
                "source": "defillama",
                "data": None,
                "fetched_at": datetime.now(timezone.utc),
            }

        return self.circuit_breaker.call(_do_fetch, fallback=_fallback)

    def transform(self, raw: dict[str, Any]) -> dict[str, Any]:
        return self._inner.transform(raw)

    def health_check(self) -> dict:
        return self.circuit_breaker.to_dict()

    def discover_chain_ids(self) -> list[str]:
        return _discover_chain_ids()

    def get_chain_tvl(self) -> dict[str, float]:
        return fetch_chain_tvl_by_defillama_name()

    def get_chart_points(self, symbol: str, days: int) -> list[dict]:
        return fetch_stablecoin_chart_points(symbol=symbol, days=days)
