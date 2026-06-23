"""Concentration analysis components."""

from typing import List, Tuple, Dict, Any


def concentration_component(
    chain_shares: List[float],
    top3_dex_pool_share: float | None = None,
) -> Tuple[int, Dict[str, Any]]:
    """Calculate concentration score and details.

    Args:
        chain_shares: List of chain share percentages (0.0-1.0)
        top3_dex_pool_share: Share of top 3 DEX pools if available (0-100)

    Returns:
        Tuple of (score, details_dict)
    """
    if not chain_shares:
        return (0, {"hhi": 0, "top_chain_share_pct": 0})

    hhi = sum(share ** 2 for share in chain_shares) * 10000

    top_chain_share = max(chain_shares) * 100 if chain_shares else 0

    # Crypto-calibrated HHI thresholds
    if hhi <= 2000:
        hhi_score = 0
    elif hhi <= 4000:
        hhi_score = 25
    elif hhi <= 7000:
        hhi_score = 50
    else:
        hhi_score = 75

    pool_score = 0
    if top3_dex_pool_share is not None:
        pool_pct = float(top3_dex_pool_share)
        if pool_pct >= 80:
            pool_score = 25
        elif pool_pct >= 60:
            pool_score = 15
        elif pool_pct >= 40:
            pool_score = 8

    score = min(100, hhi_score + pool_score)

    details = {
        "hhi": round(hhi, 2),
        "top_chain_share_pct": round(top_chain_share, 2),
        "top3_dex_pool_share_pct": round(float(top3_dex_pool_share), 2) if top3_dex_pool_share is not None else None,
    }

    return (score, details)


def composite_band(score: int) -> str:
    """Convert concentration score to band label."""
    if score <= 25:
        return "Healthy"
    if score <= 50:
        return "Watch"
    return "Alert"
