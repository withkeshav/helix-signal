"""Chainlink USD price feed reads for cross-source peg validation (transform.md §5.1)."""

from __future__ import annotations

import os
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Ethereum mainnet Chainlink USD feeds (8 decimals)
_FEED_ADDRESSES: dict[str, str] = {
    "USDC": "0x8fFfFfd4AfB6115b954Bd326cBe7B4BA576818f6",
    "USDT": "0x3E7d1eAB13AD0104d2750B9863b24D09d030F45E",
    "DAI": "0xAed0c38402a5d19df6Ee03df471Dc06BCA430558",
}

_LATEST_ROUND_DATA = "0xfeaf968c"
_PRICE_CACHE: dict[str, float] = {}

_SESSION: requests.Session | None = None


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        retry = Retry(total=2, backoff_factor=0.5, allowed_methods={"POST"})
        _SESSION.mount("https://", HTTPAdapter(max_retries=retry))
        _SESSION.mount("http://", HTTPAdapter(max_retries=retry))
    return _SESSION


def get_cached_oracle_price(symbol: str) -> float | None:
    return _PRICE_CACHE.get(symbol.upper())


def _decode_latest_round_price(hex_result: str) -> float | None:
    if not hex_result or hex_result == "0x" or len(hex_result) < 130:
        return None
    raw = hex_result[2:]
    # answer is 2nd 32-byte word
    answer_hex = raw[64:128]
    answer = int(answer_hex, 16)
    if answer <= 0:
        return None
    return round(answer / 1e8, 8)


def _resolve_rpc(rpc_url: str | None = None) -> str | None:
    rpc = (rpc_url or os.getenv("CHAINLINK_RPC_URL", "")).strip()
    if rpc:
        return rpc
    try:
        from sources.alchemy_rpc import resolve_rpc_url
        return resolve_rpc_url()
    except Exception:
        return None


def fetch_oracle_price(symbol: str, *, rpc_url: str | None = None) -> float | None:
    sym = symbol.upper()
    feed = _FEED_ADDRESSES.get(sym)
    if not feed:
        return None
    rpc = _resolve_rpc(rpc_url)
    if not rpc:
        return None
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{"to": feed, "data": _LATEST_ROUND_DATA}, "latest"],
        "id": 1,
    }
    try:
        resp = _get_session().post(rpc, json=payload, timeout=12)
        data = resp.json()
        price = _decode_latest_round_price(data.get("result", ""))
        if price is not None:
            _PRICE_CACHE[sym] = price
        return price
    except Exception:
        return None


def refresh_oracle_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch oracle peg prices for enabled symbols; updates module cache."""
    out: dict[str, float] = {}
    rpc = _resolve_rpc() or ""
    for sym in symbols:
        price = fetch_oracle_price(sym, rpc_url=rpc or None)
        if price is not None:
            out[sym.upper()] = price
    return out

