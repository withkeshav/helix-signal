"""Coinglass plugin — ETH perpetual funding rates."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session
from structlog import get_logger

from database import FundingRateSnapshot
from providers.settings import get_setting

log = get_logger(__name__)

BASE_URL = "https://open-api.coinglass.com/public/v2"
EXCHANGES = ["binance", "bybit", "okx"]


async def fetch(db: Session) -> dict[str, Any]:
    if not get_setting("coinglass_enabled", db):
        return {"status": "disabled"}

    api_key = get_setting("coinglass_api_key", db) or ""
    if not api_key:
        log.warning("coinglass.no_api_key")
        return {"status": "not_configured"}

    now = datetime.now(timezone.utc)
    created = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for exchange in EXCHANGES:
            try:
                resp = await client.get(
                    f"{BASE_URL}/funding_rates_chart",
                    params={"symbol": "ETH", "type": "U", "exchange": exchange},
                    headers={"coinglassSecret": api_key},
                )
                resp.raise_for_status()
                data = resp.json()
                rows = data.get("data", [])
                if rows:
                    latest = rows[-1]
                    rate = latest.get("fundingRate")
                    annualized = rate * 3 * 365 if rate is not None else None
                    db.add(FundingRateSnapshot(
                        exchange=exchange,
                        symbol="ETH",
                        funding_rate=rate,
                        annualized_rate=annualized,
                        next_funding_time=now,
                        timestamp=now,
                    ))
                    created += 1
            except Exception:
                log.exception("coinglass.fetch_failed", exchange=exchange)

    if created:
        db.commit()
    log.info("coinglass.fetch_complete", snapshots=created)
    return {"status": "ok", "snapshots": created}
