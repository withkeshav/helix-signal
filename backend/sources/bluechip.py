"""Bluechip public ratings API client for SMIDGE M/I/G dimensions."""

from __future__ import annotations

import os
from typing import Any

import httpx
from structlog import get_logger

log = get_logger(__name__)

BLUECHIP_BASE = "https://bluechip.org/api/v1"


def fetch_bluechip_ratings(asset_symbol: str, *, api_key: str | None = None) -> dict[str, Any]:
    """Fetch letter grades from Bluechip API (best-effort; returns empty on failure)."""
    sym = asset_symbol.upper()
    key = (api_key or os.getenv("BLUECHIP_API_KEY", "")).strip()
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    # Bluechip uses slug-style identifiers; map common stablecoins
    slug_map = {"USDT": "tether", "USDC": "usd-coin", "DAI": "dai", "PYUSD": "paypal-usd"}
    slug = slug_map.get(sym, sym.lower())

    try:
        with httpx.Client(timeout=12.0) as client:
            resp = client.get(f"{BLUECHIP_BASE}/stablecoins/{slug}", headers=headers)
        if resp.status_code == 404:
            return {"available": False, "reason": "not_found", "asset_symbol": sym}
        resp.raise_for_status()
        data = resp.json()
        ratings = data.get("ratings") or data.get("smidge") or data
        return {
            "available": True,
            "asset_symbol": sym,
            "management": _grade_to_score(ratings.get("M") or ratings.get("management")),
            "implementation": _grade_to_score(ratings.get("I") or ratings.get("implementation")),
            "governance": _grade_to_score(ratings.get("G") or ratings.get("governance")),
            "raw": ratings,
        }
    except Exception as exc:
        log.info("bluechip.fetch_failed", asset=sym, exc_info=True)
        return {"available": False, "reason": str(exc), "asset_symbol": sym}


def _grade_to_score(grade: Any) -> int | None:
    if grade is None:
        return None
    if isinstance(grade, (int, float)):
        return max(0, min(100, int(grade)))
    mapping = {"A": 90, "B": 75, "C": 60, "D": 40, "F": 20}
    letter = str(grade).strip().upper()[:1]
    return mapping.get(letter)
