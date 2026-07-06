"""Peel chain detector — detect laundering peel hop patterns in stablecoin flows.

Start from seed_address, follow outgoing txs, detect pattern:
1 large output + 1 small change output (<10% of principal).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session
from structlog import get_logger

from database import SignalEvent
from sources.alchemy_rpc import resolve_rpc_url

log = get_logger(__name__)

PEEL_CHANGE_THRESHOLD = 0.10
MAX_HOPS = 20
TIMEOUT = 30


async def detect_peel_chain(
    db: Session,
    seed_address: str,
    *,
    chain: str = "ethereum",
    asset_symbol: str = "USDT",
    max_hops: int = MAX_HOPS,
) -> dict[str, Any]:
    rpc_url = resolve_rpc_url(db)
    if not rpc_url:
        return {"status": "error", "reason": "no_rpc"}

    hops: list[dict[str, Any]] = []
    current_address = seed_address.lower()
    total_value_usd = 0.0

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for hop_num in range(max_hops):
            txs = await _fetch_outgoing_txs(client, rpc_url, current_address, asset_symbol)
            peel = _find_peel_hop(txs, current_address)
            if not peel:
                break

            hops.append(peel)
            total_value_usd += peel.get("value_usd", 0)
            current_address = peel.get("next_address", "")
            if not current_address:
                break

    if not hops:
        return {"status": "clean", "hops": [], "seed_address": seed_address}

    _fire_alert(db, seed_address, hops, total_value_usd)
    return {
        "status": "peel_chain_detected",
        "seed_address": seed_address,
        "hop_count": len(hops),
        "total_value_usd": total_value_usd,
        "hops": hops,
    }


async def _fetch_outgoing_txs(
    client: httpx.AsyncClient, rpc_url: str, address: str, symbol: str
) -> list[dict[str, Any]]:
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "alchemy_getAssetTransfers",
            "params": [{
                "fromBlock": "0x0",
                "toBlock": "latest",
                "fromAddress": address,
                "category": ["erc20"],
                "contractAddresses": _contract_for_symbol(symbol),
                "maxCount": "0x3e8",
            }],
            "id": 1,
        }
        resp = await client.post(rpc_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", {}).get("transfers", [])
    except Exception:
        log.exception("peel_chain.fetch_failed", address=address)
        return []


def _find_peel_hop(txs: list[dict[str, Any]], from_address: str) -> dict[str, Any] | None:
    if len(txs) < 2:
        return None

    txs_sorted = sorted(txs, key=lambda t: float(t.get("value", 0)), reverse=True)
    largest = txs_sorted[0]
    largest_value = float(largest.get("value", 0))

    for i, tx in enumerate(txs_sorted):
        if i == 0:
            continue
        change_value = float(tx.get("value", 0))
        if largest_value > 0 and change_value / largest_value < PEEL_CHANGE_THRESHOLD:
            to_addr = largest.get("toAddress", "").lower()
            if to_addr and to_addr != from_address.lower():
                return {
                    "hop_tx_hash": largest.get("hash", ""),
                    "from_address": from_address,
                    "next_address": to_addr,
                    "value_usd": largest_value,
                    "change_address": tx.get("toAddress", ""),
                    "change_value_usd": change_value,
                    "change_pct": round(change_value / largest_value * 100, 2) if largest_value > 0 else 0,
                }
    return None


def _contract_for_symbol(symbol: str) -> list[str]:
    mapping = {
        "USDT": ["0xdAC17F958D2ee523a2206206994597C13D831ec7"],
        "USDC": ["0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"],
        "PYUSD": ["0x6c3ea903640685c62a45c8565c8e82fb8a9ed2f0b"],
    }
    return mapping.get(symbol.upper(), mapping["USDT"])


def _fire_alert(db: Session, seed: str, hops: list, total_usd: float) -> None:
    event = SignalEvent(
        asset_symbol="USDT",
        chain_key="ethereum",
        event_type="PEEL_CHAIN_DETECTED",
        severity="critical",
        title="Peel Chain Laundering Detected",
        summary=f"{len(hops)} hops, ${total_usd:,.0f} total from {seed[:10]}...",
        new_value=total_usd,
        metadata_json=json.dumps({
            "seed_address": seed,
            "hop_count": len(hops),
            "total_value_usd": total_usd,
            "hops": [
                {"from": h["from_address"][:10], "to": h["next_address"][:10], "value": h["value_usd"]}
                for h in hops
            ],
        }),
        timestamp=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
