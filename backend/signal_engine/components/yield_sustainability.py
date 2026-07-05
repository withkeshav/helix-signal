"""Yield sustainability scorer — evaluates yield vs T-bill for yield-bearing assets."""

from typing import Any

BASE_YIELD_RISK: dict[str, float] = {
    "tbill_tokenized": 0.20,
    "delta_neutral": 0.40,
    "defi_lending": 0.55,
    "undercollat_lending": 0.70,
    "default": 0.50,
}


def compute_yield_sustainability(sub_type: str, inputs: dict[str, Any], tbill_rate: float = 4.5) -> tuple[int, dict[str, Any]]:
    current_apy = inputs.get("current_apy")
    yield_source = inputs.get("yield_source", "unknown")

    if current_apy is None:
        return 50, {"available": False, "reason": "no_apy_data"}

    base_risk = BASE_YIELD_RISK.get(sub_type, BASE_YIELD_RISK["default"])

    excess_yield = current_apy - tbill_rate
    yield_premium = excess_yield / tbill_rate if tbill_rate > 0 else 0

    score = base_risk * 100
    if yield_premium > 2.0:
        score += 30
    elif yield_premium > 1.0:
        score += 15
    elif yield_premium > 0.5:
        score += 5

    if current_apy <= 0:
        score = 100
    elif current_apy < 0.5:
        score = max(score, 75)

    return min(100, round(score)), {
        "available": True,
        "current_apy": current_apy,
        "sub_type": sub_type,
        "yield_source": yield_source,
        "tbill_rate": tbill_rate,
        "excess_yield": round(excess_yield, 2),
        "yield_premium_ratio": round(yield_premium, 2),
        "base_risk_pct": base_risk,
    }
