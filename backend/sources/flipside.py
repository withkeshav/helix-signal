"""Flipside — optional holder flow SQL queries (transform.md §5.1, 500 query-seconds/mo free)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from providers.settings import get_setting
from services.source_usage import _check_source_rate_limit, _record_source_call
from sources.onchain_tokens import ETHEREUM_TOKENS

FLIPSIDE_API = "https://api-v2.flipsidecrypto.xyz/json-rpc"


class FlipsideSource:
    name = "flipside"

    def _api_key(self, db: Any = None) -> str:
        return str(get_setting("secret_flipside_api_key", db) or "").strip()

    def configured(self, db: Any = None) -> bool:
        return bool(self._api_key(db)) and bool(get_setting("provider_flipside", db))

    def _rpc(self, method: str, params: list[Any], db: Any = None) -> Any:
        key = self._api_key(db)
        if not key:
            return None
        while not _check_source_rate_limit(self.name):
            import time
            time.sleep(1)
        _record_source_call(self.name)
        try:
            resp = httpx.post(
                FLIPSIDE_API,
                json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
                headers={"x-api-key": key, "Content-Type": "application/json"},
                timeout=45,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("error"):
                return None
            return body.get("result")
        except Exception:
            return None

    def fetch_holder_flow(self, symbol: str, *, db: Any = None) -> dict[str, Any]:
        sym = symbol.upper()
        if sym not in ETHEREUM_TOKENS:
            return {"available": False, "reason": "unsupported_asset"}
        if not self.configured(db):
            return {"available": False, "reason": "flipside_not_configured"}

        contract = str(ETHEREUM_TOKENS[sym]["address"]).lower()
        # contract from hardcoded ETHEREUM_TOKENS dict — safe from injection.
        # If Flipside API ever supports parameterized queries, migrate to that.
        sql = f"""
        SELECT
          COUNT(*) AS transfer_count,
          SUM(amount_usd) AS volume_usd
        FROM ethereum.core.ez_token_transfers
        WHERE contract_address = lower('{contract}')
          AND block_timestamp >= CURRENT_DATE - 1
        """
        result = self._rpc("createQueryRun", [{"sql": sql, "tags": {"source": "helix-signal"}}], db)
        if not result:
            return {"available": False, "reason": "flipside_error"}

        query_id = result.get("queryRunId") or result.get("id")
        if not query_id:
            return {"available": False, "reason": "flipside_no_query_id"}

        rows_result = self._rpc("getQueryRunResults", [{"queryRunId": query_id}], db)
        rows = (rows_result or {}).get("rows") or []
        transfer_count = 0
        volume_usd = 0.0
        if rows:
            transfer_count = int(rows[0].get("TRANSFER_COUNT") or rows[0].get("transfer_count") or 0)
            volume_usd = float(rows[0].get("VOLUME_USD") or rows[0].get("volume_usd") or 0)

        return {
            "available": True,
            "source": self.name,
            "transfer_count_24h": transfer_count,
            "volume_usd_24h": round(volume_usd, 2),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
