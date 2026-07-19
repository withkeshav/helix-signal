"""Alchemy RPC fallback tests."""

import os
from unittest.mock import patch


def test_resolve_rpc_prefers_chainlink():
    from sources.alchemy_rpc import resolve_rpc_url

    with patch.dict(os.environ, {"CHAINLINK_RPC_URL": "https://rpc.example", "ALCHEMY_API_KEY": "k"}):
        assert resolve_rpc_url() == "https://rpc.example"


def test_resolve_rpc_alchemy_fallback():
    from sources.alchemy_rpc import resolve_rpc_url

    with patch.dict(os.environ, {"CHAINLINK_RPC_URL": "", "ALCHEMY_API_KEY": ""}, clear=False):
        with patch("sources.alchemy_rpc.get_secret", return_value="alchemy-key"):
            url = resolve_rpc_url()
            assert url == "https://eth-mainnet.g.alchemy.com/v2/alchemy-key"
