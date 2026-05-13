from __future__ import annotations

from datetime import datetime, timezone

import requests

USDT_STABLECOINS_URL = "https://stablecoins.llama.fi/stablecoins?includePrices=true"
STABLECOIN_CHAINS_URL = "https://stablecoins.llama.fi/stablecoinchains"
DEFAULT_TIMEOUT_SECONDS = 20


class DefiLlamaError(Exception):
    """Raised when DefiLlama data cannot be fetched or parsed."""


def _request_json(url: str) -> dict | list:
    response = requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return data
    raise DefiLlamaError(f"Unexpected JSON root type from {url!r}")


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
        if not isinstance(asset, dict):
            continue
        asset_symbol = str(asset.get("symbol", "")).upper()
        name = str(asset.get("name", "")).lower()
        gecko_id = str(asset.get("gecko_id", "")).lower()
        desired = symbol.upper()
        if asset_symbol == desired or gecko_id == desired.lower() or desired.lower() in name:
            return asset
    raise DefiLlamaError(f"{symbol} asset not found in DefiLlama payload")


def fetch_chain_tvl_by_defillama_name() -> dict[str, float]:
    """
    Chain-level aggregate stablecoin TVL from DefiLlama stablecoinchains.
    Keyed by chain name as returned by DefiLlama (must match config chain `defillama_id` / name keys).
    This is NOT per-asset TVL; use only as `Chain TVL` context.
    """
    try:
        chains_payload = _request_json(STABLECOIN_CHAINS_URL)
    except Exception:
        return {}

    if isinstance(chains_payload, list):
        rows = chains_payload
    elif isinstance(chains_payload, dict):
        rows = chains_payload.get("peggedAssets") or chains_payload.get("chains") or []
    else:
        return {}
    if not isinstance(rows, list):
        return {}
    if not isinstance(rows, list):
        return {}

    out: dict[str, float] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("chain") or item.get("id") or "").strip()
        if not name:
            continue
        tvl_value = item.get("tvl")
        if isinstance(tvl_value, (int, float)):
            out[name] = float(tvl_value)
    return out


def fetch_asset_snapshot(
    *,
    asset_config: dict,
    chain_ids: list[str],
    chain_tvl_by_name: dict[str, float] | None = None,
) -> dict:
    symbol = str(asset_config.get("defillama_symbol") or asset_config.get("symbol") or "").upper()
    if not symbol:
        raise DefiLlamaError("Invalid asset config: missing symbol")

    stablecoins_payload = _request_json(USDT_STABLECOINS_URL)
    selected_asset = _find_asset(stablecoins_payload, symbol=symbol)

    raw_circulating = selected_asset.get("chainCirculating", {})
    # API has returned both dict-shaped maps and empty lists; only dict supports .get().
    chain_circulating: dict = raw_circulating if isinstance(raw_circulating, dict) else {}
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

    tvl_map = chain_tvl_by_name or {}
    for chain_id in chain_ids:
        # Prefer exact key, then case-insensitive match on chain name.
        tv = tvl_map.get(chain_id)
        if tv is None:
            lower = {k.lower(): v for k, v in tvl_map.items()}
            tv = lower.get(str(chain_id).lower())
        if tv is not None:
            chain_data[chain_id]["tvl"] = float(tv)

    return {
        "asset_symbol": symbol,
        "asset_name": selected_asset.get("name"),
        "peg_type": asset_config.get("peg_type", "peggedUSD"),
        "fetched_at": datetime.now(timezone.utc),
        "chain_data": chain_data,
    }
