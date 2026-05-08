from __future__ import annotations

from datetime import datetime, timezone

import requests

USDT_STABLECOINS_URL = "https://stablecoins.llama.fi/stablecoins?includePrices=true"
STABLECOIN_CHAINS_URL = "https://stablecoins.llama.fi/stablecoinchains"
DEFAULT_TIMEOUT_SECONDS = 20


class DefiLlamaError(Exception):
    """Raised when DefiLlama data cannot be fetched or parsed."""


def _request_json(url: str) -> dict:
    response = requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def _extract_numeric(entry: object) -> float | None:
    if isinstance(entry, (int, float)):
        return float(entry)
    if not isinstance(entry, dict):
        return None

    for key in ("peggedUSD", "circulating", "usd", "value"):
        value = entry.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _find_asset(payload: dict, *, symbol: str) -> dict:
    assets = payload.get("peggedAssets", [])
    for asset in assets:
        asset_symbol = str(asset.get("symbol", "")).upper()
        name = str(asset.get("name", "")).lower()
        gecko_id = str(asset.get("gecko_id", "")).lower()
        desired = symbol.upper()
        if asset_symbol == desired or gecko_id == desired.lower() or desired.lower() in name:
            return asset
    raise DefiLlamaError(f"{symbol} asset not found in DefiLlama payload")


def fetch_asset_snapshot(*, asset_config: dict, chain_ids: list[str]) -> dict:
    symbol = str(asset_config.get("defillama_symbol") or asset_config.get("symbol") or "").upper()
    if not symbol:
        raise DefiLlamaError("Invalid asset config: missing symbol")

    stablecoins_payload = _request_json(USDT_STABLECOINS_URL)
    selected_asset = _find_asset(stablecoins_payload, symbol=symbol)

    chain_circulating = selected_asset.get("chainCirculating", {})
    current_map: dict[str, object] = {}
    prev_day_map: dict[str, object] = {}
    prev_week_map: dict[str, object] = {}
    prev_month_map: dict[str, object] = {}

    # Some payloads are shaped as {"current": {...}}, others as {"Ethereum": {"current": ...}}.
    if isinstance(chain_circulating.get("current"), dict):
        current_map = chain_circulating.get("current", {})
        prev_day_map = chain_circulating.get("circulatingPrevDay", {})
        prev_week_map = chain_circulating.get("circulatingPrevWeek", {})
        prev_month_map = chain_circulating.get("circulatingPrevMonth", {})
    elif isinstance(chain_circulating, dict):
        for chain_name, entry in chain_circulating.items():
            if isinstance(entry, dict):
                current_map[str(chain_name)] = entry.get("current", entry)
                prev_day_map[str(chain_name)] = entry.get("circulatingPrevDay", {})
                prev_week_map[str(chain_name)] = entry.get("circulatingPrevWeek", {})
                prev_month_map[str(chain_name)] = entry.get("circulatingPrevMonth", {})

    lowercase_lookup = {key.lower(): value for key, value in current_map.items()}
    prev_day_lowercase_lookup = {key.lower(): value for key, value in prev_day_map.items()}
    prev_week_lowercase_lookup = {key.lower(): value for key, value in prev_week_map.items()}
    prev_month_lowercase_lookup = {key.lower(): value for key, value in prev_month_map.items()}

    chain_data: dict[str, dict] = {}
    for chain_id in chain_ids:
        current_entry = current_map.get(chain_id)
        if current_entry is None:
            current_entry = lowercase_lookup.get(chain_id.lower(), {})
        prev_day_entry = prev_day_map.get(chain_id)
        if prev_day_entry is None:
            prev_day_entry = prev_day_lowercase_lookup.get(chain_id.lower(), {})
        prev_week_entry = prev_week_map.get(chain_id)
        if prev_week_entry is None:
            prev_week_entry = prev_week_lowercase_lookup.get(chain_id.lower(), {})
        prev_month_entry = prev_month_map.get(chain_id)
        if prev_month_entry is None:
            prev_month_entry = prev_month_lowercase_lookup.get(chain_id.lower(), {})
        chain_data[chain_id] = {
            "supply_current": _extract_numeric(current_entry) or 0.0,
            "supply_prev_day": _extract_numeric(prev_day_entry),
            "supply_prev_week": _extract_numeric(prev_week_entry),
            "supply_prev_month": _extract_numeric(prev_month_entry),
            "price": float(selected_asset.get("price")) if isinstance(selected_asset.get("price"), (int, float)) else None,
            "tvl": None,
        }

    # TVL is optional for this phase; populate if available.
    try:
        chains_payload = _request_json(STABLECOIN_CHAINS_URL)
        chains = chains_payload.get("peggedAssets", [])
        if isinstance(chains, list):
            by_name = {str(item.get("name", "")): item for item in chains if isinstance(item, dict)}
            for chain_id in chain_ids:
                item = by_name.get(chain_id, {})
                tvl_value = item.get("tvl")
                if isinstance(tvl_value, (int, float)):
                    chain_data[chain_id]["tvl"] = float(tvl_value)
    except Exception:
        # Keep TVL nullable if this supplemental fetch fails.
        pass

    return {
        "asset_symbol": symbol,
        "asset_name": selected_asset.get("name"),
        "peg_type": asset_config.get("peg_type", "peggedUSD"),
        "fetched_at": datetime.now(timezone.utc),
        "chain_data": chain_data,
    }
