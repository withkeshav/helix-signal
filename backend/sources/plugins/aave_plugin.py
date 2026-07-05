"""Aave plugin — GHO supply, borrow, and utilization data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session
from structlog import get_logger

from database import YieldBearingSnapshot
from providers.settings import get_setting

log = get_logger(__name__)

AAVE_API = "https://aave-api-v2.aave.com/data/markets"


async def fetch(db: Session) -> dict[str, Any]:
    if not get_setting("aave_enabled", db):
        return {"status": "disabled"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(AAVE_API)
            resp.raise_for_status()
            markets = resp.json()
    except Exception:
        log.exception("aave.fetch_failed")
        return {"status": "error"}

    gho_data = None
    for m in markets if isinstance(markets, list) else []:
        if m.get("id", "").upper() == "GHO":
            gho_data = m
            break

    if not gho_data:
        log.warning("aave.gho_not_found")
        return {"status": "not_found"}

    now = datetime.now(timezone.utc)
    gho_supply = gho_data.get("totalLiquidity") or gho_data.get("totalSupply")
    gho_borrow_rate = gho_data.get("variableBorrowRate")
    util_rate = gho_data.get("utilizationRate")
    avail_liquidity = gho_data.get("availableLiquidity")

    snapshot = YieldBearingSnapshot(
        asset_symbol="GHO",
        current_apy=gho_borrow_rate,
        yield_source="aave",
        lending_utilization_pct=util_rate,
        insurance_fund_usd=avail_liquidity,
        insurance_fund_coverage=gho_supply / avail_liquidity if avail_liquidity and avail_liquidity > 0 else None,
        timestamp=now,
    )

    db.add(snapshot)
    db.commit()
    log.info("aave.fetch_complete", util_rate=util_rate, supply=gho_supply)
    return {"status": "ok"}
