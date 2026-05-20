from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session

from signal_engine.core import get_asset_by_symbol
from structlog import get_logger

log = get_logger(__name__)

ETHERSCAN_API = "https://api.etherscan.io/api"


def build_governance_payload(db: Session, *, asset: str) -> dict[str, Any]:
    sym = asset.strip().upper()
    selected = get_asset_by_symbol(sym)
    if selected is None or not bool(selected.get("enabled")):
        raise HTTPException(status_code=404, detail=f"Asset '{sym}' is not enabled")
    api_key = os.getenv("ETHERSCAN_API_KEY", "")
    result: dict[str, Any] = {
        "asset": sym,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "events": [],
        "health_score": None,
        "note": "Etherscan API key required for live governance monitoring.",
    }
    if not api_key:
        return result
    addresses = {
        "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
    }
    addr = addresses.get(sym)
    if not addr:
        return result
    try:
        resp = requests.get(ETHERSCAN_API, params={"module": "account", "action": "txlist", "address": addr, "startblock": 0, "endblock": 99999999, "page": 1, "offset": 10, "sort": "desc", "apikey": api_key}, timeout=15)
        data = resp.json()
        if data.get("status") == "1":
            events = []
            for tx in (data.get("result") or [])[:10]:
                events.append({
                    "hash": tx.get("hash"),
                    "block": tx.get("blockNumber"),
                    "from": tx.get("from"),
                    "to": tx.get("to"),
                    "timestamp": datetime.fromtimestamp(int(tx.get("timeStamp", 0)), tz=timezone.utc).isoformat().replace("+00:00", "Z") if tx.get("timeStamp") else None,
                    "method": tx.get("methodId", "0x"),
                })
            result["events"] = events
            result["health_score"] = 100 if len(events) < 5 else 80
            result["note"] = "Governance events from Etherscan (last 10 transactions)."
    except Exception as exc:
        log.warning("governance_fetch_failed", error=str(exc))
        result["note"] = f"Failed to fetch governance data: {exc}"
    return result
