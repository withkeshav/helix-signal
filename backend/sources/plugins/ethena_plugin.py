"""Ethena protocol data plugin — USDe/sUSDe reserve fund + yields."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session
from structlog import get_logger

from database import YieldBearingSnapshot
from providers.settings import get_setting

log = get_logger(__name__)

BASE_URL = "https://app.ethena.fi/api"


async def fetch(db: Session) -> dict[str, Any]:
    if not get_setting("ethena_enabled", db):
        return {"status": "disabled"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            reserve_resp = await client.get(f"{BASE_URL}/stats/reserve-fund")
            reserve_resp.raise_for_status()
            reserve_data = reserve_resp.json()

            yield_resp = await client.get(f"{BASE_URL}/yields/protocol-and-staking-yield")
            yield_resp.raise_for_status()
            yield_data = yield_resp.json()
    except Exception:
        log.exception("ethena.fetch_failed")
        return {"status": "error"}

    now = datetime.now(timezone.utc)
    reserve_fund_usd = reserve_data.get("reserveFundUsd")
    usde_supply = reserve_data.get("usdeCirculatingSupply")
    susde_supply = reserve_data.get("sUsdeCirculatingSupply")
    susde_apy = yield_data.get("sUsdeApy")
    usde_apy = yield_data.get("usdeApy")
    protocol_revenue = yield_data.get("protocolRevenue")

    coverage = None
    if reserve_fund_usd is not None and usde_supply and usde_supply > 0:
        coverage = reserve_fund_usd / usde_supply

    staking_ratio = None
    if usde_supply and susde_supply and usde_supply > 0:
        staking_ratio = susde_supply / usde_supply

    snapshots = [
        YieldBearingSnapshot(
            asset_symbol="USDe",
            current_apy=usde_apy,
            yield_source="ethena",
            insurance_fund_usd=reserve_fund_usd,
            insurance_fund_coverage=coverage,
            timestamp=now,
        ),
        YieldBearingSnapshot(
            asset_symbol="sUSDe",
            current_apy=susde_apy,
            apy_7d_avg=susde_apy,
            yield_source="ethena",
            staking_ratio=staking_ratio,
            timestamp=now,
        ),
    ]

    db.add_all(snapshots)
    db.commit()
    log.info("ethena.fetch_complete", usde_supply=usde_supply, susde_apy=susde_apy)
    return {"status": "ok", "snapshots": len(snapshots)}
