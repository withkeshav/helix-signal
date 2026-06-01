"""Concentration analysis components."""

from typing import List, Tuple, Dict, Any
import math

def concentration_component(
    chain_shares: List[float], 
    top3_dex_pool_share: float | None = None
) -> Tuple[int, Dict[str, Any]]:
    """Calculate concentration score and details.
    
    Args:
        chain_shares: List of chain share percentages (0.0-1.0)
        top3_dex_pool_share: Share of top 3 DEX pools if available
        
    Returns:
        Tuple of (score, details_dict)
    """
    if not chain_shares:
        return (0, {"hhi": 0, "top_chain_share_pct": 0})
    
    # Calculate Herfindahl-Hirschman Index (HHI)
    hhi = sum(share ** 2 for share in chain_shares) * 10000  # Normalize to 0-10000
    
    # Calculate top chain share
    top_chain_share = max(chain_shares) * 100 if chain_shares else 0
    
    # Score based on HHI (lower is better for diversification)
    if hhi <= 1000:  # Highly competitive (many small players)
        score = 0
    elif hhi <= 1800:  # Moderately concentrated
        score = 25
    elif hhi <= 3600:  # Highly concentrated
        score = 50
    else:  # Extremely concentrated
        score = 100
    
    details = {
        "hhi": round(hhi, 2),
        "top_chain_share_pct": round(top_chain_share, 2)
    }
    
    return (score, details)

def composite_band(score: int) -> str:
    """Convert concentration score to band label.
    
    Args:
        score: Concentration score (0-100)
        
    Returns:
        Band label: "Healthy", "Watch", or "Alert"
    """
    if score <= 25:
        return "Healthy"
    if score <= 50:
        return "Watch"
    return "Alert"