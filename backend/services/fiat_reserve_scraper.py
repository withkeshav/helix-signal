"""Fiat reserve attestation scraper — Tether/Circle/Paxos reserve pages.

Periodically scrapes issuer reserve attestation pages for coverage ratio,
reserve composition, and attestation lag. Stores in FiatReserveSnapshot.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session
from structlog import get_logger

from database import FiatReserveSnapshot

log = get_logger(__name__)

RESERVE_URLS: dict[str, str] = {
    "USDT": "https://www.tether.to/reserves",
    "USDC": "https://www.circle.com/en/usdc-reserves",
    "PYUSD": "https://www.paxos.com/pyusd-reserves",
}

KNOWN_ATTESTATION_SOURCES: dict[str, str] = {
    "USDT": "Tether Transparency Report",
    "USDC": "Circle Monthly Attestation",
    "PYUSD": "Paxos Reserve Report",
}


async def scrape_reserves(db: Session) -> dict[str, Any]:
    """Best-effort issuer page scrape. Never raises — HTML layout drift is expected.

    Isolated so production scheduler cannot crash the process if pages change.
    """
    scraped = 0
    errors = 0

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            for symbol, url in RESERVE_URLS.items():
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    text = resp.text

                    coverage = _extract_coverage(text, symbol)
                    composition = _extract_composition(text, symbol)
                    lag_days = _extract_lag_days(text, symbol)

                    composition = composition or {}
                    # Skip empty parses so we do not store noise rows
                    if coverage is None and "total_reserves_usd" not in composition:
                        log.info("reserve_scraper.empty_parse", asset=symbol)
                        errors += 1
                        continue

                    db.add(FiatReserveSnapshot(
                        asset_symbol=symbol,
                        attestation_date=datetime.now(timezone.utc),
                        reserve_usd=composition.get("total_reserves_usd"),
                        circulating_supply=composition.get("circulating_supply_usd"),
                        coverage_ratio=coverage,
                        reserve_composition=composition,
                        attestation_url=url,
                        attestation_source=KNOWN_ATTESTATION_SOURCES.get(symbol, "unknown"),
                        attestation_lag_days=lag_days,
                        genius_act_compliant=symbol in ("USDC", "PYUSD"),
                        mica_status="compliant" if symbol == "USDC" else "pending" if symbol == "USDT" else "unknown",
                    ))
                    scraped += 1
                except Exception:
                    log.warning("reserve_scraper.failed", asset=symbol, exc_info=True)
                    errors += 1

        if scraped:
            try:
                db.commit()
            except Exception:
                log.exception("reserve_scraper.commit_failed")
                db.rollback()
                return {"status": "error", "scraped": 0, "errors": errors + 1}
    except Exception:
        log.exception("reserve_scraper.fatal")
        try:
            db.rollback()
        except Exception:
            pass
        return {"status": "error", "scraped": 0, "errors": errors + 1}

    log.info("reserve_scraper.complete", scraped=scraped, errors=errors)
    return {"status": "ok", "scraped": scraped, "errors": errors}


def _extract_coverage(text: str, symbol: str) -> float | None:
    if symbol == "USDT":
        import re
        m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*collateralization', text, re.IGNORECASE)
        if m:
            return float(m.group(1)) / 100
        m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*reserve', text, re.IGNORECASE)
        if m:
            return float(m.group(1)) / 100
    return None


def _extract_composition(text: str, symbol: str) -> dict[str, Any]:
    import re
    result: dict[str, Any] = {}
    m = re.search(r'(\d[\d,]*\.?\d*)\s*billion', text, re.IGNORECASE)
    if m:
        try:
            result["total_reserves_usd"] = float(m.group(1).replace(",", "")) * 1_000_000_000
        except ValueError:
            log.debug("reserve_scraper.total_reserves_parse_failed", exc_info=True)
    cash_m = re.search(r'([\d.]+)\s*%\s*cash', text, re.IGNORECASE)
    if cash_m:
        result["cash_equivalent_pct"] = float(cash_m.group(1))
    else:
        result["cash_equivalent_pct"] = 100
    return result


def _extract_lag_days(text: str, symbol: str) -> int | None:
    import re
    m = re.search(r'(?:as\s+of|dated)\s+(\w+\s+\d+,?\s*\d{4})', text, re.IGNORECASE)
    if m:
        try:
            from datetime import datetime as dt
            reported = dt.strptime(m.group(1).replace(",", "").strip(), "%B %d %Y")
            return (datetime.now(timezone.utc).date() - reported.date()).days
        except (ValueError, AttributeError):
            log.debug("reserve_scraper.lag_days_parse_failed", exc_info=True)
    return None
