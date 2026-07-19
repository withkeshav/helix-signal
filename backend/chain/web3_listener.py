from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from structlog import get_logger

from chain.event_handlers import process_stablecoin_logs

log = get_logger(__name__)

ANKR_PUBLIC_RPC = os.getenv("ANKR_PUBLIC_RPC", "https://rpc.ankr.com/eth")

STABLECOIN_CONTRACTS: dict[str, dict[str, Any]] = {
    "USDT": {
        "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "decimals": 6,
        "chain": "ethereum",
    },
    "USDC": {
        "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "decimals": 6,
        "chain": "ethereum",
    },
    "DAI": {
        "address": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
        "decimals": 18,
        "chain": "ethereum",
    },
    "PYUSD": {
        "address": "0x6c3ea903640685c62a45c8565c8e82fb8a9ed2f0b",
        "decimals": 6,
        "chain": "ethereum",
    },
}

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55f4df73b3e"
MINT_TOPIC = "0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c"
BURN_TOPIC = "0xcc16f5dbb4873280815c1ee09dbd06736cffcc184412cf7a71a0edb102f6b3"

POLL_INTERVAL = int(os.getenv("RPC_POLL_INTERVAL_SECONDS", "15"))
MAX_BLOCKS_PER_POLL = int(os.getenv("RPC_MAX_BLOCKS_PER_POLL", "10"))


def _make_jsonrpc_payload(method: str, params: list[Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}


async def _jsonrpc_call(method: str, params: list[Any]) -> Any | None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            ANKR_PUBLIC_RPC,
            json=_make_jsonrpc_payload(method, params),
        )
        resp.raise_for_status()
        data = resp.json()
    if "error" in data:
        log.warning("rpc_listener.rpc_error", method=method, error=data["error"])
        return None
    if "result" not in data:
        log.warning("rpc_listener.no_result", method=method, payload=data)
        return None
    return data["result"]


async def _get_block_number() -> int | None:
    result = await _jsonrpc_call("eth_blockNumber", [])
    if result is None:
        return None
    return int(result, 16)


async def _get_block_logs(block_number: int) -> list[dict[str, Any]]:
    hex_block = hex(block_number)
    addresses = [info["address"] for info in STABLECOIN_CONTRACTS.values()]
    result = await _jsonrpc_call("eth_getLogs", [{
        "fromBlock": hex_block,
        "toBlock": hex_block,
        "address": addresses,
    }])
    return result if isinstance(result, list) else []


async def _fetch_blocks_in_range(from_block: int, to_block: int) -> list[dict[str, Any]]:
    addresses = [info["address"] for info in STABLECOIN_CONTRACTS.values()]
    result = await _jsonrpc_call("eth_getLogs", [{
        "fromBlock": hex(from_block),
        "toBlock": hex(to_block),
        "address": addresses,
    }])
    return result if isinstance(result, list) else []


async def poll_stablecoin_logs() -> None:
    last_block: int | None = None
    log.info("rpc_listener.start", rpc=ANKR_PUBLIC_RPC)

    while True:
        try:
            current_block = await _get_block_number()
            if current_block is None:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            if last_block is None:
                last_block = current_block - 1
                log.info("rpc_listener.initialized", start_block=last_block)
                await asyncio.sleep(POLL_INTERVAL)
                continue

            from_block = last_block + 1
            to_block = min(current_block, from_block + MAX_BLOCKS_PER_POLL - 1)

            if from_block > to_block:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            logs = await _fetch_blocks_in_range(from_block, to_block)
            if logs:
                await process_stablecoin_logs(logs)
                log.info("rpc_listener.logs_processed", count=len(logs), from_block=from_block, to_block=to_block)

            last_block = to_block

        except Exception as exc:
            log.warning("rpc_listener.error", exc_info=True)

        await asyncio.sleep(POLL_INTERVAL)


async def start_block_listener() -> asyncio.Task | None:
    loop = asyncio.get_running_loop()
    task = loop.create_task(poll_stablecoin_logs())
    log.info("rpc_listener.dispatched")
    return task
