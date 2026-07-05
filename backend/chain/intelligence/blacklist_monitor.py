"""Blacklist monitor — poll USDT/USDC/PYUSD freeze events from Ethereum + Tron.

Fires SignalEvent alert when frozen_balance_usd > $1M.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session
from structlog import get_logger

from database import BlacklistEvent, SignalEvent
from providers.settings import get_setting

log = get_logger(__name__)

USDT_ETH = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
USDC_ETH = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
PYUSD_ETH = "0x6c3ea903640685c62a45c8565c8e82fb8a9ed2f0b"
USDT_TRON = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

DESTROYED_BLACK_FUNDS = "0x413931bfc0d8e3b869ab5fb69d94fe83b6f0e1a1411cc76d565b0f3673a0b3"
ADDED_BLACKLIST = "0x8da295b66d8f93d2d17bcf3cb9ce4ab934b2a3e5bc9b7d4783f2a17c615fade"
REMOVED_BLACKLIST = "0xc4620b893250fa3b55dee93c496e5c17de3b6be9f5f4344f31b70844b7c8940"

BLACKLIST_CONTRACTS = {
    "USDT": {"address": USDT_ETH, "chain": "ethereum", "decimals": 6},
    "USDC": {"address": USDC_ETH, "chain": "ethereum", "decimals": 6},
    "PYUSD": {"address": PYUSD_ETH, "chain": "ethereum", "decimals": 6},
}

TRON_USDT_CONTRACT = {
    "address": USDT_TRON,
    "chain": "tron",
    "decimals": 6,
}

ALERT_THRESHOLD_USD = 1_000_000
ETH_RPC_URL = os.getenv("ALCHEMY_API_KEY", "")
if ETH_RPC_URL:
    ETH_RPC_URL = f"https://eth-mainnet.g.alchemy.com/v2/{ETH_RPC_URL}"


async def poll(db: Session) -> dict[str, Any]:
    if not get_setting("blacklist_monitor_enabled", db):
        return {"status": "disabled"}

    ethereum_result = await _poll_ethereum(db)
    tron_result = await _poll_tron(db)

    total = ethereum_result.get("events", 0) + tron_result.get("events", 0)
    log.info("blacklist.poll_complete", events=total)
    return {"status": "ok", "ethereum": ethereum_result, "tron": tron_result}


async def _poll_ethereum(db: Session) -> dict[str, Any]:
    if not ETH_RPC_URL:
        log.warning("blacklist.no_alchemy_key")
        return {"events": 0, "error": "no_alchemy_key"}

    events = 0
    alerts = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for sym, cfg in BLACKLIST_CONTRACTS.items():
            latest_block = await _get_latest_block(client)
            from_block = hex(max(0, latest_block - 500))

            payload = {
                "jsonrpc": "2.0",
                "method": "eth_getLogs",
                "params": [{
                    "address": cfg["address"],
                    "fromBlock": from_block,
                    "toBlock": "latest",
                    "topics": [DESTROYED_BLACK_FUNDS],
                }],
                "id": 1,
            }

            try:
                resp = await client.post(ETH_RPC_URL, json=payload)
                resp.raise_for_status()
                logs = resp.json().get("result", [])
            except Exception:
                log.exception("blacklist.eth_rpc_failed", asset=sym)
                continue

            for entry in logs:
                block_num = int(entry.get("blockNumber", "0x0"), 16)
                tx_hash = entry.get("transactionHash", "")
                data = entry.get("data", "0x")
                topics = entry.get("topics", [])

                frozen_address = topics[1] if len(topics) > 1 else ""

                frozen_amount_wei = int(data, 16) if data and data != "0x" else 0
                frozen_amount = frozen_amount_wei / (10 ** cfg["decimals"])
                frozen_usd = frozen_amount

                existing = db.query(BlacklistEvent).filter(
                    BlacklistEvent.tx_hash == tx_hash,
                    BlacklistEvent.chain == "ethereum",
                ).first()
                if existing:
                    continue

                event = BlacklistEvent(
                    asset_symbol=sym,
                    chain="ethereum",
                    frozen_address="0x" + frozen_address[-40:].lower() if frozen_address else "",
                    frozen_balance_usd=frozen_usd,
                    event_type="freeze",
                    tx_hash=tx_hash,
                    block_number=block_num,
                    intelligence_note=f"DestroyedBlackFunds {frozen_amount} {sym} on Ethereum",
                    timestamp=datetime.now(timezone.utc),
                )
                db.add(event)
                events += 1

                if frozen_usd > ALERT_THRESHOLD_USD:
                    db.add(SignalEvent(
                        asset_symbol=sym,
                        chain_key="ethereum",
                        event_type=f"{sym}:blacklist:critical",
                        severity="CRITICAL",
                        title=f"{sym} Blacklist Freeze Detected",
                        summary=f"${frozen_usd:,.0f} {sym} frozen in {tx_hash[:10]}...",
                        new_value=frozen_usd,
                        threshold=f">{ALERT_THRESHOLD_USD}",
                        metadata_json=json.dumps({
                            "frozen_address": frozen_address,
                            "frozen_amount": frozen_amount,
                            "tx_hash": tx_hash,
                            "block_number": block_num,
                        }),
                        timestamp=datetime.now(timezone.utc),
                    ))
                    alerts += 1

    if events or alerts:
        db.commit()
    return {"events": events, "alerts": alerts}


async def _poll_tron(db: Session) -> dict[str, Any]:
    events = 0
    alerts = 0
    now = datetime.now(timezone.utc)
    min_timestamp = int(time.time() * 1000) - 300_000

    async with httpx.AsyncClient(timeout=30) as client:
        url = f"https://api.trongrid.io/v1/contracts/{TRON_USDT_CONTRACT['address']}/events"
        try:
            resp = await client.get(url, params={
                "event_name": "Freeze",
                "min_timestamp": min_timestamp,
                "limit": 50,
            })
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            log.exception("blacklist.tron_rpc_failed")
            return {"events": 0, "error": "tron_rpc_failed"}

        for entry in data.get("data", []):
            tx_hash = entry.get("transaction_id", "")
            result = entry.get("result", {})

            existing = db.query(BlacklistEvent).filter(
                BlacklistEvent.tx_hash == tx_hash,
                BlacklistEvent.chain == "tron",
            ).first()
            if existing:
                continue

            frozen_address = result.get("address0", "")
            frozen_amount = int(result.get("uint2560", "0")) / (10 ** TRON_USDT_CONTRACT["decimals"])
            frozen_usd = frozen_amount
            block_num = entry.get("block_number", 0)

            db.add(BlacklistEvent(
                asset_symbol="USDT",
                chain="tron",
                frozen_address=frozen_address,
                frozen_balance_usd=frozen_usd,
                event_type="freeze",
                tx_hash=tx_hash,
                block_number=block_num,
                intelligence_note=f"Tron USDT freeze {frozen_amount} USDT",
                timestamp=now,
            ))
            events += 1

            if frozen_usd > ALERT_THRESHOLD_USD:
                db.add(SignalEvent(
                    asset_symbol="USDT",
                    chain_key="tron",
                    event_type="USDT:blacklist:critical",
                    severity="CRITICAL",
                    title="USDT Blacklist Freeze Detected (Tron)",
                    summary=f"${frozen_usd:,.0f} USDT frozen on Tron in {tx_hash[:10]}...",
                    new_value=frozen_usd,
                    threshold=f">{ALERT_THRESHOLD_USD}",
                    metadata_json=json.dumps({
                        "frozen_address": frozen_address,
                        "frozen_amount": frozen_amount,
                        "tx_hash": tx_hash,
                        "block_number": block_num,
                    }),
                    timestamp=now,
                ))
                alerts += 1

    if events or alerts:
        db.commit()
    return {"events": events, "alerts": alerts}


async def _get_latest_block(client: httpx.AsyncClient) -> int:
    payload = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
    try:
        resp = await client.post(ETH_RPC_URL, json=payload)
        resp.raise_for_status()
        return int(resp.json().get("result", "0x0"), 16)
    except Exception:
        log.exception("blacklist.latest_block_failed")
        return 0
