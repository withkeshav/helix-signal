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
