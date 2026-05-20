from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from database import AssetChainSnapshot, SourceStatus
from sources.defillama import DefiLlamaError, _DefiLlamaSource, fetch_chain_tvl_by_defillama_name, _discover_chain_ids
from sources.coingecko import CoinGeckoSource
from sources.dexscreener import DexScreenerSource
from sources.base import AbstractSource
from structlog import get_logger

log = get_logger(__name__)

CHAINS_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "chains.json"
ASSETS_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "assets.json"

ENABLE_CHAINLINK = False


class SourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, AbstractSource] = {}

    def register(self, source: AbstractSource) -> None:
        self._sources[source.name] = source

    def get(self, name: str) -> AbstractSource | None:
        return self._sources.get(name)

    def all(self) -> list[AbstractSource]:
        return list(self._sources.values())

    def names(self) -> list[str]:
        return list(self._sources.keys())


def build_default_registry() -> SourceRegistry:
    r = SourceRegistry()
    r.register(_DefiLlamaSource())
    r.register(CoinGeckoSource())
    r.register(DexScreenerSource())
    if ENABLE_CHAINLINK:
        from sources.chainlink import ChainlinkSource
        r.register(ChainlinkSource())
    return r


def cross_source_price_check(prices: dict[str, float | None]) -> dict[str, Any]:
    valid = {k: v for k, v in prices.items() if v is not None and v > 0}
    if len(valid) < 2:
        return {"max_discrepancy_pct": 0.0, "discrepancy_flag": False, "sources_agreeing": len(valid), "price_mean": next(iter(valid.values())) if valid else None}
    vals = list(valid.values())
    mean = sum(vals) / len(vals)
    max_disc = max(abs(v - mean) / mean * 100 for v in vals) if mean > 0 else 0.0
    return {
        "max_discrepancy_pct": round(max_disc, 4),
        "discrepancy_flag": max_disc > 0.5,
        "sources_agreeing": len(valid),
        "price_mean": round(mean, 6),
    }


def load_configured_chains() -> list[dict]:
    use_dynamic = os.getenv("ENABLE_DYNAMIC_CHAINS", "").strip().lower() in ("1", "true", "yes")
    if use_dynamic:
        discovered = _discover_chain_ids()
        if discovered:
            return [{"name": name, "defillama_id": name} for name in discovered]
    with CHAINS_CONFIG_PATH.open("r", encoding="utf-8") as file:
        chains = json.load(file)
    if not isinstance(chains, list):
        return []
    return [item for item in chains if isinstance(item, dict) and item.get("defillama_id")]


def load_configured_assets() -> list[dict]:
    with ASSETS_CONFIG_PATH.open("r", encoding="utf-8") as file:
        assets = json.load(file)
    if not isinstance(assets, list):
        return []
    return [item for item in assets if isinstance(item, dict) and item.get("symbol")]


def load_enabled_assets() -> list[dict]:
    return [asset for asset in load_configured_assets() if bool(asset.get("enabled"))]


def get_default_asset_symbol() -> str:
    assets = load_configured_assets()
    for asset in assets:
        if asset.get("default"):
            return str(asset.get("symbol", "USDT")).upper()
    enabled = load_enabled_assets()
    if enabled:
        return str(enabled[0].get("symbol", "USDT")).upper()
    return "USDT"


def get_asset_by_symbol(symbol: str) -> dict | None:
    needle = symbol.upper()
    for asset in load_configured_assets():
        if str(asset.get("symbol", "")).upper() == needle:
            return asset
    return None


def _upsert_source_status(
    db: Session,
    *,
    source_name: str,
    status: str,
    attempted_at: datetime,
    successful_at: datetime | None,
    last_error: str | None,
) -> None:
    row = db.query(SourceStatus).filter(SourceStatus.source_name == source_name).first()
    if row is None:
        row = SourceStatus(source_name=source_name)
        db.add(row)
    row.status = status
    row.last_attempted_fetch = attempted_at
    if successful_at is not None:
        row.last_successful_fetch = successful_at
    row.last_error = last_error
    row.updated_at = datetime.now(timezone.utc)


def refresh_chain_data(db: Session) -> None:
    attempted_at = datetime.now(timezone.utc)
    prior_row = db.query(SourceStatus).filter(SourceStatus.source_name == "defillama").first()
    prior_source_status = prior_row.status if prior_row else None
    configured = load_configured_chains()
    chain_ids = [str(item["defillama_id"]) for item in configured]
    enabled_assets = load_enabled_assets()
    if not enabled_assets:
        _upsert_source_status(db, source_name="defillama", status="error", attempted_at=attempted_at, successful_at=None, last_error="No enabled assets in config/assets.json")
        _upsert_source_status(db, source_name="coingecko", status="error", attempted_at=attempted_at, successful_at=None, last_error="No enabled assets")
        _upsert_source_status(db, source_name="dexscreener", status="error", attempted_at=attempted_at, successful_at=None, last_error="No enabled assets")
        db.commit()
        return

    registry = build_default_registry()
    defillama_src = registry.get("defillama")
    coingecko_src = registry.get("coingecko")
    dexscreener_src = registry.get("dexscreener")

    try:
        errors: list[str] = []
        success_count = 0
        successful_asset_symbols: list[str] = []
        chain_tvl_map = fetch_chain_tvl_by_defillama_name()

        for asset in enabled_assets:
            try:
                llm_snapshot = defillama_src.fetch(asset_config=asset, chain_ids=chain_ids, chain_tvl_by_name=chain_tvl_map) if defillama_src else {}
                fetched_at = llm_snapshot.get("fetched_at", datetime.now(timezone.utc))
                per_chain = llm_snapshot.get("chain_data", {})
                asset_symbol = str(llm_snapshot.get("asset_symbol", asset.get("symbol", ""))).upper()
                asset_name = str(llm_snapshot.get("asset_name") or asset.get("name") or asset_symbol)
                peg_type = str(llm_snapshot.get("peg_type") or asset.get("peg_type") or "peggedUSD")
                success_count += 1
                successful_asset_symbols.append(asset_symbol)

                cg_data = coingecko_src.fetch(symbols=[asset_symbol]) if coingecko_src else {}
                cg_transformed = coingecko_src.transform(cg_data) if coingecko_src else {}
                cg_asset = cg_transformed.get(asset_symbol, {})

                dx_data = dexscreener_src.fetch(symbols=[asset_symbol]) if dexscreener_src else []
                dx_transformed = dexscreener_src.transform(dx_data) if dexscreener_src else {}
                dx_asset = dx_transformed.get(asset_symbol, {})

                for chain in configured:
                    chain_name = str(chain["name"])
                    key = str(chain["defillama_id"])
                    values = per_chain.get(key, {})
                    row = db.query(AssetChainSnapshot).filter(AssetChainSnapshot.asset_symbol == asset_symbol, AssetChainSnapshot.chain_name == chain_name).first()
                    if row is None:
                        row = AssetChainSnapshot(asset_symbol=asset_symbol, chain_name=chain_name)
                        db.add(row)
                    row.asset_name = asset_name
                    row.supply_current = values.get("supply_current")
                    row.supply_prev_day = values.get("supply_prev_day")
                    row.supply_prev_week = values.get("supply_prev_week")
                    row.supply_prev_month = values.get("supply_prev_month")
                    row.tvl = values.get("tvl")
                    row.price = values.get("price")
                    row.price_coingecko = cg_asset.get("price")
                    row.market_cap = cg_asset.get("market_cap")
                    row.volume_24h = cg_asset.get("volume_24h")
                    dex_price = dx_asset.get("price")
                    if dex_price is not None:
                        row.price_dexscreener = dex_price
                    row.total_liquidity_usd = dx_asset.get("total_liquidity_usd")
                    row.top3_pool_share_pct = dx_asset.get("top3_pool_share_pct")
                    row.pool_count = dx_asset.get("pool_count")
                    row.peg_type = peg_type
                    row.source_name = "multi"
                    row.fetched_at = fetched_at
                    row.updated_at = datetime.now(timezone.utc)

            except (DefiLlamaError, Exception) as asset_exc:
                symbol = str(asset.get("symbol", "UNKNOWN")).upper()
                errors.append(f"{symbol}: {asset_exc}")

        if success_count > 0:
            completed_at = datetime.now(timezone.utc)
            _upsert_source_status(db, source_name="defillama", status="ok", attempted_at=attempted_at, successful_at=completed_at, last_error="; ".join(errors) if errors else None)
            _upsert_source_status(db, source_name="coingecko", status="ok", attempted_at=attempted_at, successful_at=completed_at, last_error=None)
            _upsert_source_status(db, source_name="dexscreener", status="ok", attempted_at=attempted_at, successful_at=completed_at, last_error=None)
            from signal_engine.history import persist_trends_and_events
            persist_trends_and_events(db, successful_asset_symbols=list(dict.fromkeys(successful_asset_symbols)), completed_at=completed_at, prior_source_status=prior_source_status)
        else:
            _upsert_source_status(db, source_name="defillama", status="error", attempted_at=attempted_at, successful_at=None, last_error="; ".join(errors) if errors else "No asset refresh succeeded")

    except Exception as exc:
        _upsert_source_status(db, source_name="defillama", status="error", attempted_at=attempted_at, successful_at=None, last_error=str(exc))
    finally:
        db.commit()
