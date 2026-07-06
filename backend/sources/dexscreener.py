from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from sources.base import AbstractSource, http_get_with_retry, async_http_get_with_retry
from services.source_usage import _check_source_rate_limit, _record_source_call

DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/token-pairs/v1/{chain}/{address}"
DEFAULT_TIMEOUT = 15

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "dexscreener_addresses.json"


def _load_stablecoin_addresses() -> dict[str, list[tuple[str, str]]]:
    """Load per-chain token addresses from config (transform.md §5.4 — un-hardcode)."""
    if _CONFIG_PATH.is_file():
        raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        return {
            chain: [(sym, addr) for sym, addr in pairs]
            for chain, pairs in raw.items()
        }
    return {
        "ethereum": [
            ("USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7"),
            ("USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
            ("DAI", "0x6B175474E89094C44Da98b954EedeAC495271d0F"),
        ],
        "solana": [
            ("USDT", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"),
            ("USDC", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"),
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
        for chain, tokens in _load_stablecoin_addresses().items():
            for sym, addr in tokens:
                if sym not in symbols:
                    continue
                # Use only the most reliable endpoint to reduce API calls
                url = f"{DEXSCREENER_TOKEN_URL.format(chain=chain, address=addr)}"
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
                except Exception:
                    continue
        return all_pairs

    async def _do_async_fetch(self, client: httpx.AsyncClient, symbols: list[str]) -> list[dict[str, Any]]:
        all_pairs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for chain, tokens in _load_stablecoin_addresses().items():
            for sym, addr in tokens:
                if sym not in symbols:
                    continue
                # Use only the most reliable endpoint to reduce API calls
                url = f"{DEXSCREENER_TOKEN_URL.format(chain=chain, address=addr)}"
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
