"""Reserve coverage scorer — evaluates fiat reserve attestation health."""

from typing import Any


def compute_reserve_coverage(inputs: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    coverage_ratio = inputs.get("coverage_ratio")
    reserve_composition = inputs.get("reserve_composition") or {}

    if coverage_ratio is None:
        return 50, {"available": False, "reason": "no_coverage_data"}

    detail: dict[str, Any] = {"available": True, "coverage_ratio": coverage_ratio}

    if coverage_ratio < 1.0:
        score = 100
        detail["tier"] = "undercollateralized"
    elif coverage_ratio < 1.02:
        score = 75
        detail["tier"] = "thin"
    elif coverage_ratio < 1.05:
        score = 50
        detail["tier"] = "adequate"
    elif coverage_ratio < 1.10:
        score = 25
        detail["tier"] = "strong"
    else:
        score = 0
        detail["tier"] = "overcollateralized"

    cash_short_duration = reserve_composition.get("cash_equivalent_pct", 100)
    if cash_short_duration < 50:
        score = min(100, score + 20)
        detail["cash_short_low"] = True
    detail["cash_equivalent_pct"] = cash_short_duration

    attestation_lag = inputs.get("attestation_lag_days") or 0
    if attestation_lag > 60:
        score = min(100, score + 25)
        detail["attestation_stale"] = True
    elif attestation_lag > 30:
        score = min(100, score + 10)
        detail["attestation_aging"] = True
    detail["attestation_lag_days"] = attestation_lag

    return score, detail
