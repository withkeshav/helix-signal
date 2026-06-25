"""Data confidence analysis components."""

from typing import Dict, Any

def chain_data_confidence(
    source_ok: bool,
    chain_snapshot_age_seconds: float | None,
    refresh_interval_seconds: int
) -> Dict[str, Any]:
    """Calculate chain data confidence score.
    
    Args:
        source_ok: Whether the data source is healthy
        chain_snapshot_age_seconds: Age of the chain snapshot in seconds
        refresh_interval_seconds: Configured refresh interval in seconds
        
    Returns:
        Dictionary with confidence score and details
    """
    # Start with source health
    if not source_ok:
        return {
            "score": 0,
            "label": "Low",
            "reason": "Source is degraded or down"
        }
    
    # Calculate freshness score based on age
    if chain_snapshot_age_seconds is None:
        return {
            "score": 25,
            "label": "Medium",
            "reason": "No timestamp available"
        }
    
    # Convert to hours for easier interpretation
    age_hours = chain_snapshot_age_seconds / 3600.0
    
    # Score based on freshness
    if age_hours <= (refresh_interval_seconds / 3600.0):  # Within one refresh cycle
        score = 100
        label = "High"
        reason = "Data is fresh"
    elif age_hours <= (refresh_interval_seconds / 3600.0) * 3:  # Within 3 cycles
        score = 75
        label = "Medium-High"
        reason = "Data is reasonably fresh"
    elif age_hours <= 24:  # Within 24 hours
        score = 50
        label = "Medium"
        reason = "Data is somewhat stale"
    else:  # Older than 24 hours
        score = 25
        label = "Low"
        reason = "Data is stale"
    
    return {
        "score": score,
        "label": label,
        "reason": reason
    }

def composite_confidence_band(score: int) -> str:
    """Convert confidence score to band label.
    
    Args:
        score: Confidence score (0-100)
        
    Returns:
        Band label: "High", "Medium", or "Low"
    """
    if score >= 75:
        return "High"
    if score >= 50:
        return "Medium"
    return "Low"