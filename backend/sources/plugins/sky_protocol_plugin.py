"""Sky Protocol plugin — DAI/USDS/sUSDS collateral, DSR, and vault data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session
from structlog import get_logger

from database import CollateralSnapshot, YieldBearingSnapshot
from providers.settings import get_setting

log = get_logger(__name__)

BASE_URL = "https://api.sky.money/v1"


async def fetch(db: Session) -> dict[str, Any]:
    if not get_setting("sky_protocol_enabled", db):
        return {"status": "disabled"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            coll_resp = await client.get(f"{BASE_URL}/collateral")
            coll_resp.raise_for_status()
            coll_data = coll_resp.json()

            dsr_resp = await client.get(f"{BASE_URL}/dsr-rate")
            dsr_resp.raise_for_status()
            dsr_data = dsr_resp.json()

            vault_resp = await client.get(f"{BASE_URL}/vaults/stats")
            vault_resp.raise_for_status()
            vault_data = vault_resp.json()
    except Exception:
        log.exception("sky.fetch_failed")
        return {"status": "error"}

    now = datetime.now(timezone.utc)
    coll_ratio = coll_data.get("collateralRatio")
    total_coll_usd = coll_data.get("totalCollateralUsd")
    dsr_rate = dsr_data.get("dsrRate")
    liquidation_queue = vault_data.get("liquidationQueueUsd")
    debt_ceiling_pct = vault_data.get("debtCeilingUtilizationPct")

    snapshots: list[Any] = [
        CollateralSnapshot(
            asset_symbol="DAI",
            collateral_ratio=coll_ratio,
            collateral_assets_json={"total_collateral_usd": total_coll_usd},
            liquidation_queue_usd=liquidation_queue,
            debt_ceiling_utilization_pct=debt_ceiling_pct,
            timestamp=now,
        ),
        YieldBearingSnapshot(
            asset_symbol="sUSDS",
            current_apy=dsr_rate,
            yield_source="sky_protocol",
            timestamp=now,
        ),
    ]

    db.add_all(snapshots)
    db.commit()
    log.info("sky.fetch_complete", dsr_rate=dsr_rate, coll_ratio=coll_ratio)
    return {"status": "ok", "snapshots": len(snapshots)}
