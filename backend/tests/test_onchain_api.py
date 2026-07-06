"""API tests for on-chain endpoints."""

from unittest.mock import patch


def test_whale_flow_endpoint(client):
    with patch("routes.onchain.get_whale_flow") as mock_fn:
        mock_fn.return_value = {
            "asset": "USDT",
            "available": True,
            "whale_net_outflow_usd": 0,
            "sources": ["thegraph"],
        }
        r = client.get("/api/onchain/whale-flow?asset=USDT")
        assert r.status_code == 200
        body = r.json()
        assert body["asset"] == "USDT"
        assert body["available"] is True


def test_holder_concentration_endpoint(client):
    with patch("routes.onchain.get_holder_concentration") as mock_fn:
        mock_fn.return_value = {
            "asset": "USDC",
            "available": False,
            "message": "Set Moralis API key",
        }
        r = client.get("/api/onchain/holder-concentration?asset=USDC")
        assert r.status_code == 200
        assert r.json()["asset"] == "USDC"
