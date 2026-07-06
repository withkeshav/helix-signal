"""Alchemy RPC URL resolution when CHAINLINK_RPC_URL is unset (transform.md §5.2)."""

from __future__ import annotations

import os
from typing import Any

from providers.settings import get_setting


def resolve_rpc_url(db: Any = None) -> str | None:
    """Prefer CHAINLINK_RPC_URL, then ALCHEMY_RPC_URL full override, then build from key."""
    rpc = os.getenv("CHAINLINK_RPC_URL", "").strip()
    if rpc:
        return rpc
    full = os.getenv("ALCHEMY_RPC_URL", "").strip()
    if full:
        return full
    api_key = str(get_setting("secret_alchemy_api_key", db) or os.getenv("ALCHEMY_API_KEY", "")).strip()
    if api_key:
        # key in path per Alchemy convention. Never log or render full URL.
        return f"https://eth-mainnet.g.alchemy.com/v2/{api_key}"
    return None
