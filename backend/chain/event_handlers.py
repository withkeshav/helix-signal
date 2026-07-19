from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from structlog import get_logger

from database import AssetChainSnapshot, SessionLocal

log = get_logger(__name__)

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55f4df73b3e"

TOPIC_MAP: dict[str, str] = {
    TRANSFER_TOPIC: "Transfer",
}

STABLECOIN_ADDRESS_MAP: dict[str, str] = {
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
    "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI",
    "0x6c3ea903640685c62a45c8565c8e82fb8a9ed2f0b": "PYUSD",
}


def _address_to_symbol(address: str) -> str | None:
    return STABLECOIN_ADDRESS_MAP.get(address.lower())


def _decode_transfer_log(log: dict[str, Any]) -> dict[str, Any] | None:
    address = log.get("address", "")
    symbol = _address_to_symbol(address)
    if symbol is None:
        return None

    topics = log.get("topics", [])
    if len(topics) < 3:
        return None

    data_hex = log.get("data", "0x")
    value = int(data_hex, 16) if data_hex and data_hex != "0x" else 0

    return {
        "symbol": symbol,
        "from": topics[1],
        "to": topics[2],
        "value": value,
        "tx_hash": log.get("transactionHash", ""),
        "block_number": int(log.get("blockNumber", "0x0"), 16),
        "log_index": int(log.get("logIndex", "0x0"), 16),
    }


def _store_chain_snapshot(db: Session, symbol: str, transfer: dict[str, Any]) -> None:
    chain_name = "Ethereum"
    row = db.execute(
        select(AssetChainSnapshot).where(
            AssetChainSnapshot.asset_symbol == symbol,
            AssetChainSnapshot.chain_name == chain_name,
        )
    ).scalars().first()
    if row is not None and row.supply_current is not None:
        existing_supply = row.supply_current
        if transfer["to"] and not transfer["from"]:
            row.supply_prev_day = existing_supply
            row.supply_current = existing_supply + float(transfer["value"])
        elif transfer["from"] and not transfer["to"]:
            row.supply_prev_day = existing_supply
            row.supply_current = max(0.0, existing_supply - float(transfer["value"]))
        row.updated_at = datetime.now(timezone.utc)


async def process_stablecoin_logs(logs: list[dict[str, Any]]) -> int:
    processed = 0
    for log_entry in logs:
        topics = log_entry.get("topics", [])
        if not topics:
            continue
        topic = topics[0]
        if topic == TRANSFER_TOPIC:
            transfer = _decode_transfer_log(log_entry)
            if transfer is None:
                continue
            db = SessionLocal()
            try:
                _store_chain_snapshot(db, transfer["symbol"], transfer)
                db.commit()
            except Exception as exc:
                log.warning("event_handler.db_error", symbol=transfer["symbol"], exc_info=True)
                db.rollback()
            finally:
                db.close()
            processed += 1

    if processed:
        log.info("event_handler.logs_stored", count=processed)
    return processed
