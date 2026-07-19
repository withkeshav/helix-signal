"""The Graph — mint/burn transfer events for USDT/USDC on Ethereum (transform.md §5.1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from providers.settings import get_setting, get_secret
from services.source_usage import _check_source_rate_limit, _record_source_call
from sources.onchain_tokens import ETHEREUM_TOKENS, ZERO_ADDRESS, DEFAULT_GRAPH_SUBGRAPH_URL

_GRAPH_HOST_ALLOWLIST = frozenset({
    "api.thegraph.com",
    "gateway.thegraph.com",
    "api.studio.thegraph.com",
    "gateway-arbitrum.network.thegraph.com",
})


def _validate_subgraph_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("https",):
        raise ValueError(f"thegraph URL must use https: {url}")
    if parsed.hostname not in _GRAPH_HOST_ALLOWLIST:
        raise ValueError(f"thegraph URL host not in allowlist: {parsed.hostname}")
    return url


class TheGraphSource:
    name = "thegraph"

    def _subgraph_url(self, db: Any = None) -> str:
        custom = (get_setting("thegraph_subgraph_url", db) or "").strip()
        url = custom or DEFAULT_GRAPH_SUBGRAPH_URL
        return _validate_subgraph_url(url)

    def _api_key(self, db: Any = None) -> str:
        return str(get_secret("secret_thegraph_api_key", db) or "").strip()

    def _headers(self, db: Any = None) -> dict[str, str]:
        key = self._api_key(db)
        if key:
            return {"Authorization": f"Bearer {key}"}
        return {}

    def _post_graphql(self, query: str, variables: dict[str, Any], db: Any = None) -> dict[str, Any] | None:
        if not get_setting("provider_thegraph", db):
            return None
        while not _check_source_rate_limit(self.name):
            import time
            time.sleep(1)
        _record_source_call(self.name)
        url = self._subgraph_url(db)
        try:
            resp = httpx.post(
                url,
                json={"query": query, "variables": variables},
                headers=self._headers(db),
                timeout=20,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("errors"):
                return None
            return body.get("data") or {}
        except Exception:
            return None

    def fetch_mint_burn(self, symbol: str, *, hours: int = 24, db: Any = None) -> dict[str, Any]:
        sym = symbol.upper()
        token = ETHEREUM_TOKENS.get(sym)
        if not token:
            return {"available": False, "reason": "unsupported_asset"}

        since = int(datetime.now(timezone.utc).timestamp()) - hours * 3600
        address = str(token["address"]).lower()
        decimals = int(token["decimals"])

        query = """
        query MintBurn($token: String!, $since: Int!) {
          mints: transfers(
            first: 100
            orderBy: timestamp
            orderDirection: desc
            where: { token: $token, from: "0x0000000000000000000000000000000000000000", timestamp_gte: $since }
          ) { id value timestamp transactionHash }
          burns: transfers(
            first: 100
            orderBy: timestamp
            orderDirection: desc
            where: { token: $token, to: "0x0000000000000000000000000000000000000000", timestamp_gte: $since }
          ) { id value timestamp transactionHash }
        }
        """
        data = self._post_graphql(query, {"token": address, "since": since}, db)
        if data is None:
            return {"available": False, "reason": "graph_unavailable"}

        mints = data.get("mints") or []
        burns = data.get("burns") or []

        def _sum_usd(rows: list[dict]) -> float:
            total = 0.0
            for row in rows:
                raw = float(row.get("value") or 0)
                total += raw / (10 ** decimals)
            return round(total, 2)

        mint_usd = _sum_usd(mints)
        burn_usd = _sum_usd(burns)
        return {
            "available": True,
            "source": self.name,
            "mint_count": len(mints),
            "burn_count": len(burns),
            "mint_usd_24h": mint_usd,
            "burn_usd_24h": burn_usd,
            "net_mint_burn_usd": round(mint_usd - burn_usd, 2),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
