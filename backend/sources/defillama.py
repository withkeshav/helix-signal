from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sources.base import AbstractSource, async_http_get_with_retry, http_get_with_retry

USDT_STABLECOINS_URL = "https://stablecoins.llama.fi/stablecoins?includePrices=true"
STABLECOIN_CHAINS_URL = "https://stablecoins.llama.fi/stablecoinchains"
STABLECOIN_CHARTS_URL = "https://stablecoins.llama.fi/stablecoincharts/all"
DEFAULT_TIMEOUT_SECONDS = 20


class DefiLlamaError(Exception):
    """Raised when DefiLlama data cannot be fetched or parsed."""


def _discover_chain_ids() -> list[str]:
    try:
        resp = http_get_with_retry(STABLECOIN_CHAINS_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
        payload = resp.json()
        rows = payload if isinstance(payload, list) else payload.get("peggedAssets") or payload.get("chains") or []
        return sorted({str(r["name"]) for r in rows if isinstance(r, dict) and r.get("name")})
    except Exception:
        return []


async def _async_discover_chain_ids() -> list[str]:
    try:
        resp = await async_http_get_with_retry(STABLECOIN_CHAINS_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
        payload = resp.json()
        rows = payload if isinstance(payload, list) else payload.get("peggedAssets") or payload.get("chains") or []
        return sorted({str(r["name"]) for r in rows if isinstance(r, dict) and r.get("name")})
    except Exception:
        return []


def fetch_chain_tvl_by_defillama_name() -> dict[str, float]:
    try:
        resp = http_get_with_retry(STABLECOIN_CHAINS_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
        chains_payload = resp.json()
    except Exception:
        return {}
    rows = chains_payload if isinstance(chains_payload, list) else chains_payload.get("peggedAssets") or chains_payload.get("chains") or []
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


async def async_fetch_chain_tvl_by_defillama_name() -> dict[str, float]:
    try:
        resp = await async_http_get_with_retry(STABLECOIN_CHAINS_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
        chains_payload = resp.json()
    except Exception:
        return {}
    rows = chains_payload if isinstance(chains_payload, list) else chains_payload.get("peggedAssets") or chains_payload.get("chains") or []
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


def fetch_stablecoin_chart_points(*, symbol: str, days: int) -> list[dict]:
    resp = http_get_with_retry(USDT_STABLECOINS_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
    payload = resp.json()
    if not isinstance(payload, dict):
        raise DefiLlamaError("Unexpected stablecoins list payload")
    raw_id = None
    for asset in payload.get("peggedAssets", []):
        if not isinstance(asset, dict):
            continue
        if str(asset.get("symbol", "")).upper() == symbol.upper():
            raw_id = asset.get("id")
            break
    if raw_id is None:
        raise DefiLlamaError(f"{symbol} asset id not found")
    coin_id = int(raw_id) if isinstance(raw_id, int) else int(raw_id)
    charts_resp = http_get_with_retry(f"{STABLECOIN_CHARTS_URL}?stablecoin={coin_id}", timeout=DEFAULT_TIMEOUT_SECONDS)
    charts_payload = charts_resp.json()
    pairs: list[tuple[int, float]] = []
    if isinstance(charts_payload, dict):
        series = charts_payload.get("peggedUSD") or charts_payload.get("totalCirculatingUSD") or []
        if isinstance(series, list):
            for entry in series:
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    ts_raw, val = entry[0], entry[1]
                    if isinstance(ts_raw, (int, float)) and isinstance(val, (int, float)):
                        ts = int(ts_raw)
                        if ts > 10_000_000_000:
                            ts = ts // 1000
                        pairs.append((ts, float(val)))
    elif isinstance(charts_payload, list):
        for entry in charts_payload:
            if isinstance(entry, dict):
                ts_raw = entry.get("date") or entry.get("timestamp")
                val = entry.get("totalCirculating") or entry.get("peggedUSD") or entry.get("circulating")
                if isinstance(ts_raw, (int, float)) and isinstance(val, (int, float)):
                    ts = int(ts_raw)
                    if ts > 10_000_000_000:
                        ts = ts // 1000
                    pairs.append((ts, float(val)))
    if not pairs:
        raise DefiLlamaError(f"No chart history returned for {symbol}")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    by_day: dict[datetime, float] = {}
    for ts, supply in pairs:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        if dt < cutoff:
            continue
        day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        by_day[day] = supply
    out: list[dict] = []
    for day in sorted(by_day.keys()):
        out.append({"timestamp": day, "total_supply": by_day[day], "price": 1.0, "depeg_index": 0, "signal_score": 0, "signal_band": "Normal", "concentration_score": 0})
    return out


class _DefiLlamaSource(AbstractSource):
    name = "defillama"

    def fetch(self, **kwargs: Any) -> dict[str, Any]:
        return self._do_fetch(httpx_client=self.get_http_session(), **kwargs)

    async def async_fetch(self, **kwargs: Any) -> dict[str, Any]:
        client = await self.get_async_http_session()
        return await self._do_async_fetch(client=client, **kwargs)

    def _do_fetch(self, *, httpx_client: httpx.Client, **kwargs: Any) -> dict[str, Any]:
        asset_config = kwargs.get("asset_config")
        chain_ids = kwargs.get("chain_ids", [])
        chain_tvl_by_name = kwargs.get("chain_tvl_by_name")
        if not asset_config:
            return {}
        symbol = str(asset_config.get("defillama_symbol") or asset_config.get("symbol") or "").upper()
        stablecoins_payload = httpx_client.get(USDT_STABLECOINS_URL, timeout=DEFAULT_TIMEOUT_SECONDS).json()
        if not isinstance(stablecoins_payload, dict):
            raise DefiLlamaError("Unexpected payload")
        selected_asset = self._find_asset(stablecoins_payload, symbol)
        if selected_asset is None:
            raise DefiLlamaError(f"{symbol} asset not found")
        return self._build_snapshot(selected_asset, chain_ids, chain_tvl_by_name, symbol, asset_config)

    async def _do_async_fetch(self, *, client: httpx.AsyncClient, **kwargs: Any) -> dict[str, Any]:
        asset_config = kwargs.get("asset_config")
        chain_ids = kwargs.get("chain_ids", [])
        chain_tvl_by_name = kwargs.get("chain_tvl_by_name")
        if not asset_config:
            return {}
        symbol = str(asset_config.get("defillama_symbol") or asset_config.get("symbol") or "").upper()
        resp = await client.get(USDT_STABLECOINS_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
        stablecoins_payload = resp.json()
        if not isinstance(stablecoins_payload, dict):
            raise DefiLlamaError("Unexpected payload")
        selected_asset = self._find_asset(stablecoins_payload, symbol)
        if selected_asset is None:
            raise DefiLlamaError(f"{symbol} asset not found")
        return self._build_snapshot(selected_asset, chain_ids, chain_tvl_by_name, symbol, asset_config)

    def _find_asset(self, payload: dict, symbol: str) -> dict | None:
        for asset in payload.get("peggedAssets", []):
            if not isinstance(asset, dict):
                continue
            asset_symbol = str(asset.get("symbol", "")).upper()
            name = str(asset.get("name", "")).lower()
            gecko_id = str(asset.get("gecko_id", "")).lower()
            desired = symbol.upper()
            if asset_symbol == desired or gecko_id == desired.lower() or desired.lower() in name:
                return asset
        return None

    def _build_snapshot(self, selected_asset: dict, chain_ids: list, chain_tvl_by_name: dict | None, symbol: str, asset_config: dict) -> dict[str, Any]:
        raw_circulating = selected_asset.get("chainCirculating", {})
        chain_circulating: dict = raw_circulating if isinstance(raw_circulating, dict) else {}
        current_map: dict[str, object] = {}
        prev_day_map: dict[str, object] = {}
        prev_week_map: dict[str, object] = {}
        prev_month_map: dict[str, object] = {}
        if isinstance(chain_circulating.get("current"), dict):
            current_map = chain_circulating.get("current", {})
            prev_day_map = chain_circulating.get("circulatingPrevDay", {})
            prev_week_map = chain_circulating.get("circulatingPrevWeek", {})
            prev_month_map = chain_circulating.get("circulatingPrevMonth", {})
        elif isinstance(chain_circulating, dict):
            for cn, entry in chain_circulating.items():
                if isinstance(entry, dict):
                    current_map[str(cn)] = entry.get("current", entry)
                    prev_day_map[str(cn)] = entry.get("circulatingPrevDay", {})
                    prev_week_map[str(cn)] = entry.get("circulatingPrevWeek", {})
                    prev_month_map[str(cn)] = entry.get("circulatingPrevMonth", {})
        lower = {k.lower(): v for k, v in current_map.items()}
        prev_day_lower = {k.lower(): v for k, v in prev_day_map.items()}
        prev_week_lower = {k.lower(): v for k, v in prev_week_map.items()}
        prev_month_lower = {k.lower(): v for k, v in prev_month_map.items()}
        chain_data: dict[str, dict] = {}
        for chain_id in chain_ids:
            def _extract(entry: object) -> float | None:
                if isinstance(entry, (int, float)):
                    return float(entry)
                if not isinstance(entry, dict):
                    return None
                for key in ("peggedUSD", "circulating", "usd", "value"):
                    v = entry.get(key)
                    if isinstance(v, (int, float)):
                        return float(v)
                return None
            cur = current_map.get(chain_id) or lower.get(chain_id.lower(), {})
            pday = prev_day_map.get(chain_id) or prev_day_lower.get(chain_id.lower(), {})
            pweek = prev_week_map.get(chain_id) or prev_week_lower.get(chain_id.lower(), {})
            pmonth = prev_month_map.get(chain_id) or prev_month_lower.get(chain_id.lower(), {})
            chain_data[chain_id] = {
                "supply_current": _extract(cur) or 0.0,
                "supply_prev_day": _extract(pday),
                "supply_prev_week": _extract(pweek),
                "supply_prev_month": _extract(pmonth),
                "price": float(selected_asset.get("price")) if isinstance(selected_asset.get("price"), (int, float)) else None,
                "tvl": None,
            }
        if chain_tvl_by_name:
            for chain_id in chain_ids:
                tv = chain_tvl_by_name.get(chain_id)
                if tv is None:
                    tv = {k.lower(): v for k, v in chain_tvl_by_name.items()}.get(str(chain_id).lower())
                if tv is not None:
                    chain_data[chain_id]["tvl"] = float(tv)
        return {
            "asset_symbol": symbol,
            "asset_name": selected_asset.get("name"),
            "peg_type": asset_config.get("peg_type", "peggedUSD"),
            "fetched_at": datetime.now(timezone.utc),
            "chain_data": chain_data,
        }

    def transform(self, raw: dict[str, Any]) -> dict[str, Any]:
        return raw
