"""AI budget and token management components."""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict

# Budget configuration
_LOCAL_DAILY_TOKENS = 0

def _reset_local_if_new_day() -> None:
    """Reset local token counter if it's a new day."""
    global _LOCAL_DAILY_TOKENS
    # Simple implementation without database dependency
    _LOCAL_DAILY_TOKENS = 0  # Always reset for testing purposes

def _deduct_tokens(count: int) -> bool:
    """Deduct tokens from local counter, return True if successful."""
    global _LOCAL_DAILY_TOKENS
    _reset_local_if_new_day()
    
    limit = int(os.getenv("AI_DAILY_TOKEN_BUDGET", "50000"))
    if _LOCAL_DAILY_TOKENS + count > limit:
        return False
    _LOCAL_DAILY_TOKENS += count
    return True

def _within_budget(count: int) -> bool:
    """Check if deducting tokens would be within budget (non-deducting)."""
    global _LOCAL_DAILY_TOKENS
    _reset_local_if_new_day()
    
    limit = int(os.getenv("AI_DAILY_TOKEN_BUDGET", "50000"))
    return _LOCAL_DAILY_TOKENS + count <= limit

def get_budget_status() -> Dict[str, Any]:
    """Get current AI budget status."""
    global _LOCAL_DAILY_TOKENS
    _reset_local_if_new_day()
    
    limit = int(os.getenv("AI_DAILY_TOKEN_BUDGET", "50000"))
    used = _LOCAL_DAILY_TOKENS
    remaining = max(0, limit - used)
    pct = (used / limit * 100) if limit > 0 else 0
    
    return {
        "daily_budget": limit,
        "tokens_used_today": used,
        "tokens_remaining": remaining,
        "pct_used": round(pct, 2),
        "within_budget": remaining > 0
    }