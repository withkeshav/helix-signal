from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from sources.base import AbstractSource, http_get_with_retry, async_http_get_with_retry
from services.source_usage import _check_source_rate_limit, _record_source_call
from sources.coingecko_ids import PINNED_COINGECKO_IDS

COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_MARKET_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
DEFAULT_TIMEOUT = 15


def _coin_ids_for_symbols(symbols: list[str]) -> dict[str, str]:
    """Pinned IDs first; symbol lower-case fallback (transform.md §5.4)."""
    out: dict[str, str] = {}
    for s in symbols:
        sym = s.upper()
        out[sym] = PINNED_COINGECKO_IDS.get(sym, sym.lower())
    return out


class CoinGeckoSource(AbstractSource):
    name = "coingecko"

    def fetch(self, **kwargs: Any) -> dict[str, Any]:
        symbols = kwargs.get("symbols", ["USDT", "USDC", "DAI", "PYUSD"])
        coin_ids = _coin_ids_for_symbols(symbols)
        ids = ",".join(coin_ids[s] for s in symbols)
        url = f"{COINGECKO_PRICE_URL}?ids={ids}&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true"
        while not _check_source_rate_limit(self.name):
            time.sleep(1)
        _record_source_call(self.name)
        resp = http_get_with_retry(url, timeout=DEFAULT_TIMEOUT)
        return resp.json()

    async def async_fetch(self, **kwargs: Any) -> dict[str, Any]:
        symbols = kwargs.get("symbols", ["USDT", "USDC", "DAI", "PYUSD"])
        coin_ids = _coin_ids_for_symbols(symbols)
        ids = ",".join(coin_ids[s] for s in symbols)
        url = f"{COINGECKO_PRICE_URL}?ids={ids}&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true"
        while not _check_source_rate_limit(self.name):
            await asyncio.sleep(1)
        _record_source_call(self.name)
        resp = await async_http_get_with_retry(url, timeout=DEFAULT_TIMEOUT)
        return resp.json()

    def transform(self, raw: dict[str, Any]) -> dict[str, Any]:
        reverse = {v: k for k, v in PINNED_COINGECKO_IDS.items()}
        out: dict[str, dict[str, Any]] = {}
        for cid, data in raw.items():
            sym = reverse.get(cid, cid.upper())
            out[sym] = {
                "price": data.get("usd"),
                "market_cap": data.get("usd_market_cap"),
                "volume_24h": data.get("usd_24h_vol"),
                "source": self.name,
                "fetched_at": datetime.now(timezone.utc),
            }
        return out
