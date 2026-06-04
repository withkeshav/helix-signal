"""Chainlink Proof of Reserve source plugin.

Fetches on-chain reserve attestation data via Chainlink PoR oracle contracts.
Requires RPC endpoint. Registers as @register_source("chainlink") with circuit
breaker. Falls back gracefully when no RPC configured.
"""

from __future__ import annotations

from typing import Any

import requests

from core.registry import register_source
from core.circuit_breaker import CircuitBreaker
from sources.base import AbstractSource


@register_source("chainlink")
class ChainlinkPoRSource(AbstractSource):
    name = "chainlink"
    config_schema = {
        "rpc_url": {"type": str, "required": True},
        "por_contract": {"type": str, "required": False},
    }

    def __init__(self):
        super().__init__()
        self.circuit_breaker = CircuitBreaker(name="chainlink", failure_threshold=5)

    def fetch(self, **kwargs) -> dict[str, Any]:
        asset_config = kwargs.get("asset_config") or {}
        sym = asset_config.get("symbol", "").upper()

        def _do_fetch():
            return self._query_por(sym)

        def _fallback():
            return {
                "source": "chainlink",
                "status": "degraded",
                "asset_symbol": sym,
                "reserves": None,
                "timestamp": None,
                "note": "Chainlink PoR not configured or unavailable. Set CHAINLINK_RPC_URL in .env",
            }

        return self.circuit_breaker.call(_do_fetch, fallback=_fallback)

    def _query_por(self, symbol: str) -> dict[str, Any]:
        import os

        rpc_url = os.getenv("CHAINLINK_RPC_URL", "")
        por_contract = os.getenv("CHAINLINK_POR_CONTRACT", "")
        if not rpc_url:
            return {
                "source": "chainlink",
                "status": "not_configured",
                "asset_symbol": symbol,
                "note": "CHAINLINK_RPC_URL not set",
            }

        payload = {
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{"to": por_contract, "data": "0x0e5b8e4b"}, "latest"],
            "id": 1,
        }
        resp = requests.post(rpc_url, json=payload, timeout=15)
        data = resp.json()

        result = data.get("result", "0x")
        reserves = int(result, 16) if result and result != "0x" else None

        return {
            "source": "chainlink",
            "status": "ok",
            "asset_symbol": symbol,
            "reserves": reserves,
            "contract": por_contract,
            "note": "Chainlink PoR on-chain attestation",
        }

    def health_check(self) -> dict[str, Any]:
        import os

        rpc_url = os.getenv("CHAINLINK_RPC_URL", "")
        return {
            "source": self.name,
            "state": self.circuit_breaker.state.value,
            "failure_count": self.circuit_breaker.failure_count,
            "configured": bool(rpc_url),
            "rpc_url": rpc_url or "not_set",
        }
