"""Collateral health scorer — evaluates over-collateralization per protocol."""

from typing import Any

LIQUIDATION_THRESHOLDS: dict[str, float] = {
    "DAI": 1.20,
    "USDS": 1.20,
    "LUSD": 1.10,
    "GHO": 1.05,
    "crvUSD": 1.10,
    "default": 1.10,
}


def compute_collateral_health(asset_symbol: str, inputs: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    collateral_ratio = inputs.get("collateral_ratio")
    if collateral_ratio is None:
        return 50, {"available": False, "reason": "no_collateral_ratio"}

    threshold = LIQUIDATION_THRESHOLDS.get(asset_symbol.upper(), LIQUIDATION_THRESHOLDS["default"])
    headroom = (collateral_ratio - threshold) / threshold if threshold > 0 else 0

    if collateral_ratio <= threshold:
        score = 100
    elif headroom <= 0.15:
        score = 75
    elif headroom <= 0.50:
        score = 50
    elif headroom <= 1.0:
        score = 25
    else:
        score = 0

    liquidation_queue = inputs.get("liquidation_queue_usd") or 0
    recovery_mode = inputs.get("recovery_mode", False)
    if recovery_mode:
        score = min(100, score + 25)
    if liquidation_queue > 50_000_000:
        score = min(100, score + 15)

    return score, {
        "available": True,
        "collateral_ratio": collateral_ratio,
        "threshold": threshold,
        "headroom_pct": round(headroom * 100, 2),
        "liquidation_queue_usd": liquidation_queue,
        "recovery_mode": recovery_mode,
    }
