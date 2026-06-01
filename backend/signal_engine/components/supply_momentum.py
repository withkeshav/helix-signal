"""Supply momentum analysis components."""

from typing import Dict, Any, Optional, Tuple

def supply_momentum_component(
    supply_current: float,
    supply_prev_day: Optional[float],
    supply_prev_week: Optional[float],
    supply_prev_month: Optional[float]
) -> Tuple[int, Dict[str, Any]]:
    """Calculate supply momentum score and details.
    
    Args:
        supply_current: Current supply
        supply_prev_day: Previous day's supply
        supply_prev_week: Previous week's supply
        supply_prev_month: Previous month's supply
        
    Returns:
        Tuple of (score, details_dict)
    """
    scores = []
    details = {}
    
    # Day-over-day change
    if supply_prev_day and supply_prev_day > 0:
        day_change_pct = ((supply_current - supply_prev_day) / supply_prev_day) * 100
        details["day_change_pct"] = round(day_change_pct, 4)
        
        # Score based on magnitude of change (smaller is better)
        if abs(day_change_pct) <= 1.0:
            scores.append(0)
        elif abs(day_change_pct) <= 5.0:
            scores.append(25)
        elif abs(day_change_pct) <= 10.0:
            scores.append(50)
        else:
            scores.append(100)
    else:
        details["day_change_pct"] = None
    
    # Week-over-week change
    if supply_prev_week and supply_prev_week > 0:
        week_change_pct = ((supply_current - supply_prev_week) / supply_prev_week) * 100
        details["week_change_pct"] = round(week_change_pct, 4)
        
        # Score based on magnitude of change (smaller is better)
        if abs(week_change_pct) <= 2.0:
            scores.append(0)
        elif abs(week_change_pct) <= 10.0:
            scores.append(25)
        elif abs(week_change_pct) <= 20.0:
            scores.append(50)
        else:
            scores.append(100)
    else:
        details["week_change_pct"] = None
    
    # Average score
    avg_score = sum(scores) // len(scores) if scores else 0
    
    return (avg_score, details)

def chain_supply_momentum(
    supply_current: Optional[float],
    supply_prev_day: Optional[float],
    supply_prev_week: Optional[float], 
    supply_prev_month: Optional[float]
) -> Dict[str, Any]:
    """Calculate chain supply momentum metrics.
    
    Args:
        supply_current: Current supply
        supply_prev_day: Previous day's supply
        supply_prev_week: Previous week's supply
        supply_prev_month: Previous month's supply
        
    Returns:
        Dictionary of momentum metrics
    """
    momentum = {}
    
    # Calculate percentage changes
    if supply_prev_day and supply_prev_day > 0 and supply_current is not None:
        momentum["day_pct"] = round(((supply_current - supply_prev_day) / supply_prev_day) * 100, 4)
    else:
        momentum["day_pct"] = None
        
    if supply_prev_week and supply_prev_week > 0 and supply_current is not None:
        momentum["week_pct"] = round(((supply_current - supply_prev_week) / supply_prev_week) * 100, 4)
    else:
        momentum["week_pct"] = None
        
    if supply_prev_month and supply_prev_month > 0 and supply_current is not None:
        momentum["month_pct"] = round(((supply_current - supply_prev_month) / supply_prev_month) * 100, 4)
    else:
        momentum["month_pct"] = None
    
    # Determine labels
    momentum["day_label"] = _momentum_label(momentum["day_pct"])
    momentum["week_label"] = _momentum_label(momentum["week_pct"])
    momentum["month_label"] = _momentum_label(momentum["month_pct"])
    
    return momentum

def _momentum_label(pct_change: Optional[float]) -> str:
    """Convert percentage change to descriptive label."""
    if pct_change is None:
        return "Unknown"
    if pct_change > 5:
        return "Strong Increase"
    if pct_change > 1:
        return "Increase"
    if pct_change > -1:
        return "Stable"
    if pct_change > -5:
        return "Decrease"
    return "Strong Decrease"