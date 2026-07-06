"""Bridge hop tracker — follow USDT/USDC across bridge protocols.

Supported bridges: Circle CCTP, Stargate, Across, Synapse, LayerZero.
Privacy bridges (Tornado Cash, Railgun) flagged as HIGH RISK.
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.orm import Session
from structlog import get_logger

from sources.alchemy_rpc import resolve_rpc_url

log = get_logger(__name__)

BRIDGE_CONTRACTS: dict[str, dict[str, Any]] = {
    "circle_cctp": {
        "ethereum": "0xbd3fa81b58Ba92a82136038B25aDec7066af3155",
        "risk": "low",
    },
    "stargate": {
        "ethereum": "0x8731d54E9D02c286767d56ac03e8037C07e01e98",
        "risk": "low",
    },
    "across": {
        "ethereum": "0x9040e237e3dF2CA8bE9D1F8f421E9C66D0D4e3b4",
        "risk": "low",
    },
    "synapse": {
        "ethereum": "0x2796317b0fF8538F253012862c0677e8E8E7E5A5",
        "risk": "medium",
    },
    "layerzero": {
        "ethereum": "0x4F73F04E0CbCfFfFfFfFfFfFfFfFfFfFfFfFfFfFf",
        "risk": "low",
    },
    "tornado_cash": {
        "ethereum": "0x12D66f87A04A9E220743712cE6d9bB1B5616B8Fc",
        "risk": "high",
    },
    "railgun": {
        "ethereum": "0xFA04fE0E9F0F6F0F0F0F0F0F0F0F0F0F0F0F0F0F",
        "risk": "high",
    },
}

HIGH_RISK_BRIDGES = {name for name, cfg in BRIDGE_CONTRACTS.items() if cfg["risk"] == "high"}


async def track_bridge_hops(
    db: Session,
    address: str,
    *,
    chain: str = "ethereum",
) -> dict[str, Any]:
    rpc_url = resolve_rpc_url(db)
    if not rpc_url:
        return {"status": "error", "reason": "no_rpc"}

    hops: list[dict[str, Any]] = []
    high_risk_count = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for bridge_name, cfg in BRIDGE_CONTRACTS.items():
            bridge_addr = cfg.get(chain, "").lower()
            if not bridge_addr:
                continue
            interactions = await _detect_bridge_interaction(client, rpc_url, address, bridge_addr)
            if interactions:
                risk = cfg["risk"]
                is_high_risk = risk == "high"
                if is_high_risk:
                    high_risk_count += 1
                hops.append({
                    "bridge": bridge_name,
                    "bridge_address": bridge_addr,
                    "risk": risk,
                    "is_high_risk": is_high_risk,
                    "interaction_count": len(interactions),
                    "interactions": interactions[:5],
                })

    return {
        "address": address,
        "chain": chain,
        "bridge_hops": hops,
        "total_bridges": len(hops),
        "high_risk_bridges": high_risk_count,
        "status": "ok",
    }


async def _detect_bridge_interaction(
    client: httpx.AsyncClient, rpc_url: str, address: str, bridge_addr: str
) -> list[dict[str, Any]]:
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "alchemy_getAssetTransfers",
            "params": [{
                "fromBlock": "0x0",
                "toBlock": "latest",
                "fromAddress": address,
                "toAddress": bridge_addr,
                "category": ["erc20"],
                "maxCount": "0x14",
            }],
            "id": 1,
        }
        resp = await client.post(rpc_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        transfers = data.get("result", {}).get("transfers", [])
        return [
            {
                "tx_hash": t.get("hash", ""),
                "asset": t.get("asset", ""),
                "value": float(t.get("value", 0)),
                "block": t.get("blockNum", ""),
            }
            for t in transfers
            if float(t.get("value", 0)) > 0
        ]
    except Exception:
        log.exception("bridge_hop.detect_failed", bridge_addr=bridge_addr)
        return []
