"""On-chain signal aggregation — whale flow, holder concentration, mint/burn (transform.md §4.2 #4/#6/#11, §9.5)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from providers.settings import get_setting
from sources.flipside import FlipsideSource
from sources.moralis import MoralisSource
from sources.thegraph import TheGraphSource

_CACHE: dict[str, dict[str, Any]] = {}
_LAST_REFRESH: datetime | None = None


def _feature_enabled(db: Session | None) -> bool:
    return bool(get_setting("feature_onchain_signals", db))


def configured_providers(db: Session | None) -> dict[str, bool]:
    moralis = MoralisSource()
    flipside = FlipsideSource()
    alchemy_key = str(get_setting("secret_alchemy_api_key", db) or "").strip()
    return {
        "thegraph": bool(get_setting("provider_thegraph", db)),
        "moralis": moralis.configured(db),
        "flipside": flipside.configured(db),
        "alchemy_rpc": bool(alchemy_key),
    }


def any_onchain_configured(db: Session | None) -> bool:
    cfg = configured_providers(db)
    return cfg["thegraph"] or cfg["moralis"] or cfg["flipside"]


def refresh_onchain_signals(db: Session, symbols: list[str] | None = None) -> None:
    """Refresh module cache during core refresh loop; respects rate limits."""
    if not _feature_enabled(db):
        return
    if not any_onchain_configured(db):
        return

    from signal_engine.core import load_enabled_assets

    syms = symbols or [str(a.get("symbol", "")).upper() for a in load_enabled_assets()]
    graph = TheGraphSource()
    moralis = MoralisSource()
    flipside = FlipsideSource()

    for sym in syms:
        if not sym:
            continue
        entry: dict[str, Any] = {"asset": sym, "updated_at": datetime.now(timezone.utc).isoformat()}
        if get_setting("provider_thegraph", db):
            entry["mint_burn"] = graph.fetch_mint_burn(sym, db=db)
        if moralis.configured(db):
            entry["holders"] = moralis.fetch_holder_concentration(sym, db=db)
            entry["transfers"] = moralis.fetch_large_transfers(sym, db=db)
        if flipside.configured(db):
            entry["flipside_flow"] = flipside.fetch_holder_flow(sym, db=db)
        _CACHE[sym] = entry

    global _LAST_REFRESH
    _LAST_REFRESH = datetime.now(timezone.utc)


def get_whale_flow(asset: str, db: Session | None = None) -> dict[str, Any]:
    sym = asset.upper()
    if not _feature_enabled(db):
        return _unavailable(sym, "On-chain signals disabled in Settings")

    cfg = configured_providers(db)
    if not any_onchain_configured(db):
        return _unavailable(
            sym,
            "Configure The Graph (free) and/or Moralis API key in Settings",
            required_keys=["provider_thegraph", "secret_moralis_api_key"],
        )

    cached = _CACHE.get(sym, {})
    mint_burn = cached.get("mint_burn") or {}
    transfers = cached.get("transfers") or {}
    flipside_flow = cached.get("flipside_flow") or {}

    if not mint_burn.get("available") and not transfers.get("available") and not flipside_flow.get("available"):
        graph = TheGraphSource()
        moralis = MoralisSource()
        flipside = FlipsideSource()
        if cfg["thegraph"]:
            mint_burn = graph.fetch_mint_burn(sym, db=db)
        if cfg["moralis"]:
            transfers = moralis.fetch_large_transfers(sym, db=db)
        if cfg["flipside"]:
            flipside_flow = flipside.fetch_holder_flow(sym, db=db)

    sources: list[str] = []
    if mint_burn.get("available"):
        sources.append("thegraph")
    if transfers.get("available"):
        sources.append("moralis")
    if flipside_flow.get("available"):
        sources.append("flipside")

    available = bool(sources)
    net_mint_burn = float(mint_burn.get("net_mint_burn_usd") or 0)
    whale_out = float(transfers.get("whale_net_outflow_usd") or 0)
    volume_24h = float(flipside_flow.get("volume_usd_24h") or 0)

    return {
        "asset": sym,
        "available": available,
        "configured": True,
        "providers": cfg,
        "net_mint_burn_usd_24h": net_mint_burn,
        "mint_count_24h": mint_burn.get("mint_count", 0),
        "burn_count_24h": mint_burn.get("burn_count", 0),
        "whale_net_outflow_usd": whale_out,
        "whale_alert": bool(transfers.get("whale_alert")),
        "large_transfers": transfers.get("large_transfers") or [],
        "flipside_volume_usd_24h": volume_24h,
        "flipside_transfer_count_24h": flipside_flow.get("transfer_count_24h", 0),
        "sources": sources,
        "last_refresh": cached.get("updated_at") or (_LAST_REFRESH.isoformat() if _LAST_REFRESH else None),
    }


def get_holder_concentration(asset: str, db: Session | None = None) -> dict[str, Any]:
    sym = asset.upper()
    if not _feature_enabled(db):
        return _unavailable(sym, "On-chain signals disabled in Settings")

    cfg = configured_providers(db)
    if not cfg["moralis"]:
        return _unavailable(
            sym,
            "Set Moralis API key in Settings → API Keys (40K CU/day free tier)",
            required_keys=["secret_moralis_api_key", "provider_moralis"],
        )

    cached = _CACHE.get(sym, {})
    holders = cached.get("holders") or {}
    if not holders.get("available"):
        holders = MoralisSource().fetch_holder_concentration(sym, db=db)

    return {
        "asset": sym,
        "available": bool(holders.get("available")),
        "configured": True,
        "providers": cfg,
        "top10_share_pct": holders.get("top10_share_pct"),
        "concentration_risk": holders.get("concentration_risk"),
        "holders": holders.get("holders") or [],
        "sources": ["moralis"] if holders.get("available") else [],
        "last_refresh": cached.get("updated_at") or (_LAST_REFRESH.isoformat() if _LAST_REFRESH else None),
    }


def onchain_risk_inputs(asset: str, db: Session | None = None) -> dict[str, Any]:
    """Compact fields for DEWS / risk_inputs."""
    whale = get_whale_flow(asset, db)
    holders = get_holder_concentration(asset, db)
    return {
        "whale_net_outflow_usd": float(whale.get("whale_net_outflow_usd") or 0),
        "whale_alert": bool(whale.get("whale_alert")),
        "net_mint_burn_usd_24h": float(whale.get("net_mint_burn_usd_24h") or 0),
        "top10_holder_share_pct": float(holders.get("top10_share_pct") or 0),
        "holder_concentration_risk": holders.get("concentration_risk"),
        "onchain_available": whale.get("available") or holders.get("available"),
    }


def _unavailable(sym: str, message: str, required_keys: list[str] | None = None) -> dict[str, Any]:
    return {
        "asset": sym,
        "available": False,
        "configured": False,
        "message": message,
        "required_keys": required_keys or [],
        "providers": configured_providers(None),
    }


def clear_cache_for_tests() -> None:
    _CACHE.clear()
    global _LAST_REFRESH
    _LAST_REFRESH = None
