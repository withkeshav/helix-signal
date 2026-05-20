from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from sources.base import AbstractSource

COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_MARKET_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
COINGECKO_ASSET_URL = "https://api.coingecko.com/api/v3/coins/list"
DEFAULT_TIMEOUT = 15

_COINGECKO_IDS: dict[str, str] = {}


def _load_coin_ids() -> dict[str, str]:
    global _COINGECKO_IDS
    if _COINGECKO_IDS:
        return _COINGECKO_IDS
    with httpx.Client(timeout=httpx.Timeout(DEFAULT_TIMEOUT)) as client:
        resp = client.get(COINGECKO_ASSET_URL)
        resp.raise_for_status()
        for coin in resp.json():
            sym = str(coin.get("symbol", "")).upper()
            cid = str(coin.get("id", ""))
            if sym and cid:
                _COINGECKO_IDS[sym] = cid
    return _COINGECKO_IDS


class CoinGeckoSource(AbstractSource):
    name = "coingecko"

    def fetch(self, **kwargs: Any) -> dict[str, Any]:
        symbols = kwargs.get("symbols", ["USDT", "USDC", "DAI", "PYUSD"])
        session = self.get_http_session()
        coin_ids = _load_coin_ids()
        ids = ",".join(coin_ids.get(s, s.lower()) for s in symbols)
        url = f"{COINGECKO_PRICE_URL}?ids={ids}&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true"
        resp = session.get(url, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def transform(self, raw: dict[str, Any]) -> dict[str, Any]:
        coin_ids = _load_coin_ids()
        reverse = {v: k for k, v in coin_ids.items()}
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
