"""Ethereum mainnet stablecoin addresses for on-chain integrations (transform.md §5.1–5.2)."""

from __future__ import annotations

ETHEREUM_TOKENS: dict[str, dict[str, object]] = {
    "USDT": {
        "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "decimals": 6,
    },
    "USDC": {
        "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "decimals": 6,
    },
}

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# Default hosted subgraph for ERC-20 transfers on Ethereum (override via Settings).
DEFAULT_GRAPH_SUBGRAPH_URL = (
    "https://api.thegraph.com/subgraphs/name/messari/ethereum-erc20"
)

WHALE_THRESHOLD_USD_DEFAULT = 1_000_000
