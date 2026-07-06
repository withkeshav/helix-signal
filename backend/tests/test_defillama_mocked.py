"""Mocked DeFiLlama integration tests.

Uses unittest.mock to patch HTTP calls — no network required.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from sources.defillama import (
    DefiLlamaError,
    _DefiLlamaSource,
    fetch_stablecoin_chart_points,
)


def _mock_response(json_data, status_code=200):
    mock = MagicMock(spec=httpx.Response)
    mock.json.return_value = json_data
    mock.status_code = status_code
    mock.raise_for_status.return_value = None
    return mock


MOCK_STABLECOINS = {
    "peggedAssets": [
        {
            "id": "1",
            "name": "Tether",
            "symbol": "USDT",
            "gecko_id": "tether",
            "pegType": "peggedUSD",
            "price": 0.9995,
            "chainCirculating": {
                "Ethereum": {
                    "current": {"peggedUSD": 60000000000.0},
                    "circulatingPrevDay": {"peggedUSD": 59000000000.0},
                    "circulatingPrevWeek": {"peggedUSD": 57000000000.0},
                    "circulatingPrevMonth": {"peggedUSD": 54000000000.0},
                },
                "Tron": {
                    "current": {"peggedUSD": 40000000000.0},
                    "circulatingPrevDay": {"peggedUSD": 40000000000.0},
                    "circulatingPrevWeek": {"peggedUSD": 38000000000.0},
                    "circulatingPrevMonth": {"peggedUSD": 36000000000.0},
                },
            },
        },
        {
            "id": "2",
            "name": "USD Coin",
            "symbol": "USDC",
            "gecko_id": "usd-coin",
            "pegType": "peggedUSD",
            "price": 1.0001,
            "chainCirculating": {
                "Ethereum": {
                    "current": {"peggedUSD": 28000000000.0},
                    "circulatingPrevDay": {"peggedUSD": 27900000000.0},
                    "circulatingPrevWeek": {"peggedUSD": 27500000000.0},
                    "circulatingPrevMonth": {"peggedUSD": 26800000000.0},
                },
            },
        },
    ],
    "chains": ["Ethereum", "Tron"],
}

import time
_NOW = int(time.time())
_DAY = 86400
MOCK_CHART_POINTS = {
    "peggedUSD": [
        [_NOW - 2 * _DAY, 100000000000.0],
        [_NOW - 1 * _DAY, 100500000000.0],
        [_NOW, 101000000000.0],
    ]
}


# --- fetch_stablecoin_chart_points tests ---


@patch("sources.defillama.http_get_with_retry")
def test_fetch_chart_points_happy_path(mock_get):
    side = [
        _mock_response(MOCK_STABLECOINS),
        _mock_response(MOCK_CHART_POINTS),
    ]
    mock_get.side_effect = side

    result = fetch_stablecoin_chart_points(symbol="USDT", days=365)

    assert len(result) >= 1
    for entry in result:
        assert "timestamp" in entry
        assert "total_supply" in entry
        assert entry["price"] == 1.0
        assert entry["signal_band"] == "Normal"
        assert entry["total_supply"] > 0
    assert mock_get.call_count == 2


@patch("sources.defillama.http_get_with_retry")
def test_fetch_chart_points_symbol_not_found(mock_get):
    mock_get.return_value = _mock_response(MOCK_STABLECOINS)

    with pytest.raises(DefiLlamaError, match="FOO asset id not found"):
        fetch_stablecoin_chart_points(symbol="FOO", days=7)


@patch("sources.defillama.http_get_with_retry")
def test_fetch_chart_points_empty_chart_data(mock_get):
    side = [
        _mock_response(MOCK_STABLECOINS),
        _mock_response({"peggedUSD": []}),
    ]
    mock_get.side_effect = side

    with pytest.raises(DefiLlamaError, match="No chart history returned for USDT"):
        fetch_stablecoin_chart_points(symbol="USDT", days=7)


@patch("sources.defillama.http_get_with_retry")
def test_fetch_chart_points_malformed_json(mock_get):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.side_effect = json.JSONDecodeError("bad json", "", 0)
    mock_get.return_value = mock_resp

    with pytest.raises(json.JSONDecodeError):
        fetch_stablecoin_chart_points(symbol="USDT", days=7)


# --- _DefiLlamaSource._do_fetch tests ---


def _build_source_mock():
    source = _DefiLlamaSource()
    return source


def test_source_fetch_happy_path():
    source = _build_source_mock()
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = _mock_response(MOCK_STABLECOINS)

    result = source._do_fetch(
        httpx_client=mock_client,
        asset_config={
            "defillama_symbol": "USDT",
            "peg_type": "peggedUSD",
            "symbol": "USDT",
        },
        chain_ids=["Ethereum"],
    )

    assert result["asset_symbol"] == "USDT"
    assert result["asset_name"] == "Tether"
    assert "chain_data" in result
    assert "Ethereum" in result["chain_data"]
    eth = result["chain_data"]["Ethereum"]
    assert eth["supply_current"] == 60000000000.0
    assert eth["supply_prev_day"] == 59000000000.0
    assert eth["price"] == 0.9995


def test_source_fetch_missing_asset_config():
    source = _build_source_mock()
    mock_client = MagicMock(spec=httpx.Client)

    result = source._do_fetch(httpx_client=mock_client)

    assert result == {}
    mock_client.get.assert_not_called()


def test_source_fetch_asset_not_found():
    source = _build_source_mock()
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = _mock_response(MOCK_STABLECOINS)

    with pytest.raises(DefiLlamaError, match="NONEXISTENT asset not found"):
        source._do_fetch(
            httpx_client=mock_client,
            asset_config={
                "defillama_symbol": "NONEXISTENT",
                "peg_type": "peggedUSD",
                "symbol": "NONEXISTENT",
            },
            chain_ids=["Ethereum"],
        )


def test_source_fetch_unexpected_payload():
    source = _build_source_mock()
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = _mock_response(["not", "a", "dict"])

    with pytest.raises(DefiLlamaError, match="Unexpected payload"):
        source._do_fetch(
            httpx_client=mock_client,
            asset_config={"defillama_symbol": "USDT", "peg_type": "peggedUSD", "symbol": "USDT"},
            chain_ids=["Ethereum"],
        )


def test_source_fetch_includes_chain_tvl():
    source = _build_source_mock()
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = _mock_response(MOCK_STABLECOINS)

    result = source._do_fetch(
        httpx_client=mock_client,
        asset_config={"defillama_symbol": "USDT", "peg_type": "peggedUSD", "symbol": "USDT"},
        chain_ids=["Ethereum", "Tron"],
        chain_tvl_by_name={"Ethereum": 500000000000.0, "Tron": 10000000000.0},
    )

    assert result["chain_data"]["Ethereum"]["tvl"] == 500000000000.0
    assert result["chain_data"]["Tron"]["tvl"] == 10000000000.0
