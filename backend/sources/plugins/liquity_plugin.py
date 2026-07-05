"""Liquity plugin — LUSD protocol stats with graceful 404 handling."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session
from structlog import get_logger

from database import CollateralSnapshot
from providers.settings import get_setting

log = get_logger(__name__)

BASE_URL = "https://api.liquity.org"


async def fetch(db: Session) -> dict[str, Any]:
    if not get_setting("liquity_enabled", db):
        return {"status": "disabled"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            stats_resp = await client.get(f"{BASE_URL}/stats")
            if stats_resp.status_code == 404:
                log.warning("liquity.api_404_disabling")
                from database import SessionLocal
                from providers.settings import set_setting_str
                set_setting_str("liquity_enabled", "false", db)
                db.commit()
                return {"status": "disabled_404"}
            stats_resp.raise_for_status()
            stats_data = stats_resp.json()

            sys_resp = await client.get(f"{BASE_URL}/system-stats")
            if sys_resp.status_code == 404:
                sys_data = {}
            else:
                sys_resp.raise_for_status()
                sys_data = sys_resp.json()
    except Exception:
        log.exception("liquity.fetch_failed")
        return {"status": "error"}

    now = datetime.now(timezone.utc)
    coll_eth = stats_data.get("totalCollateralEth")
    total_debt = stats_data.get("totalDebtLusd")
    coll_ratio = stats_data.get("collateralRatio")
    recovery_mode = sys_data.get("recoveryMode", False)
    liquidation_reserve = stats_data.get("liquidationReserve")

    snapshot = CollateralSnapshot(
        asset_symbol="LUSD",
        collateral_ratio=coll_ratio,
        collateral_assets_json={
            "total_collateral_eth": coll_eth,
            "total_debt_lusd": total_debt,
            "recovery_mode": recovery_mode,
            "liquidation_reserve": liquidation_reserve,
        },
        liquidation_queue_usd=liquidation_reserve,
        timestamp=now,
    )

    db.add(snapshot)
    db.commit()
    log.info("liquity.fetch_complete", coll_ratio=coll_ratio, recovery_mode=recovery_mode)
    return {"status": "ok"}
