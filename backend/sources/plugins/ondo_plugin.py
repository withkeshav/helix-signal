"""Ondo plugin — USDY NAV, supply, and APY data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session
from structlog import get_logger

from database import YieldBearingSnapshot
from providers.settings import get_setting

log = get_logger(__name__)

BASE_URL = "https://api.ondo.finance/v1/products/usdy/stats"


async def fetch(db: Session) -> dict[str, Any]:
    if not get_setting("ondo_enabled", db):
        return {"status": "disabled"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(BASE_URL)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        log.exception("ondo.fetch_failed")
        return {"status": "error"}

    now = datetime.now(timezone.utc)
    nav = data.get("navPerShare")
    total_supply = data.get("totalSupply")
    current_apy = data.get("currentApy")
    redemption_lag = data.get("redemptionLagHours")

    snapshot = YieldBearingSnapshot(
        asset_symbol="USDY",
        current_apy=current_apy,
        apy_7d_avg=current_apy,
        yield_source="ondo",
        insurance_fund_usd=total_supply,
        insurance_fund_coverage=nav,
        timestamp=now,
    )

    db.add(snapshot)
    db.commit()
    log.info("ondo.fetch_complete", apy=current_apy, supply=total_supply)
    return {"status": "ok"}
