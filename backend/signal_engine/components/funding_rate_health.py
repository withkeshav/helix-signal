"""Funding rate health scorer — for delta-neutral yield-bearing assets (USDe/sUSDe)."""

from typing import Any


def compute_funding_rate_health(inputs: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    avg_rate_7d = inputs.get("avg_funding_rate_7d")
    insurance_coverage = inputs.get("insurance_fund_coverage_ratio")
    susde_apy_delta = inputs.get("susde_apy_7d_delta")

    if avg_rate_7d is None and insurance_coverage is None:
        return 50, {"available": False, "reason": "no_funding_data"}

    score = 0
    detail: dict[str, Any] = {"available": True}

    if avg_rate_7d is not None:
        if avg_rate_7d <= 0:
            score += 30
            detail["funding_negative"] = True
        elif avg_rate_7d < 0.02:
            score += 15
            detail["funding_low"] = True
        detail["avg_funding_rate_7d"] = avg_rate_7d

    if insurance_coverage is not None:
        if insurance_coverage < 0.02:
            score += 40
            detail["insurance_critical"] = True
        elif insurance_coverage < 0.05:
            score += 20
            detail["insurance_low"] = True
        detail["insurance_coverage_ratio"] = insurance_coverage

    if susde_apy_delta is not None:
        if susde_apy_delta < -0.30:
            score += 25
            detail["apy_dropping"] = True
        elif susde_apy_delta < -0.15:
            score += 10
            detail["apy_declining"] = True
        detail["susde_apy_7d_delta"] = susde_apy_delta

    return min(100, score), detail
