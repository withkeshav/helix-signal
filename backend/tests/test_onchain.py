"""Unit tests for on-chain sources and service (mocked HTTP — no network)."""

from unittest.mock import MagicMock, patch

import pytest

from services.onchain import clear_cache_for_tests, get_holder_concentration, get_whale_flow, refresh_onchain_signals
from sources.moralis import MoralisSource
from sources.thegraph import TheGraphSource


@pytest.fixture(autouse=True)
def _clear_onchain_cache():
    clear_cache_for_tests()
    yield
    clear_cache_for_tests()


@patch("services.onchain.get_setting")
def test_whale_flow_unconfigured(mock_get_setting):
    mock_get_setting.side_effect = lambda key, db=None: {
        "feature_onchain_signals": True,
        "provider_thegraph": False,
        "provider_moralis": False,
        "provider_flipside": False,
    }.get(key, False)
    out = get_whale_flow("USDT", db=None)
    assert out["asset"] == "USDT"
    assert out["available"] is False
    assert "required_keys" in out


@patch("sources.thegraph.get_setting")
@patch("sources.thegraph.httpx.post")
def test_thegraph_mint_burn(mock_post, mock_get_setting):
    mock_get_setting.side_effect = lambda key, db=None: {
        "provider_thegraph": True,
        "secret_thegraph_api_key": "",
    }.get(key, False)
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "data": {
                "mints": [{"value": "1000000", "timestamp": "1700000000"}],
                "burns": [{"value": "500000", "timestamp": "1700000000"}],
            }
        },
    )
    result = TheGraphSource().fetch_mint_burn("USDT")
    assert result["available"] is True
    assert result["mint_count"] == 1
    assert result["burn_count"] == 1
    assert result["net_mint_burn_usd"] == 0.5


@patch("sources.moralis.get_setting")
@patch("sources.moralis.httpx.get")
def test_moralis_holder_concentration(mock_get, mock_get_setting):
    mock_get_setting.side_effect = lambda key, db=None: {
        "provider_moralis": True,
        "secret_moralis_api_key": "test-key",
    }.get(key, "")
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "result": [
                {"owner_address": "0xabc", "balance": "600000000000", "percentage_relative_to_total_supply": 40.0},
                {"owner_address": "0xdef", "balance": "400000000000", "percentage_relative_to_total_supply": 25.0},
            ]
        },
    )
    result = MoralisSource().fetch_holder_concentration("USDT")
    assert result["available"] is True
    assert result["top10_share_pct"] == 65.0
    assert result["concentration_risk"] == "high"


@patch("sources.moralis.get_setting")
@patch("sources.moralis.httpx.get")
def test_moralis_large_transfers_whale_alert(mock_get, mock_get_setting):
    mock_get_setting.side_effect = lambda key, db=None: {
        "provider_moralis": True,
        "secret_moralis_api_key": "test-key",
        "onchain_whale_threshold_usd": 1_000_000,
    }.get(key, 1_000_000)
    big = str(2_000_000 * 10**6)
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "result": [
                {"transaction_hash": "0x1", "from_address": "0xa", "to_address": "0xb", "value": big, "block_timestamp": "2026-01-01"},
                {"transaction_hash": "0x2", "from_address": "0xc", "to_address": "0xd", "value": big, "block_timestamp": "2026-01-01"},
                {"transaction_hash": "0x3", "from_address": "0xe", "to_address": "0xf", "value": big, "block_timestamp": "2026-01-01"},
            ]
        },
    )
    result = MoralisSource().fetch_large_transfers("USDT")
    assert result["available"] is True
    assert result["whale_alert"] is True
    assert len(result["large_transfers"]) == 3


@patch("services.onchain.get_setting")
@patch("services.onchain.TheGraphSource")
@patch("services.onchain.MoralisSource")
def test_refresh_and_whale_flow_cached(mock_moralis_cls, mock_graph_cls, mock_get_setting):
    mock_get_setting.side_effect = lambda key, db=None: {
        "feature_onchain_signals": True,
        "provider_thegraph": True,
        "provider_moralis": True,
    }.get(key, False)

    graph = mock_graph_cls.return_value
    graph.fetch_mint_burn.return_value = {
        "available": True,
        "net_mint_burn_usd": 1_000_000,
        "mint_count": 2,
        "burn_count": 1,
    }
    moralis = mock_moralis_cls.return_value
    moralis.configured.return_value = True
    moralis.fetch_large_transfers.return_value = {
        "available": True,
        "whale_net_outflow_usd": 3_000_000,
        "whale_alert": False,
        "large_transfers": [],
    }
    moralis.fetch_holder_concentration.return_value = {"available": True, "top10_share_pct": 45}

    db = MagicMock()
    refresh_onchain_signals(db, symbols=["USDT"])
    out = get_whale_flow("USDT", db)
    assert out["available"] is True
    assert out["net_mint_burn_usd_24h"] == 1_000_000
    assert "thegraph" in out["sources"]


@patch("services.onchain.get_setting")
@patch("services.onchain.MoralisSource")
def test_holder_concentration_requires_moralis(mock_moralis_cls, mock_get_setting):
    mock_get_setting.side_effect = lambda key, db=None: {
        "feature_onchain_signals": True,
        "provider_moralis": False,
        "provider_thegraph": False,
        "provider_flipside": False,
    }.get(key, False)
    mock_moralis_cls.return_value.configured.return_value = False
    out = get_holder_concentration("USDT", db=MagicMock())
    assert out["available"] is False
    assert "Moralis" in out["message"]
