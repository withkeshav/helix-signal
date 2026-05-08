from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from database import AssetChainSnapshot, SourceStatus
from sources.defillama import DefiLlamaError, fetch_asset_snapshot

CHAINS_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "chains.json"
ASSETS_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "assets.json"


def load_configured_chains() -> list[dict]:
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
    status: str,
    attempted_at: datetime,
    successful_at: datetime | None,
    last_error: str | None,
) -> None:
    row = db.query(SourceStatus).filter(SourceStatus.source_name == "defillama").first()
    if row is None:
        row = SourceStatus(source_name="defillama")
        db.add(row)

    row.status = status
    row.last_attempted_fetch = attempted_at
    if successful_at is not None:
        row.last_successful_fetch = successful_at
    row.last_error = last_error
    row.updated_at = datetime.now(timezone.utc)


def refresh_chain_data(db: Session) -> None:
    attempted_at = datetime.now(timezone.utc)
    configured = load_configured_chains()
    chain_ids = [str(item["defillama_id"]) for item in configured]
    enabled_assets = load_enabled_assets()
    if not enabled_assets:
        _upsert_source_status(
            db,
            status="error",
            attempted_at=attempted_at,
            successful_at=None,
            last_error="No enabled assets in config/assets.json",
        )
        db.commit()
        return

    try:
        latest_fetch_time: datetime | None = None
        errors: list[str] = []
        success_count = 0

        for asset in enabled_assets:
            try:
                snapshot = fetch_asset_snapshot(asset_config=asset, chain_ids=chain_ids)
                fetched_at = snapshot["fetched_at"]
                per_chain = snapshot["chain_data"]
                asset_symbol = str(snapshot.get("asset_symbol", asset.get("symbol", ""))).upper()
                asset_name = str(snapshot.get("asset_name") or asset.get("name") or asset_symbol)
                peg_type = str(snapshot.get("peg_type") or asset.get("peg_type") or "peggedUSD")
                latest_fetch_time = fetched_at
                success_count += 1

                for chain in configured:
                    chain_name = str(chain["name"])
                    key = str(chain["defillama_id"])
                    values = per_chain.get(key, {})
                    row = (
                        db.query(AssetChainSnapshot)
                        .filter(
                            AssetChainSnapshot.asset_symbol == asset_symbol,
                            AssetChainSnapshot.chain_name == chain_name,
                        )
                        .first()
                    )
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
                    row.peg_type = peg_type
                    row.source_name = "defillama"
                    row.fetched_at = fetched_at
                    row.updated_at = datetime.now(timezone.utc)
            except (DefiLlamaError, Exception) as asset_exc:
                symbol = str(asset.get("symbol", "UNKNOWN")).upper()
                errors.append(f"{symbol}: {asset_exc}")

        if success_count > 0:
            _upsert_source_status(
                db,
                status="ok",
                attempted_at=attempted_at,
                successful_at=latest_fetch_time or attempted_at,
                last_error="; ".join(errors) if errors else None,
            )
        else:
            _upsert_source_status(
                db,
                status="error",
                attempted_at=attempted_at,
                successful_at=None,
                last_error="; ".join(errors) if errors else "No asset refresh succeeded",
            )
    except (DefiLlamaError, Exception) as exc:
        _upsert_source_status(
            db,
            status="error",
            attempted_at=attempted_at,
            successful_at=None,
            last_error=str(exc),
        )
        # Intentionally do not raise to keep scheduler worker alive.
    finally:
        db.commit()
