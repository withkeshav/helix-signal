"""Settings-backed overrides for config/assets.json enabled flags."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from providers.settings import get_setting, set_setting
from signal_engine.core import get_asset_by_symbol, load_configured_assets


def _parse_overrides(raw: Any) -> dict[str, bool]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k).upper(): bool(v) for k, v in raw.items()}
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k).upper(): bool(v) for k, v in data.items()}
        except json.JSONDecodeError:
            return {}
    return {}


def get_asset_overrides(db: Session | None) -> dict[str, bool]:
    return _parse_overrides(get_setting("asset_enable_overrides", db))


def effective_asset_enabled(asset: dict[str, Any], overrides: dict[str, bool]) -> bool:
    sym = str(asset.get("symbol", "")).upper()
    if sym in overrides:
        return overrides[sym]
    return bool(asset.get("enabled"))


def load_enabled_assets_with_overrides(db: Session | None = None) -> list[dict[str, Any]]:
    overrides = get_asset_overrides(db)
    result: list[dict[str, Any]] = []
    for asset in load_configured_assets():
        if effective_asset_enabled(asset, overrides):
            out = dict(asset)
            out["enabled"] = True
            result.append(out)
    return result


def catalog_assets(db: Session | None = None) -> list[dict[str, Any]]:
    overrides = get_asset_overrides(db)
    catalog: list[dict[str, Any]] = []
    for asset in load_configured_assets():
        sym = str(asset.get("symbol", "")).upper()
        catalog.append({
            **asset,
            "symbol": sym,
            "config_enabled": bool(asset.get("enabled")),
            "enabled": effective_asset_enabled(asset, overrides),
            "override": sym in overrides,
        })
    return catalog


def set_asset_enabled(db: Session, symbol: str, enabled: bool) -> dict[str, bool]:
    sym = symbol.strip().upper()
    if get_asset_by_symbol(sym) is None:
        raise ValueError(f"Unknown asset: {sym}")
    overrides = get_asset_overrides(db)
    overrides[sym] = bool(enabled)
    set_setting("asset_enable_overrides", json.dumps(overrides), db)
    return overrides
