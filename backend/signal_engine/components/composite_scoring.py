"""Composite scoring components for risk assessment."""

from typing import Dict, Any
from datetime import datetime, timezone

def compute_risk_score(**kwargs) -> Dict[str, Any]:
    """Compute composite risk score from component scores.
    
    Args:
        **kwargs: Component scores and metadata
        
    Returns:
        Dictionary with composite score, band, and components breakdown
    """
    # Extract component scores
    depeg_score = kwargs.get("depeg_index", 0)
    concentration_score = kwargs.get("concentration_score", 0)
    supply_velocity_1h = kwargs.get("supply_velocity_1h", 0) or 0
    supply_velocity_4h = kwargs.get("supply_velocity_4h", 0) or 0
    source_ok = kwargs.get("source_ok", True)
    age_seconds = kwargs.get("age_seconds", 0) or 0
    
    # Calculate velocity contribution (higher velocity = higher risk)
    velocity_component = 0
    if supply_velocity_1h > 0:
        velocity_component += min(25, abs(supply_velocity_1h) * 5)  # Cap at 25
    if supply_velocity_4h > 0:
        velocity_component += min(15, abs(supply_velocity_4h) * 3)  # Cap at 15
    
    # Calculate age penalty (older data = higher penalty)
    age_penalty = 0
    if age_seconds > 3600:  # Older than 1 hour
        age_penalty = min(20, (age_seconds / 3600) * 2)  # Max 20 point penalty
    
    # Base score is weighted average
    base_score = (depeg_score * 0.35 +  # 35% weight
                  concentration_score * 0.25 +  # 25% weight
                  velocity_component * 0.20 +  # 20% weight
                  age_penalty * 0.20)  # 20% weight (penalty)
    
    # Apply source health modifier
    if not source_ok:
        base_score *= 0.5  # 50% penalty for degraded sources
    
    # Clamp to 0-100 range
    final_score = max(0, min(100, base_score))
    
    # Determine band
    band = _score_to_band(final_score)
    
    # Component breakdown for transparency
    components = {
        "depeg": int(depeg_score),
        "concentration": int(concentration_score),
        "velocity": int(velocity_component),
        "age_penalty": int(age_penalty),
        "source_health": "OK" if source_ok else "DEGRADED"
    }
    
    return {
        "score": int(final_score),
        "band": band,
        "components": components
    }

def _score_to_band(score: float) -> str:
    """Convert score to risk band.
    
    Args:
        score: Risk score (0-100)
        
    Returns:
        Risk band: "Very Low", "Low", "Medium", "High", or "Very High"
    """
    if score <= 20:
        return "Very Low"
    if score <= 40:
        return "Low"
    if score <= 60:
        return "Medium"
    if score <= 80:
        return "High"
    return "Very High"

def compute_freshness(
    source_status: str,
    last_successful_fetch: datetime | None,
    newest_chain_snapshot: datetime | None,
    refresh_interval_seconds: int
) -> Dict[str, Any]:
    """Compute freshness metrics.
    
    Args:
        source_status: Status of the data source
        last_successful_fetch: Timestamp of last successful fetch
        newest_chain_snapshot: Timestamp of newest chain snapshot
        refresh_interval_seconds: Configured refresh interval
        
    Returns:
        Dictionary with freshness metrics
    """
    # Determine basis timestamp
    basis_timestamp = newest_chain_snapshot or last_successful_fetch
    basis = "chain_snapshot" if newest_chain_snapshot else "source_fetch"
    
    if basis_timestamp is None:
        return {
            "status": "unknown",
            "age_seconds": None,
            "age_minutes": None,
            "basis_timestamp": None,
            "basis": basis,
            "fresh_window_seconds": refresh_interval_seconds,
            "warning_window_seconds": refresh_interval_seconds * 3,
            "fresh_window_minutes": refresh_interval_seconds / 60,
            "stale_window_minutes": (refresh_interval_seconds * 6) / 60,
            "reason": "No timestamp available"
        }
    
    # Calculate age
    now = datetime.now(timezone.utc)
    age_seconds = (now - basis_timestamp).total_seconds()
    age_minutes = age_seconds / 60
    
    # Determine status based on age
    fresh_window = refresh_interval_seconds
    warning_window = refresh_interval_seconds * 3
    stale_window = refresh_interval_seconds * 6
    
    if age_seconds <= fresh_window:
        status = "fresh"
        reason = "Recently updated"
    elif age_seconds <= warning_window:
        status = "aging"
        reason = "Last update was recent but not current"
    elif age_seconds <= stale_window:
        status = "stale"
        reason = "Data is getting old, updates needed"
    else:
        status = "very stale"
        reason = "Data is very old, potential issues"
    
    return {
        "status": status,
        "age_seconds": round(age_seconds, 1),
        "age_minutes": round(age_minutes, 1),
        "basis_timestamp": basis_timestamp.isoformat(),
        "basis": basis,
        "fresh_window_seconds": fresh_window,
        "warning_window_seconds": warning_window,
        "fresh_window_minutes": fresh_window / 60,
        "stale_window_minutes": stale_window / 60,
        "reason": reason
    }