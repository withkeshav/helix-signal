from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from sources.base import AbstractSource, SourceError, http_get_with_retry, async_http_get_with_retry
from services.source_usage import _check_source_rate_limit, _record_source_call

DEXSCREENER_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"
DEXSCREENER_PAIRS_URL = "https://api.dexscreener.com/latest/dex/pairs"
DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/token-pairs/v1/{chain}/{address}"
DEFAULT_TIMEOUT = 15
MAX_RETRIES = 2

STABLECOIN_ADDRESSES: dict[str, list[tuple[str, str]]] = {
    "ethereum": [
        ("USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7"),
        ("USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
        ("DAI", "0x6B175474E89094C44Da98b954EedeAC495271d0F"),
    ],
    "solana": [
        ("USDT", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"),
        ("USDC", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"),
    ],
    "bsc": [
        ("USDT", "0x55d398326f99059fF775485246999027B3197955"),
        ("USDC", "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"),
    ],
    "polygon": [
        ("USDT", "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"),
        ("USDC", "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"),
    ],
    "arbitrum": [
        ("USDT", "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9"),
        ("USDC", "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"),
    ],
    "avalanche": [
        ("USDT", "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7"),
    ],
}


class DexScreenerSource(AbstractSource):
    name = "dexscreener"

    def fetch(self, **kwargs: Any) -> list[dict[str, Any]]:
        symbols = kwargs.get("symbols", ["USDT"])
        session = self.get_http_session()
        return self._do_fetch(session, symbols)

    async def async_fetch(self, **kwargs: Any) -> list[dict[str, Any]]:
        symbols = kwargs.get("symbols", ["USDT"])
        client = await self.get_async_http_session()
        return await self._do_async_fetch(client, symbols)

    def _do_fetch(self, session: httpx.Client, symbols: list[str]) -> list[dict[str, Any]]:
        all_pairs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for chain, tokens in STABLECOIN_ADDRESSES.items():
            for sym, addr in tokens:
                if sym not in symbols:
                    continue
                urls = [
                    f"{DEXSCREENER_TOKEN_URL.format(chain=chain, address=addr)}",
                    f"{DEXSCREENER_PAIRS_URL}/{chain}/{addr}",
                    f"{DEXSCREENER_SEARCH_URL}?q={addr}",
                ]
                for url in urls:
                    while not _check_source_rate_limit(self.name):
                        time.sleep(1)
                    try:
                        _record_source_call(self.name)
                        resp = http_get_with_retry(url, timeout=DEFAULT_TIMEOUT)
                        if resp.status_code != 200:
                            continue
                        data = resp.json()
                        pairs = data.get("pairs") or []
                        if pairs and isinstance(pairs, list):
                            for pair in pairs:
                                pid = pair.get("pairAddress", "")
                                if pid and pid not in seen:
                                    seen.add(pid)
                                    all_pairs.append(pair)
                            break
                    except Exception:
                        continue
        return all_pairs

    async def _do_async_fetch(self, client: httpx.AsyncClient, symbols: list[str]) -> list[dict[str, Any]]:
        all_pairs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for chain, tokens in STABLECOIN_ADDRESSES.items():
            for sym, addr in tokens:
                if sym not in symbols:
                    continue
                urls = [
                    f"{DEXSCREENER_TOKEN_URL.format(chain=chain, address=addr)}",
                    f"{DEXSCREENER_PAIRS_URL}/{chain}/{addr}",
                    f"{DEXSCREENER_SEARCH_URL}?q={addr}",
                ]
                for url in urls:
                    while not _check_source_rate_limit(self.name):
                        await asyncio.sleep(1)
                    try:
                        _record_source_call(self.name)
                        resp = await async_http_get_with_retry(url, timeout=DEFAULT_TIMEOUT)
                        if resp.status_code != 200:
                            continue
                        data = resp.json()
                        pairs = data.get("pairs") or []
                        if pairs and isinstance(pairs, list):
                            for pair in pairs:
                                pid = pair.get("pairAddress", "")
                                if pid and pid not in seen:
                                    seen.add(pid)
                                    all_pairs.append(pair)
                            break
                    except Exception:
                        continue
        return all_pairs

    def transform(self, raw: list[dict[str, Any]]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for pair in raw:
            base = (pair.get("baseToken") or {}).get("symbol", "").upper()
            if base not in grouped:
                grouped[base] = []
            grouped[base].append(pair)
        out: dict[str, Any] = {}
        for sym, pairs in grouped.items():
            pairs.sort(key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0), reverse=True)
            top3 = pairs[:3]
            total_liquidity = sum(float(p.get("liquidity", {}).get("usd", 0) or 0) for p in pairs)
            top3_liquidity = sum(float(p.get("liquidity", {}).get("usd", 0) or 0) for p in top3)
            top3_share = (top3_liquidity / total_liquidity * 100) if total_liquidity > 0 else 100
            price_usd = float(pairs[0].get("priceUsd", 0)) if pairs else None
            out[sym] = {
                "price": price_usd,
                "total_liquidity_usd": total_liquidity,
                "top3_pool_share_pct": round(top3_share, 2),
                "pool_count": len(pairs),
                "top_pools": [
                    {
                        "address": p.get("pairAddress"),
                        "dex": p.get("dexId"),
                        "chain": p.get("chainId"),
                        "liquidity_usd": float(p.get("liquidity", {}).get("usd", 0) or 0),
                        "price_usd": float(p.get("priceUsd", 0) or 0),
                        "txns_24h": (p.get("txns", {}) or {}).get("h24", {}).get("buys", 0) + (p.get("txns", {}) or {}).get("h24", {}).get("sells", 0),
                    }
                    for p in top3
                ],
                "source": self.name,
                "fetched_at": now,
            }
        return out
