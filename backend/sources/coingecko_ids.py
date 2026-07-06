"""Pinned CoinGecko coin IDs — transform.md §5.4 (drop full /coins/list fetch)."""

PINNED_COINGECKO_IDS: dict[str, str] = {
    "USDT": "tether",
    "USDC": "usd-coin",
    "DAI": "dai",
    "PYUSD": "paypal-usd",
    "FRAX": "frax",
    "TUSD": "true-usd",
}
