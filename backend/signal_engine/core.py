from __future__ import annotations

import asyncio
import json
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from database import AssetChainSnapshot, AssetFreshness, SourceStatus
from sources.defillama import DefiLlamaError, _DefiLlamaSource, async_fetch_chain_tvl_by_defillama_name, _discover_chain_ids
from sources.coingecko import CoinGeckoSource
from sources.dexscreener import DexScreenerSource
from sources.base import AbstractSource
from core.registry import get_source
from services.source_usage import increment_source_usage
from structlog import get_logger

log = get_logger(__name__)

CHAINS_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "chains.json"
ASSETS_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "assets.json"

class SourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, AbstractSource] = {}

    def register(self, source: AbstractSource) -> None:
        self._sources[source.name] = source

    def get(self, name: str) -> AbstractSource | None:
        return self._sources.get(name)

    def all(self) -> list[AbstractSource]:
        return list(self._sources.values())




def build_default_registry(db: Session | None = None) -> SourceRegistry:
    r = SourceRegistry()
    plugin_src = get_source("defillama")
    if plugin_src is not None:
        r.register(plugin_src)
    else:
        r.register(_DefiLlamaSource())
    r.register(CoinGeckoSource())
    r.register(DexScreenerSource())
    from providers.settings import get_setting
    if get_setting("enable_chainlink", db):
        plugin_src = get_source("chainlink")
        if plugin_src is not None:
            r.register(plugin_src)
        else:
            from sources.chainlink import ChainlinkSource
            r.register(ChainlinkSource())
    return r


def cross_source_price_check(prices: dict[str, float | None]) -> dict[str, Any]:
    valid = {k: v for k, v in prices.items() if v is not None and v > 0}
    if len(valid) < 2:
        single = next(iter(valid.values())) if valid else None
        return {"max_discrepancy_pct": 0.0, "discrepancy_flag": False, "sources_agreeing": len(valid), "price_median": single, "price_mean": single}
    vals = list(valid.values())
    med = statistics.median(vals)
    max_disc = max(abs(v - med) / med * 100 for v in vals) if med > 0 else 0.0
    return {
        "max_discrepancy_pct": round(max_disc, 4),
        "discrepancy_flag": max_disc > 0.5,
        "sources_agreeing": len(valid),
        "price_median": round(med, 6),
        "price_mean": round(sum(vals) / len(vals), 6),
    }

def load_configured_chains(db: Session | None = None) -> list[dict]:
    from providers.settings import get_setting
    use_dynamic = get_setting("enable_dynamic_chains", db)
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
    row.previous_status = row.status
    row.status = status
    row.last_attempted_fetch = attempted_at
    if successful_at is not None:
        row.last_successful_fetch = successful_at
    row.last_error = last_error
    row.updated_at = datetime.now(timezone.utc)
    
    # Increment usage counter for this source
    increment_source_usage(db, source_name)


async def refresh_chain_data(db: Session) -> None:
    attempted_at = datetime.now(timezone.utc)
    prior_row = db.query(SourceStatus).filter(SourceStatus.source_name == "defillama").first()
    prior_source_status = prior_row.status if prior_row else None
    configured = load_configured_chains(db)
    chain_ids = [str(item["defillama_id"]) for item in configured]
    enabled_assets = load_enabled_assets()
    if not enabled_assets:
        _upsert_source_status(db, source_name="defillama", status="error", attempted_at=attempted_at, successful_at=None, last_error="No enabled assets in config/assets.json")
        _upsert_source_status(db, source_name="coingecko", status="error", attempted_at=attempted_at, successful_at=None, last_error="No enabled assets")
        _upsert_source_status(db, source_name="dexscreener", status="error", attempted_at=attempted_at, successful_at=None, last_error="No enabled assets")
        db.commit()
        return

    registry = build_default_registry(db)
    defillama_src = registry.get("defillama")
    coingecko_src = registry.get("coingecko")
    dexscreener_src = registry.get("dexscreener")

    try:
        errors: list[str] = []
        success_count = 0
        successful_asset_symbols: list[str] = []
        cg_ok = False
        dx_ok = False
        cg_error: str | None = None
        dx_error: str | None = None

        all_symbols = [str(a.get("symbol", "")).upper() for a in enabled_assets]

        chain_tvl_task = asyncio.create_task(async_fetch_chain_tvl_by_defillama_name())

        async def _fetch_asset(idx: int, asset: dict, tvl_map: dict[str, float]) -> tuple[int, dict | None, Exception | None]:
            try:
                if defillama_src:
                    result = await defillama_src.async_fetch(
                        asset_config=asset, chain_ids=chain_ids, chain_tvl_by_name=tvl_map
                    )
                    return idx, result, None
                return idx, None, None
            except (DefiLlamaError, Exception) as exc:
                return idx, None, exc

        async def _fetch_coingecko() -> tuple[dict | None, str | None]:
            try:
                data = await coingecko_src.async_fetch(symbols=all_symbols) if coingecko_src else {}
                transformed = coingecko_src.transform(data) if coingecko_src else {}
                return transformed, None
            except Exception as exc:
                return None, str(exc)

        async def _fetch_dexscreener() -> tuple[dict | None, str | None]:
            try:
                data = await dexscreener_src.async_fetch(symbols=all_symbols) if dexscreener_src else []
                transformed = dexscreener_src.transform(data) if dexscreener_src else {}
                return transformed, None
            except Exception as exc:
                return None, str(exc)

        tvl_map, cg_result, dx_result = await asyncio.gather(
            chain_tvl_task,
            _fetch_coingecko(),
            _fetch_dexscreener(),
        )
        cg_transformed, cg_error = cg_result
        cg_ok = cg_transformed is not None
        dx_transformed, dx_error = dx_result
        dx_ok = dx_transformed is not None

        dl_results = await asyncio.gather(
            *[_fetch_asset(i, asset, tvl_map) for i, asset in enumerate(enabled_assets)]
        )

        # Prepare bulk operations
        asset_chain_snapshots_to_update = []
        asset_chain_snapshots_to_create = []
        asset_freshness_updates = []

        # Get existing snapshots for bulk update
        asset_symbols = [str(enabled_assets[idx].get("symbol", "")).upper() 
                        for idx, llm_snapshot, asset_exc in dl_results 
                        if asset_exc is None and llm_snapshot is not None]
        
        chain_names = [str(chain["name"]) for chain in configured]
        
        # Query all existing snapshots for the assets and chains we're working with
        existing_snapshots = db.query(AssetChainSnapshot).filter(
            AssetChainSnapshot.asset_symbol.in_(asset_symbols),
            AssetChainSnapshot.chain_name.in_(chain_names)
        ).all()
        
        # Create a lookup dict for existing snapshots
        snapshot_lookup = {(s.asset_symbol, s.chain_name): s for s in existing_snapshots}
        
        # Also get existing asset freshness records
        existing_freshness = db.query(AssetFreshness).filter(
            AssetFreshness.asset_symbol.in_(asset_symbols)
        ).all()
        
        freshness_lookup = {f.asset_symbol: f for f in existing_freshness}

        for idx, llm_snapshot, asset_exc in dl_results:
            if asset_exc is not None or llm_snapshot is None:
                symbol = str(enabled_assets[idx].get("symbol", "UNKNOWN")).upper() if idx < len(enabled_assets) else "UNKNOWN"
                errors.append(f"{symbol}: {asset_exc}")
                continue

            fetched_at = llm_snapshot.get("fetched_at", datetime.now(timezone.utc))
            per_chain = llm_snapshot.get("chain_data", {})
            asset_symbol = str(llm_snapshot.get("asset_symbol", enabled_assets[idx].get("symbol", ""))).upper()
            asset_name = str(llm_snapshot.get("asset_name") or enabled_assets[idx].get("name") or asset_symbol)
            peg_type = str(llm_snapshot.get("peg_type") or enabled_assets[idx].get("peg_type") or "peggedUSD")
            success_count += 1
            successful_asset_symbols.append(asset_symbol)

            cg_asset = (cg_transformed or {}).get(asset_symbol, {})
            dx_asset = (dx_transformed or {}).get(asset_symbol, {})

            for chain in configured:
                chain_name = str(chain["name"])
                key = str(chain["defillama_id"])
                values = per_chain.get(key, {})
                
                # Check if snapshot exists in our lookup
                snapshot_key = (asset_symbol, chain_name)
                if snapshot_key in snapshot_lookup:
                    # Update existing snapshot
                    row = snapshot_lookup[snapshot_key]
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
                    asset_chain_snapshots_to_update.append(row)
                else:
                    # Create new snapshot
                    new_snapshot = AssetChainSnapshot(
                        asset_symbol=asset_symbol,
                        chain_name=chain_name,
                        asset_name=asset_name,
                        supply_current=values.get("supply_current"),
                        supply_prev_day=values.get("supply_prev_day"),
                        supply_prev_week=values.get("supply_prev_week"),
                        supply_prev_month=values.get("supply_prev_month"),
                        tvl=values.get("tvl"),
                        price=values.get("price"),
                        price_coingecko=cg_asset.get("price"),
                        market_cap=cg_asset.get("market_cap"),
                        volume_24h=cg_asset.get("volume_24h"),
                        price_dexscreener=dx_asset.get("price") if dx_asset.get("price") is not None else None,
                        total_liquidity_usd=dx_asset.get("total_liquidity_usd"),
                        top3_pool_share_pct=dx_asset.get("top3_pool_share_pct"),
                        pool_count=dx_asset.get("pool_count"),
                        peg_type=peg_type,
                        source_name="multi",
                        fetched_at=fetched_at,
                        updated_at=datetime.now(timezone.utc)
                    )
                    asset_chain_snapshots_to_create.append(new_snapshot)

            # Prepare asset freshness updates
            completed_at = datetime.now(timezone.utc)
            if asset_symbol in freshness_lookup:
                # Update existing freshness record
                freshness_row = freshness_lookup[asset_symbol]
                freshness_row.last_successful_fetch = completed_at
                freshness_row.updated_at = completed_at
                asset_freshness_updates.append(freshness_row)
            else:
                # Create new freshness record
                new_freshness = AssetFreshness(
                    asset_symbol=asset_symbol,
                    last_successful_fetch=completed_at,
                    updated_at=completed_at
                )
                asset_freshness_updates.append(new_freshness)

        # Perform bulk operations
        if asset_chain_snapshots_to_create:
            db.bulk_save_objects(asset_chain_snapshots_to_create)
        
        # For updates, we need to merge since they're already attached to the session
        # The updates are already applied to the objects, so we just need to commit
        
        # Also commit the freshness updates
        for freshness_obj in asset_freshness_updates:
            if freshness_obj.id is None:  # New object
                db.add(freshness_obj)
            # Existing objects are already updated in place

        if success_count > 0:
            completed_at = datetime.now(timezone.utc)
            _upsert_source_status(db, source_name="defillama", status="ok", attempted_at=attempted_at, successful_at=completed_at, last_error="; ".join(errors) if errors else None)
            _upsert_source_status(
                db,
                source_name="coingecko",
                status="ok" if cg_ok else "error",
                attempted_at=attempted_at,
                successful_at=completed_at if cg_ok else None,
                last_error=cg_error,
            )
            _upsert_source_status(
                db,
                source_name="dexscreener",
                status="ok" if dx_ok else "error",
                attempted_at=attempted_at,
                successful_at=completed_at if dx_ok else None,
                last_error=dx_error,
            )

            from signal_engine.history import persist_trends_and_events
            from services.source_usage import flush_source_usage
            from services.cache import invalidate_dashboard

            symbols = list(dict.fromkeys(successful_asset_symbols))
            persist_trends_and_events(db, successful_asset_symbols=symbols, completed_at=completed_at, prior_source_status=prior_source_status)
            flush_source_usage(db)  # Flush cached source usage
            for sym in symbols:
                invalidate_dashboard(sym)
        else:
            _upsert_source_status(db, source_name="defillama", status="error", attempted_at=attempted_at, successful_at=None, last_error="; ".join(errors) if errors else "No asset refresh succeeded")

    except Exception as exc:
        _upsert_source_status(db, source_name="defillama", status="error", attempted_at=attempted_at, successful_at=None, last_error=str(exc))
    finally:
        db.commit()
