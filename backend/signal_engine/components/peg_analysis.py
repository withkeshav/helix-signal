"""Peg analysis components for stablecoin monitoring."""

from typing import Tuple, Optional

def peg_deviation(price: float | None) -> Tuple[float, float]:
    """Calculate peg deviation metrics.
    
    Args:
        price: Current price of the asset
        
    Returns:
        Tuple of (absolute_deviation, percentage_deviation)
    """
    if price is None or price <= 0:
        return (1.0, 100.0)
    dev = abs(float(price) - 1.0)
    pct = dev * 100.0
    return (dev, pct)

def peg_status_label(price: float | None) -> str:
    """Get peg status label based on price.
    
    Args:
        price: Current price of the asset
        
    Returns:
        Status label: "Healthy", "Watch", or "Alert"
    """
    dev, _ = peg_deviation(price)
    if dev <= 0.001:
        return "Healthy"
    if dev <= 0.005:
        return "Watch"
    return "Alert"

def depeg_index_score(price: float | None) -> int:
    """Calculate depeg index score.
    
    Args:
        price: Current price of the asset
        
    Returns:
        Score from 0-100 (lower is better)
    """
    if price is None:
        return 100
    _, pct = peg_deviation(price)
    if pct <= 0.1:
        return 0
    if pct <= 0.5:
        return 25
    if pct <= 1.0:
        return 50
    if pct <= 2.0:
        return 75
    return 100