from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from math import sqrt


def estimate_slippage(
    *,
    size_usd: float,
    pool_reserve_a: float,
    pool_reserve_b: float,
) -> float:
    """
    Constant-product AMM slippage estimate in bps.
    Returns price impact = (1 - input_amount / (input_amount + reserve_in)) * 10000.
    """
    if pool_reserve_a <= 0 or pool_reserve_b <= 0 or size_usd <= 0:
        return 0.0
    if pool_reserve_a >= pool_reserve_b:
        reserve_in = pool_reserve_b
    else:
        reserve_in = pool_reserve_a
    k = pool_reserve_a * pool_reserve_b
    amount_in = min(size_usd, reserve_in * 0.3)
    amount_out = (reserve_in * amount_in) / (reserve_in + amount_in)
    price_before = pool_reserve_b / pool_reserve_a if pool_reserve_a > 0 else 1.0
    reserve_a_after = pool_reserve_a + (amount_in if pool_reserve_a >= pool_reserve_b else amount_out)
    reserve_b_after = k / reserve_a_after if reserve_a_after > 0 else pool_reserve_b
    price_after = reserve_b_after / reserve_a_after if reserve_a_after > 0 else price_before
    impact_pct = abs(price_after - price_before) / price_before if price_before > 0 else 0.0
    bps = impact_pct * 10000
    return round(min(bps, 10000), 2)


def depeg_minutes_above_threshold(
    *,
    price: float | None,
    threshold_bps: float = 50,
    refresh_interval_seconds: int = 300,
) -> int:
    if price is None or price <= 0:
        return refresh_interval_seconds // 60
    dev_bps = abs(price - 1.0) * 10000
    if dev_bps > threshold_bps:
        return refresh_interval_seconds // 60
    return 0


def compute_bridged_share(
    *,
    native_supply: float | None,
    total_supply: float | None,
) -> float | None:
    if native_supply is None or total_supply is None or total_supply <= 0:
        return None
    native_share = native_supply / total_supply
    bridged_share = 1.0 - native_share
    return round(max(0.0, bridged_share) * 100, 2)


def mint_burn_anomaly(
    *,
    current_supply: float | None,
    prev_day_supply: float | None,
    rolling_mean_30d: float | None,
    rolling_std_30d: float | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"mint_burn_24h": None, "z_score": None, "anomaly": False}
    if current_supply is None or prev_day_supply is None or prev_day_supply <= 0:
        return result
    change = current_supply - prev_day_supply
    result["mint_burn_24h"] = round(change, 2)
    if rolling_mean_30d is not None and rolling_std_30d is not None and rolling_std_30d > 0:
        z = (change - rolling_mean_30d) / rolling_std_30d
        result["z_score"] = round(z, 4)
        result["anomaly"] = abs(z) > 3.0
    return result
