"""Tiered Explainable Depeg Watch Score (DEWS) — transform.md §4.3, §9.1.

Combines statistical tripwires, cross-source discrepancy, ONNX depeg probability,
and budget-gated LLM narrative into one explainable 0–100 score per asset.

Circuit breakers: per-source circuit breakers live in core/circuit_breaker.py
and are enforced at the source plugin level (sources/plugins/*). DEWS itself
does not implement circuit breakers — it consumes already-gated source data.
"""

from __future__ import annotations

from typing import Any

BANDS = (
    (0, 25, "normal"),
    (25, 50, "watch"),
    (50, 75, "warning"),
    (75, 101, "critical"),
)


def _band(score: float) -> str:
    for lo, hi, name in BANDS:
        if lo <= score < hi:
            return name
    return "critical"


def compute_dews(
    *,
    z_score_max: float = 0.0,
    cusum_triggered: bool = False,
    cross_source_discrepancy_pct: float = 0.0,
    depeg_probability_24h: float = 0.0,
    llm_escalated: bool = False,
    whale_net_outflow_usd: float = 0.0,
    whale_alert: bool = False,
    top10_holder_share_pct: float = 0.0,
    net_mint_burn_usd_24h: float = 0.0,
) -> dict[str, Any]:
    """Compute DEWS from tier inputs. Each tier is traceable in the response."""
    tiers: list[dict[str, Any]] = []
    score = 0.0

    if abs(z_score_max) > 3.0:
        tier_score = min(35.0, abs(z_score_max) * 8.0)
        score += tier_score
        tiers.append({"tier": 1, "name": "statistical", "detail": f"z_max={z_score_max:.2f}", "points": round(tier_score, 1)})
    if cusum_triggered:
        score += 15.0
        tiers.append({"tier": 1, "name": "cusum", "detail": "slow_drift", "points": 15.0})

    if cross_source_discrepancy_pct > 0.15:
        tier_score = min(25.0, cross_source_discrepancy_pct * 40.0)
        score += tier_score
        tiers.append({"tier": 2, "name": "discrepancy", "detail": f"{cross_source_discrepancy_pct:.2f}%", "points": round(tier_score, 1)})

    if whale_alert or whale_net_outflow_usd >= 5_000_000:
        tier_score = min(15.0, whale_net_outflow_usd / 1_000_000)
        score += tier_score
        tiers.append({"tier": 2, "name": "whale_flow", "detail": f"outflow=${whale_net_outflow_usd:,.0f}", "points": round(tier_score, 1)})

    if top10_holder_share_pct > 50:
        tier_score = min(10.0, (top10_holder_share_pct - 50) * 0.4)
        score += tier_score
        tiers.append({"tier": 2, "name": "holder_concentration", "detail": f"top10={top10_holder_share_pct:.1f}%", "points": round(tier_score, 1)})

    if abs(net_mint_burn_usd_24h) >= 10_000_000:
        tier_score = min(10.0, abs(net_mint_burn_usd_24h) / 2_000_000)
        score += tier_score
        tiers.append({"tier": 2, "name": "mint_burn", "detail": f"net=${net_mint_burn_usd_24h:,.0f}", "points": round(tier_score, 1)})

    if depeg_probability_24h > 0.05:
        tier_score = min(30.0, depeg_probability_24h * 100.0)
        score += tier_score
        tiers.append({"tier": 3, "name": "model", "detail": f"p24h={depeg_probability_24h:.2%}", "points": round(tier_score, 1)})

    if llm_escalated:
        score += 10.0
        tiers.append({"tier": 4, "name": "llm", "detail": "narrative_escalation", "points": 10.0})

    final = min(100.0, round(score, 1))
    return {
        "dews_score": final,
        "band": _band(final),
        "tiers_fired": tiers,
        "tier_count": len(tiers),
    }
